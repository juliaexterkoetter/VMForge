"""Validação conservadora de appliances antes de qualquer registro."""
from pathlib import Path
import struct
import uuid
import xml.etree.ElementTree as ET
from .extraction import safe_path

PROTECTED_UUID = '2d792251-94c7-41f0-95e5-5ebf008983b2'
PROTECTED_NAME = 'kali-linux-2026.3-virtualbox-amd64'


def canonical_uuid(value):
    try:
        return str(uuid.UUID(str(value).strip('{}')))
    except (ValueError, AttributeError) as exc:
        raise ValueError('UUID ausente ou inválido; operação bloqueada.') from exc


def validate_appliance(path):
    path = Path(path)
    if path.is_symlink() or path.stat().st_size > 4 * 1024**2:
        raise ValueError('Arquivo .vbox inválido ou grande demais.')
    raw = path.read_bytes()
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ValueError('DTD e entidades não são permitidos.')
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError('XML .vbox inválido.') from exc
    local = lambda element: element.tag.rsplit('}', 1)[-1]
    machines = [e for e in root.iter() if local(e) == 'Machine']
    if len(machines) != 1:
        raise ValueError('Esperada uma única máquina no .vbox.')
    machine = machines[0]
    machine_uuid = canonical_uuid(machine.get('uuid'))
    if machine_uuid == PROTECTED_UUID:
        raise ValueError('UUID protegido: a VM existente não pode ser importada ou alterada.')
    disks = [e for e in root.iter() if local(e) == 'HardDisk']
    if len(disks) != 1 or disks[0].get('format', '').upper() != 'VDI':
        raise ValueError('Apenas uma imagem VDI independente é suportada.')
    for element in root.iter():
        tag = local(element)
        if tag in ('Snapshot', 'SharedFolder', 'HostDrive'):
            raise ValueError(f'Recurso externo ou estado existente não suportado: {tag}.')
        for key, value in element.attrib.items():
            if key.lower() in ('location', 'src', 'path', 'hostpath', 'statefile', 'snapshotfolder', 'logfolder', 'nvram') and value:
                safe_path(value)
                if key.lower() != 'location':
                    raise ValueError(f'Referência de arquivo não suportada: {key}.')
    disk = disks[0]
    relative = safe_path(disk.get('location', ''))
    disk_path = path.parent.joinpath(*relative.split('/'))
    if disk_path.suffix.lower() != '.vdi' or disk_path.is_symlink() or not disk_path.resolve().is_relative_to(path.parent.resolve()):
        raise ValueError('Disco fora do diretório da imagem.')
    disk_uuid = canonical_uuid(disk.get('uuid'))
    if not disk_path.is_file():
        raise ValueError('Disco VDI ausente.')
    with disk_path.open('rb') as stream:
        header = stream.read(512)
    if len(header) < 400 or struct.unpack_from('<I', header, 64)[0] != 0xbeda107f:
        raise ValueError('Assinatura VDI inválida.')
    if struct.unpack_from('<I', header, 68)[0] != 0x00010001:
        raise ValueError('Versão VDI não suportada.')
    if struct.unpack_from('<I', header, 76)[0] not in (1, 2):
        raise ValueError('Discos diferenciais não são permitidos.')
    if str(uuid.UUID(bytes_le=header[392:408])) != disk_uuid:
        raise ValueError('UUID do VDI difere do manifesto .vbox.')
    # Parent/link UUIDs must be zero for an independent image.
    if any(header[424:456]):
        raise ValueError('VDI com vínculo a outro disco não é permitido.')
    for image in (e for e in root.iter() if local(e) == 'Image'):
        if canonical_uuid(image.get('uuid')) != disk_uuid:
            raise ValueError('Referência a mídia externa não permitida.')
    return {'uuid': machine_uuid, 'name': machine.get('name', ''),
            'disk_uuid': disk_uuid, 'disk_path': disk_path}
