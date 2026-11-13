"""Planejamento textual e execução explícita da criação de VMs."""
import getpass
import re
import shutil
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from .config import Settings, prepare_image, validate
from .extraction import inspect_archive
from .appliance import validate_appliance, write_appliance
from .protection import load_protection, require_unprotected, require_available_port
from .providers.virtualbox import VirtualBox, VMError
from .provisioners.kali import bootstrap_ssh, change_password, connect_ssh, setup_lab, shutdown_guest, wait_guest


def ask(prompt, default):
    entered = input(f'{prompt} [{default}]: ').strip().strip('"')
    return entered or str(default)


def yes(prompt, default=False):
    suffix = 'S/n' if default else 's/N'
    while True:
        answer = input(f'{prompt} ({suffix}): ').strip().lower()
        if not answer:
            return default
        if answer in ('s', 'sim', 'y', 'yes'):
            return True
        if answer in ('n', 'não', 'nao', 'no'):
            return False
        print('Resposta inválida. Digite s para sim ou n para não.')


def escolher_modo():
    while True:
        print('\n1. Configuração básica\n2. Configuração avançada')
        escolha = input('Escolha [1]: ').strip()
        if escolha in ('', '1'):
            return 'basico'
        if escolha == '2':
            return 'avancado'
        print('Opção inválida. Digite 1 ou 2.')


def encontrar_porta_livre(inicio=2223, fim=2299):
    import socket
    protection = load_protection()
    for porta in range(inicio, fim + 1):
        if protection.reserves_port(porta):
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(('127.0.0.1', porta))
            except OSError:
                continue
            return porta
    raise ValueError('Nenhuma porta SSH disponível.')


def planejar_finalizacao(criar_snapshot, manter_ligada):
    return {'desligar': criar_snapshot or not manter_ligada,
            'snapshot': criar_snapshot, 'religar': criar_snapshot and manter_ligada}


def wait_poweroff(vbox, name, seconds=90):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if vbox.status(name) == 'poweroff':
            return
        time.sleep(3)
    raise VMError('A VM não desligou a tempo. Nenhum desligamento forçado foi realizado.')


@dataclass
class CreationPlan:
    settings: Settings
    name: str
    network: str = 'nat'
    start: bool = True
    provision: bool = True
    folders: bool = False
    upgrade: bool = False
    snapshot: bool = False
    keep_running: bool = True

    def describe(self):
        s = self.settings
        label = lambda value: 'sim' if value else 'não'
        return '\n'.join([
            'PLANO DE CRIAÇÃO', f'Imagem (somente leitura): {s.image}',
            f'Novo destino: {s.destination}', f'Nome: {self.name}',
            f'RAM: {s.ram} MB; CPUs: {s.cpus}; rede: {self.network}',
            f'Porta SSH local: {s.port}' if self.network == 'nat' else 'Rede desconectada; SSH indisponível.',
            'Validar manifesto, espaço livre, XML, VDI e conflitos de UUID.',
            'Extrair somente para pasta nova; gerar UUIDs e MACs independentes na cópia.',
            'Registrar e configurar somente a nova VM com esses identificadores.',
            f'Iniciar: {label(self.start)}; configurar SSH e trocar senha: {label(self.provision)}',
            f'Pastas de laboratório: {label(self.folders)}; atualizar pacotes: {label(self.upgrade)}',
            f'Snapshot: {label(self.snapshot)}; manter ligada: {label(self.keep_running)}',
            'Falhas posteriores ao registro preservam a VM e os arquivos para diagnóstico.',
        ])


def validate_plan(plan, vbox):
    validate(plan.settings)
    if not re.fullmatch(r'[\w .-]{1,80}', plan.name) or plan.name.endswith(('.', ' ')):
        raise ValueError('Nome inválido: use até 80 letras, números, espaços, pontos, hífens ou sublinhados.')
    require_unprotected(name=plan.name)
    require_available_port(plan.settings.port)
    if plan.network not in ('nat', 'none') or (plan.provision and (not plan.start or plan.network != 'nat')):
        raise ValueError('SSH exige início da VM e rede NAT.')
    if (plan.folders or plan.upgrade) and not plan.provision:
        raise ValueError('Pastas e atualizações exigem provisionamento SSH.')
    if plan.keep_running and not plan.start:
        raise ValueError('Não é possível manter ligada uma VM que não será iniciada.')
    entries = inspect_archive(plan.settings.image)
    if sum(not folder and name.lower().endswith('.vbox') for name, _, folder in entries) != 1:
        raise ValueError('A imagem precisa conter exatamente um .vbox.')
    if sum(not folder and name.lower().endswith('.vdi') for name, _, folder in entries) != 1:
        raise ValueError('A imagem precisa conter exatamente um .vdi.')
    required = sum(size for _, size, _ in entries) + 512 * 1024**2
    ancestor = plan.settings.destination.parent
    while not ancestor.exists():
        ancestor = ancestor.parent
    free = shutil.disk_usage(ancestor).free
    print(f'Espaço estimado com margem: {required} bytes; disponível: {free} bytes.')
    if free < required:
        raise ValueError('Espaço insuficiente para a imagem descompactada.')
    if vbox is not None:
        for existing in vbox.list_vms():
            if existing['name'].casefold() == plan.name.casefold():
                raise ValueError('Já existe uma VM com esse nome.')
            info = vbox.info(existing['uuid'])
            for key, value in info.items():
                if key.startswith('Forwarding('):
                    fields = value.split(',')
                    if len(fields) >= 4 and fields[3] == str(plan.settings.port):
                        raise ValueError('Porta SSH reservada por uma VM registrada, mesmo desligada.')


def collect_plan():
    image = Path(ask('Caminho do arquivo .7z original', '')).expanduser().resolve()
    destination = Path(ask('Nova pasta de destino', image.parent/'VMForge-Kali-Teste')).expanduser().resolve()
    name = ask('Nome da nova máquina', 'VMForge-Kali-Teste')
    mode = escolher_modo()
    port = encontrar_porta_livre()
    ram, cpus, network = 4096, 2, 'nat'
    if mode == 'avancado':
        ram = int(ask('RAM em MB', ram))
        cpus = int(ask('CPUs', cpus))
        port = int(ask('Porta SSH local', port))
        print('1. NAT (SSH somente em 127.0.0.1)\n2. Sem rede')
        selection = ask('Rede', '1')
        if selection not in ('1', '2'):
            raise ValueError('Rede inválida. Selecione 1 ou 2.')
        network = 'nat' if selection == '1' else 'none'
    start = yes('Iniciar a nova VM?', True)
    provision = start and network == 'nat' and yes('Configurar SSH e alterar a senha inicial?', True)
    folders = provision and yes('Criar pastas opcionais de laboratório?')
    upgrade = provision and yes('Atualizar todos os pacotes? Pode demorar e usar bastante espaço.')
    snapshot = yes('Criar snapshot inicial?')
    keep = start and yes('Manter a VM ligada ao finalizar?', True)
    return CreationPlan(Settings(image, destination, ram, cpus, port), name, network,
                        start, provision, folders, upgrade, snapshot, keep)


def execute_plan(plan, vbox):
    """Caller must obtain explicit confirmation after displaying the full plan."""
    password = None
    if plan.provision:
        password = getpass.getpass('Nova senha do usuário kali (mínimo de 12 caracteres): ')
        confirm = getpass.getpass('Repita a nova senha: ')
        if password != confirm or len(password) < 12 or any(c in password for c in '\r\n:'):
            raise ValueError('Senha inválida ou confirmação diferente. Nada foi criado.')
    validate_plan(plan, vbox)
    phase = 'preparação da imagem'
    try:
        path = prepare_image(plan.settings)
        appliance = validate_appliance(path)
        identity = appliance['uuid']
        tree = ET.parse(path)
        machine = next(e for e in tree.getroot().iter() if e.tag.rsplit('}', 1)[-1] == 'Machine')
        machine.set('name', plan.name)
        write_appliance(tree, path)
        phase = 'registro'
        vbox.register(path)
        # Use the exact validated UUID; never infer identity by a list difference.
        identity = vbox.require_writable(identity)
        phase = 'configuração'
        vbox.configure(identity, plan.settings.ram, plan.settings.cpus, plan.settings.port, network=plan.network)
        if plan.start:
            vbox.start(identity)
        if plan.provision:
            phase = 'provisionamento SSH'
            wait_guest(vbox, identity)
            key = bootstrap_ssh(vbox, identity)
            client = connect_ssh(plan.settings.port, key)
            try:
                change_password(client, 'kali', password)
            finally:
                client.close()
            client = connect_ssh(plan.settings.port, key, password=password)
            try:
                setup_lab(client, password, update=plan.upgrade, create_folders=plan.folders)
            finally:
                client.close()
        phase = 'finalização'
        if plan.start and (plan.snapshot or not plan.keep_running):
            vbox.shutdown(identity)
            wait_poweroff(vbox, identity, seconds=180)
        if plan.snapshot:
            vbox.snapshot(identity, 'VMForge-Inicial')
        if plan.snapshot and plan.keep_running:
            vbox.start(identity)
        print('\nCONFIGURAÇÃO CONCLUÍDA')
        print(f'Nome: {plan.name}\nUUID: {identity}\nStatus: {vbox.status(identity)}')
        print(f'Snapshot: {"VMForge-Inicial" if plan.snapshot else "não solicitado"}')
        if plan.provision:
            print(f'Acesso: ssh -p {plan.settings.port} kali@127.0.0.1')
        else:
            print('SSH não configurado. A senha original da imagem não foi alterada.')
        return 0
    except Exception as exc:
        raise RuntimeError(f'Criação não concluída na etapa {phase}: {exc}. Verifique o destino e o registro antes de tentar novamente; nenhuma VM será excluída automaticamente.') from exc


def create_wizard(dry_run=False):
    print('\nVMForge - Assistente de criação de máquina virtual')
    plan = collect_plan()
    try:
        vbox = VirtualBox()
        print(f'VirtualBox: {vbox.version()}')
    except VMError:
        if not dry_run:
            raise
        vbox = None
        print('VirtualBox indisponível: conflitos de registro não puderam ser verificados.')
    validate_plan(plan, vbox)
    print(plan.describe())
    if dry_run:
        print('SIMULAÇÃO: nenhum arquivo ou máquina virtual foi modificado. O XML e o VDI serão validados após a extração autorizada.')
        return 0
    if not yes('Autoriza executar todas as operações deste plano na NOVA máquina?', False):
        print('Operação cancelada sem alterações.')
        return 0
    return execute_plan(plan, vbox)
