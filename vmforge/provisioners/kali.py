"""Kali-specific bootstrap with VM Guest Additions and verified SSH access."""
import base64
import getpass
import hashlib
import os
import shlex
import socket
import subprocess
import tempfile
import time
from pathlib import Path


class ProvisionError(RuntimeError):
    pass


def guest_run(vbox, name, username, password, exe, args=(), timeout=120):
    """Use --passwordfile to avoid placing the *login* password in argv."""
    with tempfile.TemporaryDirectory(prefix='vmforge-') as td:
        pwfile = Path(td) / 'guest.pass'
        pwfile.write_text(password, encoding='utf-8')
        if os.name != 'nt':
            pwfile.chmod(0o600)
        return vbox.run('guestcontrol', name, 'run', '--exe', exe,
                        '--username', username, '--passwordfile', str(pwfile),
                        '--wait-stdout', '--wait-stderr', '--', *args, timeout=timeout)


def wait_guest(vbox, name, password='kali', seconds=150):
    last = ''
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            result = guest_run(vbox, name, 'kali', password, '/usr/bin/whoami')
            if 'kali' in result:
                return
        except Exception as exc:
            last = str(exc)
        time.sleep(4)
    raise ProvisionError('As Guest Additions não responderam. Verifique se a imagem é oficial. ' + last[-180:])


def bootstrap_ssh(vbox, name):
    """Only for a fresh Kali image with *public* default password 'kali'.
    The public/default secret appears in one guest shell argument; custom secrets never do.
    """
    script = "printf 'kali\\n' | sudo -S -p '' /bin/bash -c 'apt-get update -qq && apt-get install -y openssh-server >/dev/null && systemctl enable --now ssh'"
    guest_run(vbox, name, 'kali', 'kali', '/bin/bash', ('-c', script), timeout=750)
    pubkey = guest_run(vbox, name, 'kali', 'kali', '/bin/cat', ('/etc/ssh/ssh_host_ed25519_key.pub',))
    fields = pubkey.split()
    if len(fields) < 2 or fields[0] != 'ssh-ed25519':
        raise ProvisionError('Não foi possível verificar a chave SSH do Kali.')
    return base64.b64decode(fields[1])


def connect_ssh(port, hostkey, password='kali', seconds=90):
    try:
        import paramiko
    except ImportError as exc:
        raise ProvisionError('Instale a dependencia: python -m pip install -e .') from exc

    class ExactKey(paramiko.MissingHostKeyPolicy):
        def missing_host_key(self, client, hostname, key):
            if key.asbytes() != hostkey:
                raise paramiko.SSHException('Chave SSH diferente da chave obtida da VM.')

    deadline = time.monotonic() + seconds
    last = None
    while time.monotonic() < deadline:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(ExactKey())
        try:
            client.connect('127.0.0.1', port=port, username='kali', password=password,
                           allow_agent=False, look_for_keys=False, timeout=6, auth_timeout=8)
            return client
        except (OSError, paramiko.SSHException) as exc:
            client.close()
            last = exc
            time.sleep(3)
    raise ProvisionError(f'Não foi possível conectar ao SSH: {last}')


def remote_sudo(client, sudo_password, command, input_text='', timeout=900):
    """Feed credentials over SSH stdin, not through command-line process arguments."""
    stdin, stdout, stderr = client.exec_command("sudo -S -p '' " + command, timeout=timeout)
    stdin.write(sudo_password + '\n' + input_text)
    stdin.flush()
    stdin.channel.shutdown_write()
    out = stdout.read().decode('utf-8', 'replace')
    err = stderr.read().decode('utf-8', 'replace')
    code = stdout.channel.recv_exit_status()
    if code:
        raise ProvisionError(f'Comando remoto falhou (codigo {code}): {(err or out)[-450:]}')
    return out


def change_password(client, initial, new):
    if not new or '\n' in new or ':' in new:
        raise ProvisionError('Senha inválida: não pode ser vazia nem conter dois-pontos ou quebras de linha.')
    remote_sudo(client, initial, '/usr/sbin/chpasswd', 'kali:' + new + '\n')


def setup_lab(client, password, update=False, create_folders=False):
    """Apply optional lab layout and optional package updates.

    Neither task is performed without the user's opt-in.
    """
    if create_folders:
        remote_sudo(client, password, '/usr/bin/mkdir -p /home/kali/pentest-lab/scans /home/kali/pentest-lab/evidencias /home/kali/pentest-lab/notas')
        remote_sudo(client, password, '/usr/bin/chown -R kali:kali /home/kali/pentest-lab')
        print('Pastas de laboratório criadas.')
    else:
        print('Criação de pastas de laboratório ignorada.')
    if update:
        print('Atualizando pacotes. Esta etapa pode ser extensa e usa bastante espaco.')
        remote_sudo(client, password, '/usr/bin/apt-get update', timeout=1200)
        remote_sudo(client, password, '/usr/bin/env DEBIAN_FRONTEND=noninteractive /usr/bin/apt-get full-upgrade -y', timeout=7200)
    else:
        print('Atualização completa não selecionada. Você poderá executá-la posteriormente.')


def shutdown_guest(client, password):
    try:
        # shutdown typically drops the SSH channel; it is not necessarily a failure.
        stdin, _, _ = client.exec_command("sudo -S -p '' /usr/sbin/shutdown -h now", timeout=12)
        stdin.write(password + '\n')
        stdin.flush()
    except (OSError, EOFError):
        pass
