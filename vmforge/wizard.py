"""Interactive Kali VirtualBox lab builder."""
import getpass
import re
import time
from pathlib import Path

from .config import Settings, prepare_image, validate, sevenzip_path
from .providers.virtualbox import VirtualBox, VMError
from .provisioners.kali import (
    bootstrap_ssh, change_password, connect_ssh, setup_lab,
    shutdown_guest, wait_guest,
)


def ask(prompt, default):
    entered = input(f'{prompt} [{default}]: ').strip().strip('"')
    return entered or str(default)


def yes(prompt, default=False):
    suffix = 'S/n' if default else 's/N'
    answer = input(f'{prompt} ({suffix}): ').strip().lower()
    return default if not answer else answer in ('s', 'sim', 'y', 'yes')



def escolher_modo():
    """Seleciona o modo de configuração."""

    while True:
        print("\n1. Configuração básica")
        print("2. Configuração avançada")

        escolha = input("Escolha [1]: ").strip()

        if escolha in ("", "1"):
            return "basico"

        if escolha == "2":
            return "avancado"

        print("Opção inválida. Digite 1 ou 2.")


def encontrar_porta_livre(inicio=2223, fim=2299):
    """Sugere uma porta TCP local disponível."""
    import socket

    for porta in range(inicio, fim + 1):
        with socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM
        ) as sock:
            try:
                sock.bind(("127.0.0.1", porta))
            except OSError:
                continue

            return porta

    raise ValueError("Nenhuma porta SSH disponível.")



def planejar_finalizacao(criar_snapshot, manter_ligada):
    """Define o comportamento de finalização da VM."""

    return {
        "desligar": criar_snapshot or not manter_ligada,
        "snapshot": criar_snapshot,
        "religar": criar_snapshot and manter_ligada,
    }


def wait_poweroff(vbox, name, seconds=90):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if vbox.status(name) == 'poweroff':
            return
        time.sleep(3)
    raise VMError('A VM não desligou a tempo. Nenhum desligamento forçado foi realizado.')


def create_wizard():
    print('\nVMForge - Assistente de criação de máquina virtual')
    print('Suporte inicial: Windows, Oracle VirtualBox e imagens oficiais do Kali Linux.')
    print('IMPORTANTE: não utilize uma VM já configurada ou registrada para criar uma duplicata.')
    print('Forneça um arquivo .7z original ou um .vbox de uma máquina ainda não registrada.')
    vbox = VirtualBox()
    print(f'VirtualBox: {vbox.version()}')
    image = Path(ask('Caminho do arquivo .7z ou .vbox', '')).expanduser().resolve()
    default_destination = image.parent / 'VMForge-Kali-Lab'
    destination = Path(ask('Nova pasta de destino', str(default_destination))).expanduser().resolve()
    modo = escolher_modo()
    porta_sugerida = encontrar_porta_livre()

    if modo == "basico":
        ram = 4096
        cpus = 2
        port = porta_sugerida
        print(f"Configuração básica: 4096 MB, 2 CPUs, SSH {port}.")
    else:
        ram = int(ask('RAM em MB', 4096))
        cpus = int(ask('CPUs', 2))
        port = int(ask('Porta SSH local', porta_sugerida))
    settings = Settings(image, destination, ram, cpus, port)
    validate(settings)
    print('\nResumo:')
    print(f'  Imagem: {image}\n  Destino: {destination}\n  RAM: {ram} MB\n  CPUs: {cpus}\n  SSH: 127.0.0.1:{port}')
    print('  Rede: NAT (porta SSH acessivel apenas no computador local)')
    print('  Senha inicial da imagem oficial: kali (publica e temporaria)')
    print('  A senha nova sera solicitada sem exibir caracteres.')
    print('  Se ocorrer erro, arquivos gerados permanecerao para diagnostico; nenhuma VM sera excluida.')
    if not yes('Continuar criando uma nova máquina?'):
        print('Operacao cancelada sem alteracoes.')
        return 0

    # This is a new VM, not an existing machine that may contain user data.
    before = {vm['uuid'] for vm in vbox.list_vms()}
    print('Etapa 1/8: copiando ou extraindo a imagem...')
    vboxfile = prepare_image(settings)
    print('Etapa 2/8: registrando a VM...')
    vbox.register(vboxfile)
    new = [vm for vm in vbox.list_vms() if vm['uuid'] not in before]
    if len(new) != 1:
        raise VMError('Não foi possível identificar exclusivamente a VM registrada.')
    name = new[0]['name']
    print(f'Maquina registrada: {name}')
    print('Etapa 3/8: configurando recursos e NAT SSH...')
    vbox.configure(name, ram, cpus, port)
    print('Etapa 4/8: iniciando sem janela grafica...')
    vbox.start(name)
    print('Aguardando Guest Additions...')
    wait_guest(vbox, name)
    print('Etapa 5/8: iniciando SSH no Kali...')
    ssh_key = bootstrap_ssh(vbox, name)
    client = connect_ssh(port, ssh_key)
    try:
        print('Etapa 6/8: protegendo a conta kali...')
        new_password = getpass.getpass('Digite a NOVA senha do usuário kali: ')
        confirm = getpass.getpass('Repita a nova senha: ')
        if new_password != confirm:
            raise ValueError('As senhas não conferem. A VM permanece criada; execute passwd via SSH.')
        if len(new_password) < 12:
            raise ValueError('Use uma senha com pelo menos 12 caracteres.')
        change_password(client, 'kali', new_password)
        print('Senha alterada. Nenhuma senha nova foi passada como argumento de comando.')
    finally:
        client.close()
    client = connect_ssh(port, ssh_key, password=new_password)
    try:
        print('Etapa 7/8: preferencias opcionais...')
        create_folders = yes('Deseja criar pastas opcionais de laboratório (scans, evidências e notas)?', default=False)
        # This first release intentionally does not upgrade 1,000+ packages without explicit opt-in.
        upgrade = yes('Executar atualização completa de pacotes agora? (pode ser demorado)')
        setup_lab(client, new_password, update=upgrade, create_folders=create_folders)
        print('Etapa 8/8: finalizando configuração...')

        criar_snapshot = yes(
            'Criar snapshot inicial?',
            default=True
        )

        manter_ligada = yes(
            'Manter a máquina ligada ao finalizar?',
            default=True
        )

        plano = planejar_finalizacao(
            criar_snapshot,
            manter_ligada
        )

        if plano["desligar"]:
            shutdown_guest(client, new_password)
    finally:
        client.close()

    if plano["desligar"]:
        wait_poweroff(vbox, name, seconds=180)

    snapshot_name = None

    if plano["snapshot"]:
        snapshot_name = "VMForge-Inicial"
        vbox.snapshot(name, snapshot_name)

    if plano["religar"]:
        vbox.start(name)
    print('\nLABORATORIO CONFIGURADO')
    print(f'Maquina: {name}')
    print(f'Status: {vbox.status(name)}')
    print(f'Snapshot: {snapshot_name or "não solicitado"}')
    print(f'Pastas de laboratório: {"criadas" if create_folders else "não solicitadas"}')
    print(f'Para conectar (com VM ligada): ssh -p {port} kali@127.0.0.1')
    if not upgrade:
        print('Pendente: atualizar pacotes quando desejar: sudo apt update && sudo apt full-upgrade -y')
    print('Importante: aplicativos gráficos como Burp Suite exigem configuração de acessibilidade separada.')
    return 0
