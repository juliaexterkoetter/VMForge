"""Import a trusted VMDK as a NEW isolated VirtualBox VM.

Run with python -m vmforge.import_disk. Safe dry-run is the default.
Does not modify or unregister existing VMs or the source VMDK.
"""
import argparse
import hashlib
import shutil
import struct
import uuid
import xml.etree.ElementTree as ET
import re
import subprocess
import sys
from pathlib import Path

from .providers.virtualbox import VirtualBox, VMError
from .protection import load_protection
from .appliance import write_appliance


_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_WINDOWS_DEVICE_NAMES = frozenset({
    'CON', 'PRN', 'AUX', 'NUL',
    *(f'COM{i}' for i in range(1, 10)),
    *(f'LPT{i}' for i in range(1, 10)),
})


class _PortugueseFormatter(argparse.HelpFormatter):
    def add_usage(self, usage, actions, groups, prefix=None):
        super().add_usage(usage, actions, groups, prefix or 'uso: ')


class _ImportParser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(2, 'Erro: argumentos inválidos ou obrigatórios ausentes. '
                  'Consulte --help para opções, tipos e limites.\n')


def _call(binary, *args, timeout=300):
    try:
        p = subprocess.run([str(binary), *map(str, args)], text=True,
                           capture_output=True, encoding="utf-8",
                           errors="replace", timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VMError(f"Falha no VirtualBox: {exc}") from exc
    if p.returncode:
        raise VMError((p.stderr or p.stdout or "VBoxManage falhou").strip())
    return p.stdout.strip()


def _regular(path):
    path = Path(path).absolute()
    for part in (path, *path.parents):
        if part.is_symlink() or part.is_junction():
            raise ValueError('Links e junctions nao sao permitidos.')
    if not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError('Esperado arquivo regular sem hard links.')
    return path.resolve(strict=True)


def _digest(path):
    with _regular(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _vmdk(source):
    """Accept only standalone sparse/flat disks with local, explicit extents."""
    src = _regular(source)
    source_digest = _digest(src)
    with src.open('rb') as stream:
        header = stream.read(512)
        embedded = header[:4] == b'KDMV'
        if embedded:
            if len(header) != 512 or struct.unpack_from('<I', header, 4)[0] != 1:
                raise ValueError('Cabecalho sparse nao suportado.')
            offset, size = struct.unpack_from('<QQ', header, 28)
            if not offset or not 0 < size <= 2048 or (offset + size) * 512 > src.stat().st_size:
                raise ValueError('Descritor VMDK invalido.')
            stream.seek(offset * 512)
            raw = stream.read(size * 512).rstrip(b'\0')
        else:
            stream.seek(0)
            raw = stream.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError('Descritor VMDK grande demais.')
    try:
        descriptor = raw.decode('ascii')
    except UnicodeError as exc:
        raise ValueError('Descritor VMDK invalido.') from exc
    fields, extents = {}, []
    for line in descriptor.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        extent = re.fullmatch(r'RW\s+([1-9][0-9]*)\s+(FLAT|SPARSE)\s+"([A-Za-z0-9_.-]+)"(?:\s+([0-9]+))?', line)
        if extent:
            extents.append(extent.groups())
            continue
        field = re.fullmatch(r'([A-Za-z][A-Za-z0-9_.]*)\s*=\s*(?:"([^"\r\n]*)"|([A-Za-z0-9]+))', line)
        if not field or field[1] in fields:
            raise ValueError('Linha VMDK nao suportada ou duplicada.')
        key, value = field[1], field[2] if field[2] is not None else field[3]
        if key not in ('version', 'CID', 'parentCID', 'createType') and not key.startswith('ddb.'):
            raise ValueError('Dependencia ou campo VMDK nao suportado: ' + key)
        if 'parent' in key.lower():
            if key != 'parentCID':
                raise ValueError('Metadados de encadeamento nao suportados.')
        fields[key] = value
    if (fields.get('version') != '1' or fields.get('parentCID', '').lower() != 'ffffffff'
            or not re.fullmatch('[0-9a-fA-F]{8}', fields.get('CID', '')) or not extents):
        raise ValueError('VMDK invalido ou encadeado; pais/snapshots nao sao aceitos.')
    kind = fields.get('createType')
    allowed = {'monolithicSparse', 'monolithicFlat', 'twoGbMaxExtentSparse', 'twoGbMaxExtentFlat'}
    if len(extents) > 128 or sum(int(e[0]) for e in extents) * 512 > 128 * 1024**3:
        raise ValueError('Disco excede o limite de 128 extents ou 128 GiB.')
    if kind not in allowed or embedded != (kind == 'monolithicSparse'):
        raise ValueError('Tipo VMDK nao suportado (raw devices tambem sao recusados).')
    if kind.startswith('monolithic') and len(extents) != 1:
        raise ValueError('Quantidade de extents invalida.')
    files = {src: source_digest}
    seen = set()
    for sectors, mode, filename, offset in extents:
        extent = _regular(src.parent / filename)
        if extent in seen or (embedded and extent != src) or (not embedded and extent == src):
            raise ValueError('Extent repetido ou referencia circular/externa.')
        seen.add(extent)
        if mode != ('SPARSE' if kind.endswith('Sparse') else 'FLAT'):
            raise ValueError('Tipo de extent inconsistente.')
        if mode == 'FLAT':
            if offset is None or (int(offset) + int(sectors)) * 512 != extent.stat().st_size:
                raise ValueError('Extent FLAT truncado ou tamanho invalido.')
        else:
            with extent.open('rb') as stream:
                sparse = stream.read(512)
            if (offset is not None or len(sparse) != 512 or sparse[:4] != b'KDMV'
                    or struct.unpack_from('<I', sparse, 4)[0] != 1
                    or struct.unpack_from('<Q', sparse, 12)[0] != int(sectors)):
                raise ValueError('Extent SPARSE invalido.')
            if extent != src and any(struct.unpack_from('<QQ', sparse, 28)):
                raise ValueError('Descritor aninhado nao permitido.')
        if extent != src:
            files[extent] = _digest(extent)
    _unchanged(files)
    return files


def _unchanged(files):
    for path, digest in files.items():
        if _digest(path) != digest:
            raise ValueError('Origem alterada desde o planejamento: ' + str(path))


def _required_space(files):
    physical = sum(path.stat().st_size for path in files)
    logical = 0
    for path in files:
        with path.open('rb') as stream:
            header = stream.read(512)
        logical += (struct.unpack_from('<Q', header, 12)[0] * 512
                    if len(header) == 512 and header[:4] == b'KDMV'
                    else path.stat().st_size)
    return physical + logical + 512 * 1024**2


def _disable_network(config, identity, name):
    config = _regular(config)
    if config.stat().st_size > 4 * 1024 * 1024:
        raise ValueError('Configuracao grande demais.')
    raw = config.read_bytes()
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ValueError('XML inseguro.')
    root = ET.fromstring(raw)
    local = lambda e: e.tag.rsplit('}', 1)[-1]
    machines = [e for e in root.iter() if local(e) == 'Machine']
    if (len(machines) != 1 or str(uuid.UUID(machines[0].get('uuid', '').strip('{}'))) != identity
            or machines[0].get('name') != name):
        raise ValueError('Identidade inesperada na configuracao criada.')
    machine = machines[0]
    namespace = machine.tag[:-len('Machine')]
    hardware = [e for e in machine if local(e) == 'Hardware']
    if len(hardware) != 1:
        raise ValueError('Hardware ausente ou ambiguo.')
    networks = [e for e in hardware[0] if local(e) == 'Network']
    if len(networks) > 1:
        raise ValueError('Rede ambigua.')
    network = networks[0] if networks else ET.SubElement(hardware[0], namespace + 'Network')
    # Explicit disabled slots avoid relying on VirtualBox defaults, even if omitted.
    for child in list(network):
        network.remove(child)
    for slot in range(8):
        ET.SubElement(network, namespace + 'Adapter', slot=str(slot), enabled='false')
    write_appliance(ET.ElementTree(root), config)


def _independent_vdi(path):
    with _regular(path).open('rb') as stream:
        header = stream.read(512)
    if (len(header) < 456 or struct.unpack_from('<I', header, 64)[0] != 0xbeda107f
            or struct.unpack_from('<I', header, 68)[0] != 0x00010001
            or struct.unpack_from('<I', header, 76)[0] not in (1, 2)
            or not any(header[392:408]) or any(header[424:456])):
        raise ValueError('Clone VDI invalido ou dependente de outro disco.')


def plan(source, name, basefolder, hostonly, ram=512, cpus=1, vb=None):
    """Validate safely and return an execution plan; never mutates."""
    vb = vb or VirtualBox()
    protection = load_protection()  # fail closed if missing/invalid
    if not _NAME.fullmatch(name) or name in ('.', '..'):
        raise ValueError("Nome inválido (use letras, números, ponto, hífen ou sublinhado).")
    # The VM name becomes both a directory and a disk filename, including on Windows.
    if name.endswith('.') or name.split('.')[0].upper() in _WINDOWS_DEVICE_NAMES:
        raise ValueError("Nome inválido para Windows: não use nomes de dispositivo reservados ou ponto final.")
    try:
        name_uuid = str(uuid.UUID(name))
    except ValueError:
        name_uuid = None
    if protection.protects_vm(uuid_value=name_uuid, name=name):
        raise ValueError("Nome de VM protegido.")
    if not (256 <= ram <= 131072 and 1 <= cpus <= 64):
        raise ValueError("RAM ou CPUs fora dos limites.")
    raw_source = Path(source).expanduser()
    if raw_source.is_symlink():
        raise ValueError("Links simbólicos não são aceitos como fonte.")
    try:
        src = _regular(raw_source)
    except (OSError, RuntimeError) as exc:
        raise ValueError("Disco de origem inexistente ou inacessível.") from exc
    if not src.is_file() or src.suffix.lower() != '.vmdk' or src.is_symlink():
        raise ValueError("Informe um disco .vmdk regular e confiável.")
    files = _vmdk(src)
    raw_base = Path(basefolder).expanduser().absolute()
    if any(part.is_symlink() or part.is_junction() for part in (raw_base, *raw_base.parents)):
        raise ValueError('Pasta-base com links nao permitida.')
    base = raw_base.resolve(strict=True)
    if not base.is_dir():
        raise ValueError("Pasta-base inexistente.")
    target = base / name
    if target.exists() or target.is_symlink() or target.is_junction():
        raise ValueError(f"Destino já existe, não será sobrescrito: {target}")
    required = _required_space(files)
    if shutil.disk_usage(base).free < required:
        raise ValueError(f'Espaço insuficiente: necessários pelo menos {required} bytes.')
    if any(v['name'].casefold() == name.casefold() for v in vb.list_vms()):
        raise ValueError("Já existe VM registrada com este nome.")
    if not hostonly or '\n' in hostonly or '\r' in hostonly:
        raise ValueError("Informe a interface Host-only.")
    interfaces = _call(vb.binary, 'list', 'hostonlyifs')
    names = re.findall(r'^Name:\s*(.+?)\s*$', interfaces, flags=re.MULTILINE)
    if hostonly not in names:
        raise ValueError("Interface Host-only não encontrada.")
    return {'source': src, 'files': files, 'required_bytes': required, 'name': name, 'base': base, 'target': target,
            'hostonly': hostonly, 'ram': ram, 'cpus': cpus, 'binary': vb.binary}


def execute(p):
    """Clone a private snapshot; register only after disabling default networking."""
    binary, name = p['binary'], p['name']
    vb = VirtualBox(binary)
    current = plan(p['source'], name, p['base'], p['hostonly'], p['ram'], p['cpus'], vb)
    if current['target'] != p['target'] or current['files'] != p['files']:
        raise VMError('Destino ou origem mudou desde o planejamento.')
    identity = str(uuid.uuid4())
    protection = load_protection()
    if protection.protects_vm(uuid_value=identity, name=name):
        raise VMError('Identidade protegida.')
    if any(str(uuid.UUID(v['uuid'])) == identity for v in vb.list_vms()):
        raise VMError('UUID ja registrado.')

    def guard(*, isolated=False):
        protection = load_protection()
        info = vb.info(identity)
        if (info.get('UUID', '').strip('{}').lower() != identity or info.get('name') != name
                or info.get('VMState') != 'poweroff'
                or protection.protects_vm(uuid_value=identity, name=info.get('name'))):
            raise VMError('Identidade, protecao ou estado da nova VM mudou.')
        if isolated and (info.get('nic1') != 'hostonly'
                or info.get('hostonlyadapter1') != p['hostonly']
                or any(info.get(f'nic{i}') != 'none' for i in range(2, 9))):
            raise VMError('Nao foi possivel comprovar isolamento Host-only.')
        return info

    stage = 'createvm'
    try:
        # An interrupted create cannot leave a registered VM with default NAT.
        _call(binary, 'createvm', '--name', name, '--uuid', identity, '--ostype', 'Ubuntu',
              '--basefolder', p['base'])
        config = p['target'] / (name + '.vbox')
        _disable_network(config, identity, name)
        stage = 'copia privada'
        staging = p['target'] / 'source-copy'
        staging.mkdir()
        for source, digest in p['files'].items():
            with _regular(source).open('rb') as reader, (staging / source.name).open('xb') as writer:
                while block := reader.read(1024 * 1024):
                    writer.write(block)
            if _digest(staging / source.name) != digest:
                raise ValueError('Origem mudou durante a copia.')
        _unchanged(p['files'])
        target_disk = p['target'] / (name + '.vdi')
        stage = 'clonemedium'
        _call(binary, 'clonemedium', 'disk', staging / p['source'].name, target_disk,
              '--format', 'VDI', '--variant', 'Standard', timeout=1200)
        _independent_vdi(target_disk)
        _unchanged(p['files'])
        with target_disk.open('rb') as stream:
            stream.seek(392)
            disk_uuid = str(uuid.UUID(bytes_le=stream.read(16)))
        if disk_uuid in _call(binary, 'list', 'hdds').lower():
            raise VMError('UUID do clone já registrado; estado parcial preservado.')
        stage = 'registervm'
        if load_protection().protects_vm(uuid_value=identity, name=name):
            raise VMError('Identidade protegida.')
        _call(binary, 'registervm', config)
        stage = 'modifyvm'
        guard()
        _call(binary, 'modifyvm', identity, '--memory', p['ram'], '--cpus', p['cpus'],
              '--firmware', 'bios', '--pae', 'on', '--usb-ohci', 'on',
              '--usb-ehci', 'off', '--usb-xhci', 'off',
              '--nic1', 'hostonly', '--host-only-adapter1', p['hostonly'],
              *[arg for i in range(2, 9) for arg in (f'--nic{i}', 'none')])
        guard(isolated=True)
        stage = 'storagectl'
        guard(isolated=True)
        _call(binary, 'storagectl', identity, '--name', 'SATA', '--add', 'sata', '--controller', 'IntelAhci')
        stage = 'storageattach'
        guard(isolated=True)
        _independent_vdi(target_disk)
        _call(binary, 'storageattach', identity, '--storagectl', 'SATA', '--port', '0',
              '--device', '0', '--type', 'hdd', '--medium', target_disk)
        guard(isolated=True)
    except (Exception, KeyboardInterrupt) as exc:
        raise VMError(f'Falha em {stage} da NOVA VM {name} ({identity}). Estado parcial preservado; '
                      f'inspecione antes de repetir. Erro: {exc}') from exc
    finally:
        try:
            _unchanged(p['files'])
        except (OSError, ValueError) as exc:
            raise VMError(f'Nao foi possivel comprovar origem imutavel; estado parcial preservado: {exc}') from exc
    return name


def main(argv=None):
    parser = _ImportParser(
        prog='vmforge import-disk', add_help=False,
        formatter_class=_PortugueseFormatter,
        description='Importação conservadora de VMDK para VM nova e Host-only',
        epilog='Retornos: 0 = simulação, cancelamento ou sucesso; '
               '1 = falha ou interrupção; 2 = argumentos inválidos.')
    parser._optionals.title = 'opções'
    parser.add_argument('-h', '--help', action='help', help='Mostrar esta ajuda e sair')
    parser.add_argument('--source', required=True, help='Caminho do .vmdk confiável')
    parser.add_argument('--name', required=True, help='Novo nome da VM')
    parser.add_argument('--basefolder', required=True, help='Pasta-base EXISTENTE das VMs')
    parser.add_argument('--hostonly', required=True, help='Nome da interface Host-only existente')
    parser.add_argument('--memory', type=int, default=512, help='RAM em MB, de 256 a 131072 (padrão: 512)')
    parser.add_argument('--cpus', type=int, default=1, help='Quantidade de CPUs, de 1 a 64 (padrão: 1)')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true', help='Simular sem escrita (modo padrão)')
    mode.add_argument('--execute', action='store_true', help='Executar após confirmação; sem flag só simula')
    args = parser.parse_args(argv)
    try:
        p = plan(args.source, args.name, args.basefolder, args.hostonly,
                 args.memory, args.cpus)
        print('Plano: criar NOVA VM', p['name'])
        print('Fonte VMDK (somente leitura):', p['source'])
        for source, digest in p['files'].items():
            print('SHA-256:', digest, source)
        print('Destino:', p['target'])
        print('Disco novo: clone independente VDI')
        print('Rede: Host-only', p['hostonly'], '; sem NAT, sem Bridge')
        print('RAM:', p['ram'], 'MB; CPU(s):', p['cpus'])
        if not args.execute:
            print('SIMULAÇÃO: nenhuma alteração realizada.')
            return 0
        answer = input('Digite CRIAR para autorizar: ').strip()
        if answer != 'CRIAR':
            print('Cancelado sem alterações.')
            return 0
        print('VM criada:', execute(p))
        print('A VM permanece DESLIGADA. Verifique o estado antes de iniciar.')
        return 0
    except (EOFError, KeyboardInterrupt):
        print('Importação interrompida pelo usuário. Verifique o estado antes de tentar novamente.', file=sys.stderr)
        return 1
    except (ValueError, RuntimeError, OSError) as exc:
        print('Erro:', exc, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
