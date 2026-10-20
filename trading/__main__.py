"""Simulador del modo sombra.

    python -m trading                 # simula un día con dinero ficticio
    python -m trading --semilla 42    # repite exactamente el mismo día
    python -m trading --tokens 100    # un día con más lanzamientos
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import date

from . import RAIZ, config
from .interruptor import RUTA_PARAR, hay_que_parar
from .simulador import Simulador


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="trading", description="Simulador del modo sombra (dinero ficticio).")
    parser.add_argument("--semilla", type=int, help="número para repetir el mismo día simulado")
    parser.add_argument("--tokens", type=int, default=60, help="cuántos tokens se lanzan en el día")
    args = parser.parse_args(argv)

    if hay_que_parar():
        print(f"⛔ Existe {RUTA_PARAR.name}: no arranco. Bórralo tú cuando quieras seguir.")
        return 1
    try:
        cfg = config.cargar()
    except config.ConfigError as e:
        print(f"⛔ No opero: {e}")
        return 1
    if cfg.modo != "sombra":
        print("Aviso: limites.toml dice modo = \"real\", pero esto es SÓLO un simulador:"
              " nunca toca dinero real.\n")

    semilla = args.semilla if args.semilla is not None else random.randrange(1_000_000)
    carpeta = RAIZ / "diario" / "sombra" / f"{date.today().isoformat()}_semilla-{semilla}"
    texto = Simulador(cfg, semilla, args.tokens, carpeta).correr()
    print(texto)
    print(f"📓 Diario completo en: {carpeta.relative_to(RAIZ)}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
