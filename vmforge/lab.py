"""Versioned multi-VM labs, with an on-disk journal and internal networking."""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import sys
import uuid
import xml.etree.ElementTree as ET

from .appliance import canonical_uuid, isolate_new_image, validate_appliance, write_appliance
from .extraction import extract_archive
from .protection import require_unprotected
from .providers.virtualbox import VirtualBox, VMError
from .recovery import _no_links


ERRORS = (ValueError, RuntimeError, OSError, EOFError, KeyboardInterrupt)


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f'Campo duplicado: {key}')
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=unique)


def fields(value, required, optional=()):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or set(required) - set(value):
        raise ValueError('Campos ausentes ou desconhecidos no documento.')


def label(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,47}', value):
        raise ValueError('Nome deve ter 1-48 caracteres: letras, numeros, _ ou -; iniciar com letra.')
    return value


def plan(path):
    """Offline validation: no provider, extraction, socket, or filesystem writes."""
    path = Path(path).resolve()
    data = read_json(path)
    fields(data, ('version', 'name', 'vms'))
    if type(data['version']) is not int or data['version'] != 1:
        raise ValueError('Versao de manifesto nao suportada; esperado 1.')
    name = label(data['name'])
    if not isinstance(data['vms'], list) or not 1 <= len(data['vms']) <= 32:
        raise ValueError('Informe entre 1 e 32 VMs.')
    nodes, seen = [], set()
    for item in data['vms']:
        fields(item, ('name', 'image'), ('ram', 'cpus'))
        node = label(item['name'])
        if node.casefold() in seen:
            raise ValueError('Nomes de VM duplicados.')
        seen.add(node.casefold())
        if not isinstance(item['image'], str) or not item['image']:
            raise ValueError('Imagem invalida.')
        image = (path.parent / item['image']).resolve()
        if image.suffix.lower() != '.7z' or not image.is_file():
            raise ValueError('Informe um arquivo .7z original existente.')
        ram, cpus = item.get('ram', 4096), item.get('cpus', 2)
        if type(ram) is not int or not 1024 <= ram <= 131072 or type(cpus) is not int or not 1 <= cpus <= 64:
            raise ValueError('Recursos invalidos: RAM 1024-131072 MB, CPUs 1-64.')
        nodes.append(dict(name=node, image=str(image), ram=ram, cpus=cpus))
    return dict(version=1, name=name, vms=nodes)


def save(path, data):
    """Replace atomically; never continue external mutations if journaling fails."""
    temp = path.with_suffix('.tmp')
    with temp.open('x', encoding='utf-8') as stream:
        json.dump(data, stream, indent=2, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


@contextmanager
def locked(directory):
    lock = directory / '.lab.lock'
    with lock.open('x', encoding='utf-8') as stream:
        stream.write(str(os.getpid()))
    try:
        yield
    finally:
        lock.unlink()


def prepare(node, directory, network, name):
    extract_archive(Path(node['image']), directory)
    paths = [p for p in directory.rglob('*') if p.is_file() and p.suffix.lower() == '.vbox']
    if len(paths) != 1:
        raise ValueError('Esperado exatamente um arquivo .vbox por VM.')
    path = paths[0]
    isolate_new_image(path, directory)
    tree = ET.parse(path)
    local = lambda e: e.tag.rsplit('}', 1)[-1]
    machine = next(e for e in tree.getroot().iter() if local(e) == 'Machine')
    machine.set('name', name)
    hardware = [e for e in machine if local(e) == 'Hardware']
    if len(hardware) != 1:
        raise ValueError('Hardware ausente ou ambiguo no appliance.')
    hardware = hardware[0]
    ns = hardware.tag[:-len('Hardware')]
    for element in list(hardware):
        if local(element) == 'Network':
            hardware.remove(element)
    net = ET.SubElement(hardware, ns + 'Network')
    adapter = ET.SubElement(net, ns + 'Adapter', slot='0', enabled='true',
                            MACAddress='080027' + uuid.uuid4().hex[:6].upper(), cable='true', type='82540EM')
    ET.SubElement(adapter, ns + 'InternalNetwork', name=network)
    write_appliance(tree, path)
    return path, validate_appliance(path)


def create(spec, directory, vb):
    directory.mkdir()  # exclusive: never reuse a partial or existing lab
    lab_id = str(uuid.uuid4())
    state = dict(version=1, name=spec['name'], uuid=lab_id,
                 network='vmforge-' + lab_id, vms=[])
    for node in spec['vms']:
        state['vms'].append(dict(name=spec['name'] + '-' + node['name'], uuid=None,
                                 disk_uuid=None, path=None, phase='preparing', error=None))
    registry = directory / 'lab.json'
    with locked(directory):
        save(registry, state)
        existing = {vm['name'].casefold() for vm in vb.list_vms()}
        for node in spec['vms']:
            name = spec['name'] + '-' + node['name']
            require_unprotected(name=name)
            if name.casefold() in existing:
                raise ValueError(f'Nome ja registrado: {name}')
        for node, entry in zip(spec['vms'], state['vms']):
            try:
                path, appliance = prepare(node, directory / node['name'], state['network'], entry['name'])
                entry.update(uuid=appliance['uuid'], disk_uuid=appliance['disk_uuid'],
                             path=str(path), phase='registering')
                save(registry, state)  # UUID survives registration timeout/partial success
                vb.register(path)
                entry['phase'] = 'configuring'
                save(registry, state)
                vb.configure_lab(entry['uuid'], node['ram'], node['cpus'], state['network'])
                verify(vb, entry, state['network'])
                entry['phase'] = 'ready'
                save(registry, state)
            except ERRORS as exc:
                entry['error'] = str(exc) or type(exc).__name__
                save(registry, state)
                raise RuntimeError(f'Criacao parcial; consulte {registry}: {entry["name"]}: {entry["error"]}') from exc
    return state


def load_state(directory):
    _no_links(directory)
    _no_links(directory / 'lab.json')
    data = read_json(directory / 'lab.json')
    fields(data, ('version', 'name', 'uuid', 'network', 'vms'))
    if type(data['version']) is not int or data['version'] != 1:
        raise ValueError('Versao do registro nao suportada.')
    label(data['name'])
    if data['network'] != 'vmforge-' + canonical_uuid(data['uuid']):
        raise ValueError('Rede do registro invalida.')
    if not isinstance(data['vms'], list) or len(data['vms']) > 32:
        raise ValueError('Registro de VMs invalido.')
    seen = set()
    for vm in data['vms']:
        fields(vm, ('name', 'uuid', 'disk_uuid', 'path', 'phase', 'error'), ('last_action', 'result'))
        if not isinstance(vm['name'], str) or not vm['name'].startswith(data['name'] + '-'):
            raise ValueError('Nome de VM invalido no registro.')
        label(vm['name'][len(data['name']) + 1:])
        if vm['phase'] not in ('preparing', 'registering', 'configuring', 'ready'):
            raise ValueError('Etapa invalida no registro.')
        if vm['uuid'] is not None:
            vm['uuid'] = canonical_uuid(vm['uuid'])
            canonical_uuid(vm['disk_uuid'])
            if vm['uuid'] in seen:
                raise ValueError('UUID duplicado no registro.')
            seen.add(vm['uuid'])
            if not isinstance(vm['path'], str) or not Path(vm['path']).resolve().is_relative_to(directory):
                raise ValueError('Arquivo da VM fora do laboratorio.')
        elif vm['phase'] != 'preparing':
            raise ValueError('UUID ausente no registro.')
    return data


def verify(vb, vm, network, *, isolated=True):
    info = vb.info(vm['uuid'])
    if canonical_uuid(info.get('UUID')) != vm['uuid'] or info.get('name') != vm['name']:
        raise ValueError('Identidade da VM diverge do registro.')
    if Path(info.get('CfgFile', '')).resolve() != Path(vm['path']).resolve():
        raise ValueError('Arquivo da VM diverge do registro.')
    if isolated and (info.get('nic1') != 'intnet' or info.get('intnet1') != network or
                     any(info.get(f'nic{i}') != 'none' for i in range(2, 9))):
        raise ValueError('Rede da VM diverge da rede isolada do laboratorio.')
    return info.get('VMState', 'unknown')


def operate(action, directory, vb):
    def run(state):
        failed = False
        for vm in state['vms']:
            try:
                if vm['uuid'] is None:
                    raise ValueError('Preparacao incompleta; UUID ainda nao registrado.')
                current = verify(vb, vm, state['network'], isolated=action == 'start')
                if action == 'status':
                    print(f'{vm["name"]}: {current}; etapa={vm["phase"]}; erro={vm["error"]}')
                    failed |= vm['phase'] != 'ready'
                    continue
                if action == 'start' and vm['phase'] != 'ready':
                    raise ValueError('Criacao incompleta; inicio bloqueado.')
                vm.update(last_action=action, result='pending')
                save(directory / 'lab.json', state)
                vb.require_writable(vm['uuid'])
                if action == 'start':
                    result = vb.start(vm['uuid'])
                elif current == 'poweroff':
                    result = 'Ja desligada.'
                else:
                    result = vb.shutdown(vm['uuid'])
                vm['result'] = str(result)
                vm['error'] = None
                print(f'{vm["name"]}: {result}')
            except ERRORS as exc:
                failed = True
                if action != 'status':
                    vm['error'] = str(exc) or type(exc).__name__
                    vm['result'] = 'failed-or-uncertain'
                print(f'{vm["name"]}: falha: {str(exc) or type(exc).__name__}', file=sys.stderr)
            if action != 'status':
                save(directory / 'lab.json', state)
            if failed and action == 'start':
                break  # do not expand a partially started lab
        return int(failed)
    if action == 'status':
        return run(load_state(directory))
    with locked(directory):
        return run(load_state(directory))


def main(argv=None):
    parser = argparse.ArgumentParser(prog='vmforge lab')
    subs = parser.add_subparsers(dest='action', required=True)
    for action in ('plan', 'create', 'start', 'status', 'stop', 'inspect', 'list'):
        sub = subs.add_parser(action)
        sub.add_argument('manifest' if action in ('plan', 'create') else 'directory', type=Path)
        if action == 'create':
            sub.add_argument('--directory', required=True, type=Path, help='Novo diretorio exclusivo do laboratorio')
        if action in ('create', 'start', 'stop'):
            sub.add_argument('--yes', action='store_true', help='Confirmar explicitamente a operacao')
    args = parser.parse_args(argv)
    try:
        if args.action in ('inspect', 'list'):
            directory = args.directory.resolve()
            if args.action == 'inspect':
                print(json.dumps(load_state(directory), ensure_ascii=False, indent=2))
            else:
                for child in sorted(directory.iterdir()):
                    if child.is_dir() and not child.is_symlink() and not child.is_junction() and (child / 'lab.json').is_file():
                        state = load_state(child.resolve())
                        print(f'{state["name"]}: {state["uuid"]}; {child}')
            return 0
        if args.action in ('plan', 'create'):
            spec = plan(args.manifest)
            print(json.dumps(spec, indent=2, ensure_ascii=False))
            print('Rede: interna exclusiva (sem NAT, bridge ou acesso ao host).')
            if args.action == 'plan':
                return 0
        _no_links(args.directory)
        directory = args.directory.resolve()
        if args.action != 'status':
            if args.action != 'create':
                state = load_state(directory)
                print('VMs: ' + ', '.join(vm['name'] for vm in state['vms']))
            print(f'Operacao: {args.action}; laboratorio: {directory}')
            if not args.yes and input('Digite SIM para confirmar: ').strip() != 'SIM':
                print('Cancelado.')
                return 0
        vb = VirtualBox()
        if args.action == 'create':
            create(spec, directory, vb)
            print(f'Laboratorio criado, VMs desligadas. Registro: {directory / "lab.json"}')
            return 0
        return operate(args.action, directory, vb)
    except ERRORS as exc:
        print(f'Erro: {str(exc) or type(exc).__name__}', file=sys.stderr)
        return 1
