"""Input validation and import helpers."""
import os
import re
import shutil
import socket
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Settings:
    image: Path
    destination: Path
    ram: int = 4096
    cpus: int = 2
    port: int = 2223


def validate(settings):
    if not settings.image.is_file() or settings.image.suffix.lower() not in ('.7z', '.vbox'):
        raise ValueError('Informe um arquivo .7z ou .vbox existente.')
    if not 1024 <= settings.ram <= 131072:
        raise ValueError('RAM fora do intervalo de 1024 a 131072 MB.')
    if not 1 <= settings.cpus <= 64:
        raise ValueError('Quantidade de CPUs fora do intervalo de 1 a 64.')
    if not 1024 <= settings.port <= 65535:
        raise ValueError('A porta SSH precisa estar entre 1024 e 65535.')
    if settings.destination.exists():
        raise ValueError('A pasta de destino ja existe. Escolha outra pasta vazia/inexistente.')
    with socket.socket() as sock:
        try:
            sock.bind(('127.0.0.1', settings.port))
        except OSError as exc:
            raise ValueError(f'Porta local {settings.port} indisponivel.') from exc
    if settings.image.suffix.lower() == '.vbox' and settings.destination.resolve() == settings.image.parent.resolve():
        raise ValueError('O destino precisa ser diferente da pasta de origem.')


from .extraction import find_extractor, sevenzip_path, extract_archive


def prepare_image(settings):
    """Copy/import a trusted VirtualBox appliance. Never modify the original."""
    validate(settings)
    try:
        if settings.image.suffix.lower() == '.7z':
            extract_archive(settings.image, settings.destination)
        else:
            raise ValueError('Importação direta de .vbox bloqueada até validar referências externas; utilize o .7z original.')
        matches = list(settings.destination.rglob('*.vbox'))
        if len(matches) != 1:
            raise RuntimeError(f'Esperado exatamente um arquivo .vbox; encontrados: {len(matches)}.')
        from .appliance import validate_appliance
        validate_appliance(matches[0])
        return matches[0]
    except Exception:
        # Retain the directory on failure so the user can inspect the files.
        raise
