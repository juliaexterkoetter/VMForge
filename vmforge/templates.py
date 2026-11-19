"""Declarative templates for the supported isolated 7z laboratory workflow."""
import argparse
import json

from .lab import fields, label


CATALOG = {
    'linux-basico': ['linux'],
    'kali-estudos': ['kali'],
    'dois-linux': ['linux-a', 'linux-b'],
    'testes-rede': ['cliente', 'servidor'],
    'desenvolvimento': ['app', 'banco'],
}


def validate(data):
    fields(data, ('version', 'name', 'vms'))
    if type(data['version']) is not int or data['version'] != 1:
        raise ValueError('Versão de template inválida.')
    label(data['name'])
    if not isinstance(data['vms'], list) or not 1 <= len(data['vms']) <= 32:
        raise ValueError('Template precisa conter de 1 a 32 máquinas.')
    seen = set()
    for vm in data['vms']:
        fields(vm, ('name', 'image'), ('ram', 'cpus'))
        name = label(vm['name']).casefold()
        if name in seen:
            raise ValueError('Nome duplicado no template.')
        seen.add(name)
        if not isinstance(vm['image'], str) or not vm['image'].lower().endswith('.7z'):
            raise ValueError('Template requer imagem .7z local.')
        for key, default, lower, upper in (('ram', 4096, 1024, 131072), ('cpus', 2, 1, 64)):
            value = vm.get(key, default)
            if type(value) is not int or not lower <= value <= upper:
                raise ValueError('Recursos inválidos no template.')
    return data


def main(argv=None):
    parser = argparse.ArgumentParser(prog='vmforge template', description='Templates de dados; não baixa imagens nem cria VMs.')
    subs = parser.add_subparsers(dest='action', required=True)
    subs.add_parser('list')
    show = subs.add_parser('show')
    show.add_argument('name', choices=sorted(CATALOG))
    args = parser.parse_args(argv)
    if args.action == 'list':
        print('\n'.join(sorted(CATALOG)))
    else:
        data = {'version': 1, 'name': args.name, 'vms': [
            {'name': name, 'image': f'imagens/{name}.7z', 'ram': 4096, 'cpus': 2}
            for name in CATALOG[args.name]]}
        print(json.dumps(validate(data), ensure_ascii=False, indent=2))
    return 0
