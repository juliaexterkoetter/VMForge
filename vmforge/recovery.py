"""Retoma imagem ja extraida; descarte restrito de VMs criadas pelo VMForge.

Nunca usa a VM original como fonte de escrita; somente arquivos previamente extraidos.
"""
import argparse
import os
import re
import subprocess
from pathlib import Path
from .appliance import canonical_uuid, validate_appliance
from .protection import load_protection, require_unprotected, require_available_port
from .providers.virtualbox import VirtualBox, VMError
from .wizard import CreationPlan, execute_plan, validate_recovery_plan, yes
from .config import Settings


def _no_links(path):
    path = Path(path).absolute()
    node = path
    while True:
        if node.is_symlink() or (hasattr(node, 'is_junction') and node.is_junction()):
            raise ValueError('Caminho contendo link simbolico ou junction: operacao bloqueada.')
        if node.parent == node:
            break
        node = node.parent


def _check_copy(path, destination, expected_uuid=None, expected_disk_uuid=None):
    path, destination = Path(path).absolute(), Path(destination).absolute()
    _no_links(path)
    _no_links(destination)
    if not path.is_relative_to(destination) or path == destination:
        raise ValueError('O arquivo .vbox precisa estar dentro do destino exclusivo de teste.')
    if path.suffix.lower() != '.vbox' or path.stat().st_nlink != 1:
        raise ValueError('Arquivo .vbox nao independente.')
    # Avoid recovery of a directory containing unknown files / additional images.
    for child in destination.rglob('*'):
        if child.is_symlink() or (hasattr(child, 'is_junction') and child.is_junction()):
            raise ValueError('Copia contem links ou junctions: operacao bloqueada.')
    vboxes = list(destination.rglob('*.vbox'))
    vdis = list(destination.rglob('*.vdi'))
    if len(vboxes) != 1 or len(vdis) != 1 or vboxes[0].resolve() != path.resolve():
        raise ValueError('Destino ambiguo: esperados exatamente um .vbox e um .vdi.')
    app = validate_appliance(path, template=True)
    if app['disk_path'].stat().st_nlink != 1:
        raise ValueError('Disco com hard links: operacao bloqueada.')
    if expected_uuid and app['uuid'] != canonical_uuid(expected_uuid):
        raise ValueError('UUID da copia diferente do UUID esperado.')
    if expected_disk_uuid and app['disk_uuid'] != canonical_uuid(expected_disk_uuid):
        raise ValueError('UUID do disco diferente do esperado.')
    require_unprotected(uuid_value=app['uuid'])
    if app['disk_path'].resolve() != vdis[0].resolve():
        raise ValueError('VDI inesperado.')
    return app


def recover_main(argv=None):
    parser = argparse.ArgumentParser(prog='vmforge recover')
    parser.add_argument('--vbox', required=True)
    parser.add_argument('--destination', required=True)
    parser.add_argument('--expected-uuid', required=True)
    parser.add_argument('--expected-disk-uuid', required=True)
    parser.add_argument('--name', required=True)
    parser.add_argument('--ram', type=int, default=2048)
    parser.add_argument('--cpus', type=int, default=2)
    parser.add_argument('--port', type=int, default=2224)
    parser.add_argument('--dry-run', action='store_true')
    opts = parser.parse_args(argv)
    path = Path(opts.vbox)
    dest = Path(opts.destination)
    app = _check_copy(path, dest, opts.expected_uuid, opts.expected_disk_uuid)
    vb = VirtualBox()
    plan = CreationPlan(Settings(path, dest, opts.ram, opts.cpus, opts.port), opts.name,
                        network='nat', start=True, provision=True,
                        folders=False, upgrade=False, snapshot=True, keep_running=True)
    validate_recovery_plan(plan, vb, path)
    print('RECUPERACAO - PLANO')
    print(f'Arquivo extraido (sem reextrair): {path}')
    print(f'UUID copia: {app["uuid"]}; VDI: {app["disk_uuid"]}')
    print(f'Nome final: {plan.name}; RAM: {plan.settings.ram} MB; CPUs: {plan.settings.cpus}; SSH: {plan.settings.port}')
    print('Apenas copia: renomear, registrar, configurar, iniciar, provisionar SSH, snapshot e religar.')
    if opts.dry_run:
        print('SIMULACAO: nenhum arquivo ou VM modificado.')
        return 0
    if not yes('Autoriza registrar e configurar ESTA COPIA de teste?', False):
        print('Cancelado sem alteracoes.')
        return 0
    return execute_plan(plan, vb, prepared_path=path)


def _norm_cfg_path(raw):
    return str(Path(raw).resolve()).casefold()


def purge_main(argv=None):
    parser = argparse.ArgumentParser(prog='vmforge purge-test')
    parser.add_argument('--uuid', required=True)
    parser.add_argument('--vbox', required=True)
    parser.add_argument('--test-root', required=True)
    args = parser.parse_args(argv)
    target = canonical_uuid(args.uuid)
    path = Path(args.vbox).resolve()
    root = Path(args.test_root).resolve()
    _no_links(path)
    _no_links(root)
    if not path.is_relative_to(root) or path == root:
        raise ValueError('VM fora da pasta EXCLUSIVA de testes: exclusao bloqueada.')
    vb = VirtualBox()
    writable = vb.require_writable(target)
    if writable != target:
        raise ValueError('UUID de destino nao corresponde ao registrado.')
    if not path.is_file():
        raise ValueError('O .vbox esperado nao existe.')
    info = vb.info(target)
    cfg = info.get('CfgFile', '')
    if not info.get('name', '').startswith('VMForge-'):
        raise ValueError('Somente VMs com nome VMForge- podem ser descartadas neste comando.')
    if not cfg or _norm_cfg_path(cfg) != _norm_cfg_path(path):
        raise ValueError('O caminho registrado no VirtualBox nao corresponde ao .vbox informado.')
    if vb.status(target) != 'poweroff':
        raise ValueError('A VM precisa estar DESLIGADA. Desligue pelo convidado; nenhuma parada forcada sera feita.')
    if load_protection().protects_vm(uuid_value=target, name=info.get('name')):
        raise ValueError('Maquina protegida; exclusao proibida.')
    print(f'ATENCAO: sera excluida a VM {info.get("name")} UUID {target} com os discos e snapshots registrados.')
    print(f'Caminho da configuracao: {cfg}')
    typed = input(f'Para excluir, digite EXCLUIR {target}: ').strip()
    if typed != f'EXCLUIR {target}':
        print('Exclusao cancelada.')
        return 0
    # Controlled exception: provider intentionally forbids unregistervm.
    cp = subprocess.run([str(vb.binary), 'unregistervm', target, '--delete'],
                        capture_output=True, text=True, errors='replace', timeout=600)
    if cp.returncode != 0:
        raise VMError((cp.stderr or cp.stdout or 'Falha ao excluir VM').strip())
    print('VirtualBox confirmou unregistervm --delete. Confira os arquivos remanescentes manualmente.')
    return 0
