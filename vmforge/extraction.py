"""Extração restrita: manifesto validado e conteúdo enviado por stdout."""
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path, PureWindowsPath

MAX_BYTES = 128 * 1024**3
MAX_ENTRIES = 128


def sevenzip_path():
    candidates = []
    if os.name == 'nt':
        for root in (os.environ.get('ProgramFiles'), os.environ.get('ProgramFiles(x86)')):
            if root:
                candidates.append(str(Path(root) / '7-Zip' / '7z.exe'))
    candidates += [shutil.which(cmd) for cmd in ('7zz', '7z', '7za', '7z.exe')]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            try:
                cp = subprocess.run([candidate, 'i'], capture_output=True, text=True,
                                    encoding='utf-8', errors='strict', timeout=15)
                if cp.returncode == 0 and re.search(r'\b7z\b', cp.stdout):
                    return candidate
            except (OSError, UnicodeError, subprocess.TimeoutExpired):
                continue
    raise RuntimeError('7-Zip compatível não encontrado; necessário para validar o manifesto com segurança.')


def find_extractor():
    if os.name == 'nt':
        native = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'tar.exe'
        if native.is_file():
            try:
                cp = subprocess.run([str(native), '--version'], capture_output=True,
                                    text=True, timeout=15)
                if cp.returncode == 0 and 'bsdtar' in cp.stdout.lower():
                    return 'tar', str(native)
            except (OSError, subprocess.TimeoutExpired):
                pass
    return '7zip', sevenzip_path()


def safe_path(name):
    """Reject ambiguous names on both Windows and POSIX, before any writes."""
    name = name.replace('\\', '/')
    if not name or any(ord(c) < 32 for c in name) or ':' in name:
        raise ValueError(f'Caminho interno inseguro: {name!r}')
    path = PureWindowsPath(name)
    parts = name.rstrip('/').split('/')
    if path.drive or path.root or any(p in ('', '.', '..') for p in parts):
        raise ValueError(f'Caminho interno inseguro: {name!r}')
    for part in parts:
        if part.endswith((' ', '.')) or any(c in part for c in '*?<>|"'):
            raise ValueError(f'Caminho interno ambíguo: {name!r}')
        if part.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *('COM'+str(i) for i in range(10)), *('LPT'+str(i) for i in range(10))}:
            raise ValueError(f'Nome reservado: {name!r}')
    return '/'.join(parts)


def parse_manifest(output):
    marker = '----------\n'
    if marker not in output:
        raise ValueError('Manifesto do arquivo não reconhecido.')
    header, records = output.split(marker, 1)
    if '\nType = 7z\n' not in '\n' + header:
        raise ValueError('O conteúdo precisa ser um arquivo 7z válido.')
    entries = []
    seen = set()
    for block in records.strip().split('\n\n'):
        fields = {}
        for line in block.splitlines():
            if ' = ' not in line:
                raise ValueError('Manifesto ambíguo ou malformado.')
            key, value = line.split(' = ', 1)
            if key in fields:
                raise ValueError('Campo duplicado no manifesto.')
            fields[key] = value
        name = safe_path(fields.get('Path', ''))
        if name.casefold() in seen:
            raise ValueError('Entradas duplicadas no arquivo.')
        seen.add(name.casefold())
        attrs = fields.get('Attributes', '')
        if any('link' in k.lower() or 'reparse' in k.lower() for k in fields):
            raise ValueError('Links não são permitidos.')
        if re.search(r'(?:^|\s)l[rwx-]', attrs) or fields.get('Encrypted') == '+':
            raise ValueError('Links ou entradas criptografadas não são permitidos.')
        folder = fields.get('Folder') == '+' or attrs.startswith('D')
        size = int(fields.get('Size', '-1'))
        if size < 0 or (folder and size != 0):
            raise ValueError('Tamanho inválido no manifesto.')
        if not folder and Path(name).suffix.lower() not in ('.vbox', '.vdi'):
            raise ValueError('A imagem deve conter somente diretórios, .vbox e .vdi.')
        entries.append((name, size, folder))
    if not entries or len(entries) > MAX_ENTRIES or sum(e[1] for e in entries) > MAX_BYTES:
        raise ValueError('Imagem excede os limites de entradas ou tamanho (128 GiB).')
    files = {n.casefold() for n, _, d in entries if not d}
    for name, _, _ in entries:
        if any('/'.join(name.split('/')[:i]).casefold() in files for i in range(1, len(name.split('/')))):
            raise ValueError('Conflito entre arquivo e diretório.')
    return entries


def inspect_archive(image):
    with image.open('rb') as source:
        if source.read(6) != b'7z\xbc\xaf\x27\x1c':
            raise ValueError('Assinatura 7z inválida.')
    try:
        cp = subprocess.run([sevenzip_path(), 'l', '-slt', '-sccUTF-8', '-p-', '--', str(image.resolve())],
                            capture_output=True, text=True, encoding='utf-8', errors='strict', timeout=60)
    except (OSError, UnicodeError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError('Falha ou timeout ao validar o arquivo 7z.') from exc
    if cp.returncode:
        raise ValueError('Arquivo 7z inválido, corrompido ou protegido por senha.')
    return parse_manifest(cp.stdout.replace('\r\n', '\n'))


def stream_entry(command, target, expected, timeout=900):
    """Never let archive tools choose output paths; bound streamed bytes and time."""
    with target.open('xb') as output, tempfile.TemporaryFile() as errors:
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors, stdin=subprocess.DEVNULL) as proc:
            # Reader thread permits timeout even if the child stops producing output.
            import threading
            failures = []
            def copy():
                try:
                    total = 0
                    while chunk := proc.stdout.read(1024 * 1024):
                        total += len(chunk)
                        if total > expected:
                            raise ValueError('Extração excedeu o tamanho declarado.')
                        output.write(chunk)
                    if total != expected:
                        raise ValueError('Extração incompleta: tamanho diferente do manifesto.')
                except BaseException as exc:
                    failures.append(exc)
                    proc.kill()
            reader = threading.Thread(target=copy, daemon=True)
            reader.start()
            try:
                proc.wait(timeout=timeout)
            except BaseException:
                proc.kill()
                proc.wait()
                reader.join()
                raise
            reader.join(timeout=5)
            if reader.is_alive():
                raise RuntimeError('A leitura da extração não terminou.')
            if failures:
                raise failures[0]
            if proc.returncode:
                raise RuntimeError(f'Extrator falhou (código {proc.returncode}).')


def extract_archive(image, destination):
    entries = inspect_archive(image)
    kind, executable = find_extractor()
    ancestor = destination.parent
    while not ancestor.exists():
        ancestor = ancestor.parent
    required = sum(size for _, size, _ in entries) + 512 * 1024**2
    if shutil.disk_usage(ancestor).free < required:
        raise ValueError(f'Espaço insuficiente: necessários {required} bytes, incluindo margem.')
    if destination.exists():
        raise ValueError('A pasta de destino já existe.')
    destination.mkdir(parents=True, exist_ok=False)
    print(f'Extrator: {kind} ({executable}). Espaço estimado: {required} bytes.')
    try:
        for name, size, folder in entries:
            target = destination.joinpath(*name.split('/'))
            if folder:
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if kind == 'tar':
                command = [executable, '-xOf', str(image.resolve()), '--', name]
            else:
                command = [executable, 'x', '-so', '-spd', '-p-', '--', str(image.resolve()), name]
            stream_entry(command, target, size)
    except BaseException:
        # Only this newly created disposable destination is removed, never the source.
        shutil.rmtree(destination)
        raise
