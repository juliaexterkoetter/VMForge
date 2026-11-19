"""Import a trusted VMDK as a NEW isolated VirtualBox VM.

Run with python -m vmforge.import_disk. Safe dry-run is the default.
Does not modify or unregister existing VMs or the source VMDK.
"""
import argparse
import re
import subprocess
from pathlib import Path

from .providers.virtualbox import VirtualBox, VMError
from .protection import load_protection


_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_WINDOWS_DEVICE_NAMES = frozenset({
    'CON', 'PRN', 'AUX', 'NUL',
    *(f'COM{i}' for i in range(1, 10)),
    *(f'LPT{i}' for i in range(1, 10)),
})


def _call(binary, *args, timeout=300):
    try:
        p = subprocess.run([str(binary), *map(str, args)], text=True,
                           capture_output=True, encoding="utf-8",
                           errors="replace", timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VMError(f"Falha no VirtualBox: {exc}") from exc
    if p.returncode:
        raise VMError((p.stderr or p.stdout or "VBoxManage falhou").strip())
    return p.stdout.strip()


def plan(source, name, basefolder, hostonly, ram=512, cpus=1, vb=None):
    """Validate safely and return an execution plan; never mutates."""
    vb = vb or VirtualBox()
    protection = load_protection()  # fail closed if missing/invalid
    if not _NAME.fullmatch(name) or name in ('.', '..'):
        raise ValueError("Nome inválido (use letras, números, ponto, hífen ou sublinhado).")
    # The VM name becomes both a directory and a disk filename, including on Windows.
    if name.endswith('.') or name.split('.')[0].upper() in _WINDOWS_DEVICE_NAMES:
        raise ValueError("Nome inválido para Windows: não use nomes de dispositivo reservados ou ponto final.")
    if protection.protects_vm(name=name):
        raise ValueError("Nome de VM protegido.")
    if not (256 <= ram <= 131072 and 1 <= cpus <= 64):
        raise ValueError("RAM ou CPUs fora dos limites.")
    raw_source = Path(source).expanduser()
    if raw_source.is_symlink():
        raise ValueError("Links simbólicos não são aceitos como fonte.")
    try:
        src = raw_source.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError("Disco de origem inexistente ou inacessível.") from exc
    if not src.is_file() or src.suffix.lower() != '.vmdk' or src.is_symlink():
        raise ValueError("Informe um disco .vmdk regular e confiável.")
    base = Path(basefolder).expanduser().resolve(strict=True)
    if not base.is_dir():
        raise ValueError("Pasta-base inexistente.")
    target = base / name
    if target.exists():
        raise ValueError(f"Destino já existe, não será sobrescrito: {target}")
    if any(v['name'].casefold() == name.casefold() for v in vb.list_vms()):
        raise ValueError("Já existe VM registrada com este nome.")
    if not hostonly or '\n' in hostonly or '\r' in hostonly:
        raise ValueError("Informe a interface Host-only.")
    interfaces = _call(vb.binary, 'list', 'hostonlyifs')
    names = re.findall(r'^Name:\s*(.+?)\s*$', interfaces, flags=re.MULTILINE)
    if hostonly not in names:
        raise ValueError("Interface Host-only não encontrada.")
    return {'source': src, 'name': name, 'base': base, 'target': target,
            'hostonly': hostonly, 'ram': ram, 'cpus': cpus, 'binary': vb.binary}


def execute(p):
    """Create NEW VM and clone source medium to private VDI, without force cleanup."""
    binary = p['binary']
    name = p['name']
    # Fail-closed revalidation immediately before the first mutating operation.
    current = plan(p['source'], name, p['base'], p['hostonly'],
                   p['ram'], p['cpus'], VirtualBox(binary))
    if current['target'] != p['target']:
        raise VMError('Destino mudou desde o planejamento.')
    # New VM is registered first, so VirtualBox owns its configuration directory.
    _call(binary, 'createvm', '--name', name, '--ostype', 'Ubuntu',
          '--basefolder', p['base'], '--register')
    try:
        target_disk = p['target'] / (name + '.vdi')
        _call(binary, 'clonemedium', 'disk', p['source'], target_disk, '--format', 'VDI', timeout=1200)
        _call(binary, 'modifyvm', name, '--memory', p['ram'], '--cpus', p['cpus'],
              '--firmware', 'bios', '--pae', 'on', '--usb-ohci', 'on',
              '--usb-ehci', 'off', '--usb-xhci', 'off',
              '--nic1', 'hostonly', '--host-only-adapter1', p['hostonly'],
              '--nic2', 'none', '--nic3', 'none', '--nic4', 'none',
              '--nic5', 'none', '--nic6', 'none', '--nic7', 'none', '--nic8', 'none')
        _call(binary, 'storagectl', name, '--name', 'SATA', '--add', 'sata',
              '--controller', 'IntelAhci')
        _call(binary, 'storageattach', name, '--storagectl', 'SATA',
              '--port', '0', '--device', '0', '--type', 'hdd', '--medium', target_disk)
    except Exception as exc:
        raise VMError(f"Configuração parcial da NOVA VM {name}. "
                      "Arquivos e registro preservados para diagnóstico. "
                      "Não repita a importação sem inspecionar o estado. "
                      f"Erro: {exc}") from exc
    return name


def main(argv=None):
    parser = argparse.ArgumentParser(description='Importação conservadora de VMDK para VM nova e Host-only')
    parser.add_argument('--source', required=True, help='Caminho do .vmdk confiável')
    parser.add_argument('--name', required=True, help='Novo nome da VM')
    parser.add_argument('--basefolder', required=True, help='Pasta-base EXISTENTE das VMs')
    parser.add_argument('--hostonly', required=True, help='Nome da interface Host-only existente')
    parser.add_argument('--memory', type=int, default=512)
    parser.add_argument('--cpus', type=int, default=1)
    parser.add_argument('--execute', action='store_true', help='Executar após confirmação; sem flag só simula')
    args = parser.parse_args(argv)
    try:
        p = plan(args.source, args.name, args.basefolder, args.hostonly,
                 args.memory, args.cpus)
        print('Plano: criar NOVA VM', p['name'])
        print('Fonte VMDK (somente leitura):', p['source'])
        print('Destino:', p['target'])
        print('Disco novo: clone independente VDI')
        print('Rede: Host-only', p['hostonly'], '; sem NAT, sem Bridge')
        print('RAM:', p['ram'], 'MB; CPU(s):', p['cpus'])
        if not args.execute:
            print('SIMULAÇÃO: nenhuma alteração realizada.')
            return 0
        answer = input('Digite CRIAR para autorizar: ').strip()
        if answer != 'CRIAR':
            print('Cancelado sem alterações.')
            return 0
        print('VM criada:', execute(p))
        print('A VM permanece DESLIGADA. Verifique o estado antes de iniciar.')
        return 0
    except (EOFError, KeyboardInterrupt):
        print('Importação interrompida pelo usuário. Verifique o estado antes de tentar novamente.')
        return 1
    except (ValueError, VMError, OSError) as exc:
        print('Erro:', exc)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
