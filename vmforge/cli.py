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
    subs.add_parser('import-disk', help='Importar disco VMDK para uma VM nova')
    subs.add_parser('list', help='Listar máquinas virtuais')
    for action, description in [('status', 'Consultar status da VM'), ('start', 'Iniciar VM em segundo plano'), ('stop', 'Solicitar desligamento ACPI')]:
        sub = subs.add_parser(action, help=description)
        sub.add_argument('name', help='Nome ou UUID da VM')
    lab = subs.add_parser('lab', help='Snapshots e diagnostico de uma VM')
    lab_subs = lab.add_subparsers(dest='lab_action', required=True)
    for commands in (subs, lab_subs):
        for action in ('snapshot', 'restore', 'diagnose'):
            sub = commands.add_parser(action, help=f'{action} de uma VM de laboratorio')
            sub.add_argument('name', help='Nome ou UUID da VM')
            if action == 'snapshot':
                sub.add_argument('title', help='Nome do snapshot')
            elif action == 'restore':
                sub.add_argument('snapshot_uuid', help='UUID do snapshot a restaurar')
    create = subs.add_parser('create', help='Assistente de criação de máquina virtual (Kali/VirtualBox)')
    create.add_argument('--dry-run', action='store_true', help='Mostrar plano sem modificar arquivos ou VMs')
    subs.add_parser('recover', help='Recuperar VM extraida com UUIDs validados')
    subs.add_parser('purge-test', help='Excluir VM de teste registrada com confirmacao forte')
    subs.add_parser('resume-provision', help='Retomar SSH de VM de teste ja registrada')
    # Forward recovery-specific options without argparse consuming them.
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == 'lab' and (len(argv) < 2 or argv[1] not in ('snapshot', 'restore', 'diagnose')):
        from .lab import main as lab_main
        return lab_main(argv[1:])
    if argv and argv[0] in ('recover', 'purge-test', 'resume-provision'):
        from .recovery import recover_main, purge_main
        try:
            if argv[0] == 'resume-provision':
                from .resume import resume_main
                return resume_main(argv[1:])
            return (recover_main if argv[0] == 'recover' else purge_main)(argv[1:])
        except (ValueError, VMError, RuntimeError, OSError, EOFError, KeyboardInterrupt) as exc:
            print(f'Erro ({type(exc).__name__}): {str(exc) or chr(91) + 'sem detalhes; consulte a etapa registrada' + chr(93)}', file=sys.stderr)
            return 1
    if argv and argv[0] == 'import-disk':
        from .import_disk import main as import_disk_main
        return import_disk_main(argv[1:])
    args = parser.parse_args(argv)
    if args.action == 'lab':
        args.action = args.lab_action
    try:
        if args.action is None:
            print('VMForge - Menu principal')
            print('1. Criar máquina virtual\n2. Listar máquinas virtuais\n3. Verificar requisitos\n0. Sair')
            actions = {'1': lambda: create_wizard(), '2': lambda: main(['list']), '3': lambda: main(['check']), '0': lambda: 0}
            while True:
                choice = input('Escolha: ').strip()
                if choice in actions:
                    return actions[choice]()
                print('Opção inválida. Digite 1, 2, 3 ou 0 para sair.')
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
        elif args.action == 'diagnose':
            import json
            print(json.dumps(vb.diagnose(args.name), ensure_ascii=False, indent=2))
        elif args.action in ('snapshot', 'restore'):
            identity = vb.require_writable(args.name)
            if args.action == 'restore':
                from .appliance import canonical_uuid
                args.snapshot_uuid = canonical_uuid(args.snapshot_uuid)
                print('AVISO: restaurar causa perda do estado atual da VM e das alteracoes posteriores ao snapshot.')
                print(f'Snapshot de destino: {args.snapshot_uuid}')
            print(f'Operacao: {args.action}. VM: {identity}. A VM deve estar desligada; nao sera desligada automaticamente.')
            if input('Digite o UUID completo da VM para confirmar (ou Enter para cancelar): ').strip() != identity:
                print('Operacao cancelada. Nenhuma alteracao solicitada.')
                return 0
            if args.action == 'restore':
                vb.restore(identity, args.snapshot_uuid)
                print('Restore concluido.')
            else:
                vb.snapshot(identity, args.title)
                print('Snapshot criado.')
        return 0
    except (ValueError, VMError, RuntimeError, OSError, EOFError, KeyboardInterrupt) as exc:
        print(f'Erro ({type(exc).__name__}): {str(exc) or chr(91) + 'sem detalhes; consulte a etapa registrada' + chr(93)}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
