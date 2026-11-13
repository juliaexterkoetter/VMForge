"""Accessible, text-only CLI for VMForge."""
import argparse
import sys

from .providers.virtualbox import VirtualBox, VMError
from .wizard import create_wizard

from . import __version__ as VERSION


def check():
    print('VMForge - Verificacao de requisitos')
    print(f'Python: {sys.version.split()[0]}')
    try:
        vb = VirtualBox()
        print(f'VirtualBox: INSTALADO ({vb.version()})')
        print(f'Caminho: {vb.binary}')
        return 0
    except VMError as exc:
        print(f'VirtualBox: INDISPONIVEL. {exc}', file=sys.stderr)
        return 1


def main(argv=None):
    parser = argparse.ArgumentParser(prog='vmforge', description='VMForge - Virtual Machine Automation Toolkit')
    parser.add_argument('--version', action='version', version='VMForge ' + VERSION)
    subs = parser.add_subparsers(dest='action')
    subs.add_parser('check', help='Verificar Python e VirtualBox')
    subs.add_parser('list', help='Listar máquinas virtuais')
    for action, description in [('status', 'Consultar status da VM'), ('start', 'Iniciar VM em segundo plano'), ('stop', 'Solicitar desligamento ACPI'), ('snapshot', 'Criar snapshot com VM desligada')]:
        sub = subs.add_parser(action, help=description)
        sub.add_argument('name', help='Nome ou UUID da VM')
        if action == 'snapshot':
            sub.add_argument('title', help='Nome do snapshot')
    create = subs.add_parser('create', help='Assistente de criação de máquina virtual (Kali/VirtualBox)')
    create.add_argument('--dry-run', action='store_true', help='Mostrar plano sem modificar arquivos ou VMs')
    args = parser.parse_args(argv)
    try:
        if args.action is None:
            print('VMForge - Menu principal')
            print('1. Criar máquina virtual\n2. Listar máquinas virtuais\n3. Verificar requisitos\n0. Sair')
            choice = input('Escolha: ').strip()
            return {'1': lambda: create_wizard(), '2': lambda: main(['list']), '3': lambda: main(['check']), '0': lambda: 0}.get(choice, lambda: 2)()
        if args.action == 'check':
            return check()
        if args.action == 'create':
            return create_wizard(dry_run=args.dry_run)
        vb = VirtualBox()
        if args.action == 'list':
            vms = vb.list_vms()
            for vm in vms:
                print(f"Nome: {vm['name']}\nUUID: {vm['uuid']}")
            if not vms:
                print('Nenhuma VM registrada.')
        elif args.action == 'status':
            print(f'Maquina: {args.name}\nEstado: {vb.status(args.name)}')
        elif args.action == 'start':
            print(vb.start(args.name))
        elif args.action == 'stop':
            from .wizard import yes
            identity = vb.require_writable(args.name)
            if not yes(f'Autoriza solicitar desligamento da VM {identity}?'):
                return 0
            print(vb.shutdown(identity))
        elif args.action == 'snapshot':
            from .wizard import yes
            identity = vb.require_writable(args.name)
            if not yes(f'Autoriza criar o snapshot {args.title} na VM {identity}?'):
                return 0
            print(vb.snapshot(identity, args.title))
        return 0
    except (ValueError, VMError, RuntimeError, OSError, EOFError, KeyboardInterrupt) as exc:
        print(f'Erro: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
