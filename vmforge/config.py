"""Input validation and import helpers."""
import os
import re
import shutil
import socket
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Settings:
    image: Path
    destination: Path
    ram: int = 4096
    cpus: int = 2
    port: int = 2222


def validate(settings):
    if not settings.image.is_file() or settings.image.suffix.lower() not in ('.7z', '.vbox'):
        raise ValueError('Informe um arquivo .7z ou .vbox existente.')
    if not 1024 <= settings.ram <= 131072:
        raise ValueError('RAM fora do intervalo de 1024 a 131072 MB.')
    if not 1 <= settings.cpus <= 64:
        raise ValueError('Quantidade de CPUs fora do intervalo de 1 a 64.')
    if not 1024 <= settings.port <= 65535:
        raise ValueError('A porta SSH precisa estar entre 1024 e 65535.')
    if settings.destination.exists():
        raise ValueError('A pasta de destino ja existe. Escolha outra pasta vazia/inexistente.')
    with socket.socket() as sock:
        try:
            sock.bind(('127.0.0.1', settings.port))
        except OSError as exc:
            raise ValueError(f'Porta local {settings.port} indisponivel.') from exc
    if settings.image.suffix.lower() == '.vbox' and settings.destination.resolve() == settings.image.parent.resolve():
        raise ValueError('O destino precisa ser diferente da pasta de origem.')


def sevenzip_path():
    for cmd in ('7z', '7zz', '7za', '7z.exe'):
        found = shutil.which(cmd)
        if found:
            return found
    if os.name == 'nt':
        for root in (os.environ.get('ProgramFiles'), os.environ.get('ProgramFiles(x86)')):
            if root:
                loc = Path(root) / '7-Zip' / '7z.exe'
                if loc.is_file():
                    return str(loc)
    raise RuntimeError('7-Zip não encontrado. Instale o 7-Zip ou utilize um arquivo .vbox extraído.')


def prepare_image(settings):
    """Copy/import a trusted VirtualBox appliance. Never modify the original."""
    validate(settings)
    settings.destination.mkdir(parents=True, exist_ok=False)
    try:
        if settings.image.suffix.lower() == '.7z':
            sevenzip = sevenzip_path()
            cp = subprocess.run([sevenzip, 'x', '-y', str(settings.image.resolve()), '-o' + str(settings.destination.resolve())], capture_output=True, text=True, errors='replace', timeout=900)
            if cp.returncode:
                raise RuntimeError((cp.stderr or cp.stdout)[-1000:])
        else:
            shutil.copytree(settings.image.parent, settings.destination, dirs_exist_ok=True)
        matches = list(settings.destination.rglob('*.vbox'))
        if len(matches) != 1:
            raise RuntimeError(f'Esperado exatamente um arquivo .vbox; encontrados: {len(matches)}.')
        # Refuse unexpected guest images and avoid accidentally configuring another OS.
        if not re.search(r'kali-linux', matches[0].name, re.I):
            raise RuntimeError('Esta versao aceita apenas imagens oficiais do Kali Linux VirtualBox.')
        return matches[0]
    except Exception:
        # Retain the directory on failure so the user can inspect the files.
        raise
