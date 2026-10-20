"""Interruptor de emergencia: si existe PARAR.txt en la raíz, no se opera."""

from pathlib import Path

from . import RAIZ

RUTA_PARAR = RAIZ / "PARAR.txt"


def hay_que_parar(ruta: Path = RUTA_PARAR) -> bool:
    return ruta.exists()
