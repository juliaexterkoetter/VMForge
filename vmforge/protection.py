"""Configuração local das máquinas virtuais protegidas."""

import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProtectionConfig:
    uuids: frozenset[str]
    names: frozenset[str]
    ports: frozenset[int]

    def protects_vm(self, uuid_value=None, name=None):
        if uuid_value is not None:
            try:
                identifier = str(uuid.UUID(str(uuid_value).strip("{}")))
            except (ValueError, AttributeError, TypeError) as exc:
                raise ValueError("UUID inválido. Operação bloqueada.") from exc

            if identifier in self.uuids:
                return True

        return name is not None and name.casefold() in self.names

    def reserves_port(self, port):
        return port in self.ports


def load_protection(path=None):
    """Carrega a proteção local ou bloqueia se ela estiver indisponível."""

    config_path = (
        Path(path)
        if path is not None
        else Path(
            os.environ.get(
                "VMFORGE_PROTECTION_CONFIG",
                str(Path.home() / ".vmforge" / "config.json")
            )
        )
    )

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"Não foi possível carregar a configuração de proteção: {config_path}"
        ) from exc

    if not isinstance(data, dict):
        raise ValueError("Configuração de proteção inválida.")

    machines = data.get("protected_vms")
    ports = data.get("reserved_ports")

    if not isinstance(machines, list) or not isinstance(ports, list):
        raise ValueError("Listas de máquinas e portas obrigatórias.")

    uuids = set()
    names = set()

    for machine in machines:
        if not isinstance(machine, dict):
            raise ValueError("Entrada de máquina protegida inválida.")

        name = machine.get("name")
        identifier = machine.get("uuid")

        if not isinstance(name, str) or not name.strip():
            raise ValueError("Nome de máquina protegida inválido.")

        try:
            identifier = str(uuid.UUID(str(identifier).strip("{}")))
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError("UUID de máquina protegida inválido.") from exc

        uuids.add(identifier)
        names.add(name.casefold())

    checked_ports = set()

    for port in ports:
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("Porta reservada inválida.")
        checked_ports.add(port)

    return ProtectionConfig(
        uuids=frozenset(uuids),
        names=frozenset(names),
        ports=frozenset(checked_ports),
    )


def require_unprotected(uuid_value=None, name=None, config=None):
    """Bloqueia operações sobre máquinas virtuais protegidas."""
    protection = config if config is not None else load_protection()

    if protection.protects_vm(uuid_value, name):
        raise ValueError(
            "Máquina virtual protegida: operação não autorizada."
        )

    return True


def require_available_port(port, config=None):
    """Bloqueia o uso de portas reservadas."""
    protection = config if config is not None else load_protection()

    if protection.reserves_port(port):
        raise ValueError(
            f"Porta {port} reservada para uma máquina protegida."
        )

    return True
