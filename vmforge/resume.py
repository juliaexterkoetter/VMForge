"""Continue the SSH setup of one previously registered, independent test VM.

Does not extract, register, or modify another VM. Requires explicit opt-in.
"""
import argparse
import getpass
from pathlib import Path

from .appliance import canonical_uuid, validate_appliance
from .protection import load_protection
from .providers.virtualbox import VirtualBox
from .provisioners.kali import (guest_run, bootstrap_ssh, connect_ssh,
                                change_password, setup_lab)
from .wizard import wait_poweroff, yes


def verify_registered_copy(vb, uuid_value, path, disk_uuid, name):
    identity = canonical_uuid(uuid_value)
    if not name.startswith('VMForge-'):
        raise ValueError('Somente VMs de teste VMForge- podem ser retomadas.')
    if vb.require_writable(identity) != identity:
        raise ValueError('Identidade divergente; nenhuma operacao realizada.')
    path = Path(path).absolute()
    current = path
    while True:
        if current.is_symlink() or (hasattr(current, 'is_junction') and current.is_junction()):
            raise ValueError('Caminho com link ou junction: bloqueado.')
        if current.parent == current:
            break
        current = current.parent
    app = validate_appliance(path)
    if app['uuid'] != identity or app['disk_uuid'] != canonical_uuid(disk_uuid) or app['name'] != name:
        raise ValueError('Nome ou UUID da copia nao corresponde ao esperado.')
    if app['disk_path'].stat().st_nlink != 1 or path.stat().st_nlink != 1:
        raise ValueError('Arquivos com hardlinks: bloqueado.')
    info = vb.info(identity)
    # Compare Windows paths with the exact registered configuration.
    registered = info.get('CfgFile', '')
    if not registered or Path(registered.replace(chr(92) * 2, chr(92))).resolve() != path.resolve() or info.get('name') != name:
        raise ValueError('Registro do VirtualBox nao corresponde ao arquivo informado.')
    if load_protection().protects_vm(uuid_value=identity, name=name):
        raise ValueError('Maquina protegida: bloqueado.')
    if vb.status(identity) != 'running':
        raise ValueError('A VM deve estar ligada para retomar o SSH.')
    return identity


def resume_main(argv=None):
    p = argparse.ArgumentParser(prog='vmforge resume-provision')
    p.add_argument('--uuid', required=True)
    p.add_argument('--vbox', required=True)
    p.add_argument('--expected-disk-uuid', required=True)
    p.add_argument('--name', required=True)
    p.add_argument('--port', type=int, default=2224)
    p.add_argument('--dry-run', action='store_true')
    a = p.parse_args(argv)
    if not 1024 <= a.port <= 65535:
        raise ValueError('Porta fora dos limites.')
    vb = VirtualBox()
    identity = verify_registered_copy(vb, a.uuid, a.vbox, a.expected_disk_uuid, a.name)
    info = vb.info(identity)
    pf = [v for k, v in info.items() if k.startswith('Forwarding(')]
    if not any(v.split(',')[:4] == ['vmforge-ssh', 'tcp', '127.0.0.1', str(a.port)] for v in pf):
        raise ValueError('Regra de NAT para SSH nao confere com a porta esperada.')
    print('PLANO: retomar somente o SSH da VM registrada e criar snapshot inicial.')
    print(f'Nome: {a.name}; UUID: {identity}; SSH: {a.port}; VDI: {a.expected_disk_uuid}')
    print('Nao reextrai, nao registra, nao modifica a maquina original.')
    if a.dry_run:
        print('SIMULACAO: sem alteracoes.')
        return 0
    if not yes('Autoriza instalar SSH, definir nova senha e criar snapshot nesta VM?', False):
        print('Cancelado.')
        return 0
    stage = 'entrada da nova senha'
    try:
        new = getpass.getpass('Nova senha do usuario kali (minimo 12 caracteres): ')
        confirm = getpass.getpass('Confirme a nova senha: ')
        if new != confirm or len(new) < 12 or any(c in new for c in '\r\n:'):
            raise ValueError('Senha invalida ou confirmacao diferente.')
        stage = 'disponibilidade do Guest Control'
        print('[1/5] Verificando Guest Control e autenticacao inicial...', flush=True)
        # This workflow is for an unprovisioned official Kali image whose
        # initial public password remains the default. Do not guess alternatives.
        try:
            identity_text = guest_run(vb, identity, 'kali', 'kali', '/usr/bin/id', ('-un',), timeout=45)
        except Exception as exc:
            raise RuntimeError('Guest Control indisponivel ou credencial inicial ja alterada. '
                               'Nao repetir sem investigar o estado atual.') from exc
        if identity_text.strip() != 'kali':
            raise RuntimeError('Identidade do usuario convidado inesperada.')
        stage = 'instalacao ou inicio do servidor SSH'
        print('[2/5] Preparando servidor SSH e verificando sua chave...', flush=True)
        hostkey = bootstrap_ssh(vb, identity)
        stage = 'autenticacao SSH inicial'
        print('[3/5] Validando SSH com chave do servidor verificada...', flush=True)
        client = connect_ssh(a.port, hostkey, password='kali', seconds=60)
        try:
            stage = 'alteracao da senha no Kali'
            change_password(client, 'kali', new)
        finally:
            client.close()
        stage = 'autenticacao SSH com nova senha'
        client = connect_ssh(a.port, hostkey, password=new, seconds=45)
        try:
            stdin, stdout, stderr = client.exec_command('id -un', timeout=15)
            if stdout.read().decode('utf-8', 'replace').strip() != 'kali':
                raise RuntimeError('SSH autenticado, mas usuario inesperado.')
            print('[4/5] SSH autenticado com sucesso.', flush=True)
            setup_lab(client, new, update=False, create_folders=False)
        finally:
            client.close()
        stage = 'desligamento normal'
        print('[5/5] Solicitando desligamento ACPI para snapshot...', flush=True)
        vb.shutdown(identity)
        wait_poweroff(vb, identity, seconds=180)
        stage = 'snapshot inicial'
        # No automatic replacement of existing snapshots. Snapshot creation
        # is refused by VirtualBox if the name is already used.
        vb.snapshot(identity, 'VMForge-Inicial')
        stage = 'reinicio'
        vb.start(identity)
        print('CONCLUIDO: SSH autenticado, snapshot criado e VM religada.', flush=True)
        return 0
    except Exception as exc:
        # Never echo supplied secrets or stderr that may contain credentials.
        detail = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        raise RuntimeError(f'Provisionamento interrompido em: {stage}. '
                           f'Detalhe: {detail}. VM preservada; nao repita automaticamente.') from None
