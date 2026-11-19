"""Read-only inventory with explicit output fields; never dump provider data."""
import argparse
import json
import re
import sys

from .appliance import canonical_uuid
from .providers.virtualbox import VirtualBox


def collect(vb):
    report = {'version': 1, 'machines': [], 'problems': []}
    for registered in vb.list_vms():
        identity = canonical_uuid(registered['uuid'])
        try:
            item = vb.diagnose(identity)
            if item['UUID'] != identity:
                raise ValueError('Identidade retornada diverge do inventário.')
            info = vb.info(identity)
            if canonical_uuid(info.get('UUID')) != identity:
                raise ValueError('Identidade mudou durante a consulta.')
            item['networks'] = [
                {'slot': n, 'mode': info.get(f'nic{n}', 'unknown'),
                 'hostonly': info.get(f'hostonlyadapter{n}'),
                 'internal': info.get(f'intnet{n}')}
                for n in range(1, 9) if info.get(f'nic{n}', 'none') != 'none']
            # Only disk UUIDs, never arbitrary paths, guest properties or credentials.
            item['disks'] = [canonical_uuid(value) for key, value in info.items()
                             if re.fullmatch(r'.+-ImageUUID-\d+-\d+', key.strip('"'))]
            item['recommendations'] = []
            if any(net['mode'] in ('nat', 'bridged', 'natnetwork') for net in item['networks']):
                item['recommendations'].append('Há rede com acesso externo. Confira a política de isolamento antes de iniciar.')
            report['machines'].append(item)
        except (ValueError, RuntimeError, OSError):
            # Provider error text can contain paths or other private settings.
            report['problems'].append({'uuid': identity, 'message': 'Consulta incompleta; confirme registro, discos e disponibilidade do VirtualBox.'})
    return report


def render(report, output_format):
    if output_format == 'json':
        return json.dumps(report, ensure_ascii=False, indent=2)
    lines = ['# Inventário VMForge' if output_format == 'markdown' else 'Inventário VMForge']
    for item in report['machines']:
        # JSON quoting prevents terminal control characters in VM names.
        lines.append(json.dumps(item, ensure_ascii=False, sort_keys=True))
    lines.extend(json.dumps(problem, ensure_ascii=False) for problem in report['problems'])
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(prog='vmforge report', description='Inventário somente de leitura; sem credenciais ou caminhos de discos.')
    parser.add_argument('--format', choices=('text', 'json', 'markdown'), default='text')
    args = parser.parse_args(argv)
    try:
        report = collect(VirtualBox())
        print(render(report, args.format))
        return int(bool(report['problems']))
    except (ValueError, RuntimeError, OSError):
        print('Inventário indisponível. Verifique a instalação e o registro do VirtualBox.', file=sys.stderr)
        return 1
