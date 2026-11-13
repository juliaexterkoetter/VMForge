"""Wrapper for VBoxManage; never uses shell=True."""
import os
import re
import shutil
import subprocess
from pathlib import Path
from ..appliance import canonical_uuid, validate_appliance
from ..protection import load_protection, require_available_port


class VMError(RuntimeError):
    pass


def find_vboxmanage():
    path = shutil.which('VBoxManage') or shutil.which('VBoxManage.exe')
    if path:
        return Path(path)
    if os.name == 'nt':
        for root in (os.environ.get('VBOX_MSI_INSTALL_PATH'), os.environ.get('ProgramFiles'), os.environ.get('ProgramFiles(x86)')):
            if not root:
                continue
            for path in (Path(root) / 'VBoxManage.exe', Path(root) / 'Oracle' / 'VirtualBox' / 'VBoxManage.exe'):
                if path.is_file():
                    return path
    return None


class VirtualBox:
    def __init__(self, binary=None):
        self.binary = Path(binary) if binary else find_vboxmanage()
        if not self.binary:
            raise VMError('VBoxManage não encontrado. Instale o Oracle VirtualBox.')

    def run(self, *args, timeout=90):
        if not args:
            raise VMError('Comando vazio.')
        args = list(args)
        action = args[0]
        if action in ('modifyvm', 'startvm', 'controlvm', 'snapshot', 'guestcontrol'):
            args[1] = self.require_writable(args[1])
        elif action == 'registervm':
            self.check_registration(args[1])
        elif action not in ('--version', 'list', 'showvminfo'):
            raise VMError('Operação não autorizada pelo provedor VMForge.')
        cmd = [str(self.binary), *map(str, args)]
        try:
            cp = subprocess.run(cmd, capture_output=True, text=True, errors='replace', timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise VMError(f'Falha ao executar VBoxManage: {exc}') from exc
        if cp.returncode:
            raise VMError((cp.stderr or cp.stdout or 'Erro desconhecido do VirtualBox').strip())
        return cp.stdout.strip()

    def require_writable(self, target):
        """Bloqueia alterações em máquinas protegidas."""
        try:
            protection = load_protection()
            target = str(target)

            if protection.protects_vm(name=target):
                raise VMError("Máquina virtual protegida.")

            try:
                supplied_uuid = canonical_uuid(target)
            except ValueError:
                supplied_uuid = None

            if supplied_uuid and protection.protects_vm(
                uuid_value=supplied_uuid
            ):
                raise VMError("UUID protegido.")

            info = self.info(target)
            identity = canonical_uuid(info.get("UUID"))

            if protection.protects_vm(
                uuid_value=identity,
                name=info.get("name")
            ):
                raise VMError("Máquina virtual protegida.")

            return identity

        except ValueError as exc:
            raise VMError(str(exc)) from exc

    def check_registration(self, path):
        try:
            appliance = validate_appliance(path)
        except (ValueError, OSError) as exc:
            raise VMError(str(exc)) from exc
        for existing in self.list_vms():
            if canonical_uuid(existing['uuid']) == appliance['uuid'] or existing['name'].casefold() == appliance['name'].casefold():
                raise VMError('Nome ou UUID já registrado. Nenhuma VM existente foi alterada.')
        media = self.run('list', 'hdds')
        if appliance['disk_uuid'].lower() in media.lower():
            raise VMError('UUID de disco já registrado; use uma imagem independente.')
        return appliance

    def version(self):
        return self.run('--version')

    def list_vms(self):
        output = []
        for line in self.run('list', 'vms').splitlines():
            match = re.fullmatch(r'"(.*)" \{([0-9a-fA-F-]+)\}', line.strip())
            if match:
                output.append({'name': match.group(1), 'uuid': match.group(2)})
        return output

    def info(self, name):
        data = {}
        for line in self.run('showvminfo', name, '--machinereadable').splitlines():
            if '=' in line:
                key, value = line.split('=', 1)
                data[key] = value.strip('"')
        return data

    def status(self, name):
        return self.info(name).get('VMState', 'unknown')

    def register(self, path):
        return self.run('registervm', path)

    def configure(self, name, ram, cpus, port, network='nat'):
        if self.status(name) != 'poweroff':
            raise VMError('A VM precisa estar desligada para configurar recursos.')
        info = self.info(name)
        if 'ssh,tcp,' in '\n'.join(info.values()) or 'Forwarding(0)' in info:
            # Only the freshly imported VM should be configured by the wizard.
            raise VMError('A VM já possui redirecionamento de portas; a configuração existente será preservada.')
        try:
            require_available_port(port)
        except ValueError as exc:
            raise VMError(str(exc)) from exc
        if network not in ('nat', 'none') or not 1024 <= ram <= 131072 or not 1 <= cpus <= 64 or not 1024 <= port <= 65535:
            raise VMError('Configuração de recursos ou rede inválida.')
        options = ['--memory', ram, '--cpus', cpus, '--nic1', network]
        for index in range(2, 9):
            options.extend([f'--nic{index}', 'none'])
        if network == 'nat':
            options.extend(['--nat-pf1', f'vmforge-ssh,tcp,127.0.0.1,{port},,22'])
        self.run('modifyvm', name, *options)

    def start(self, name):
        state = self.status(name)
        if state == 'running':
            return 'A máquina já está ligada.'
        if state != 'poweroff':
            raise VMError(f'Não é possível iniciar a VM no estado {state}.')
        return self.run('startvm', name, '--type', 'headless', timeout=150)

    def shutdown(self, name):
        if self.status(name) != 'running':
            raise VMError('A máquina não está em execução.')
        self.run('controlvm', name, 'acpipowerbutton')
        return 'Desligamento solicitado ao sistema convidado.'

    def snapshot(self, name, title):
        if self.status(name) != 'poweroff':
            raise VMError('Desligue a VM antes de criar este snapshot.')
        return self.run('snapshot', name, 'take', title, '--description', 'Preparada pelo VMForge', timeout=300)
