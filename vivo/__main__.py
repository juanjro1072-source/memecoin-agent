"""Observador en vivo, MODO SOMBRA (precios reales, dinero ficticio).

    python3 -m vivo                     # arrancar (Ctrl+C para detener)
    python3 -m vivo --cada 300          # un ciclo cada 5 minutos
    python3 -m vivo resumen             # rehacer el resumen de hoy sin arrancar
    python3 -m vivo probar DIRECCION    # comprobar que DexScreener y RugCheck responden
"""

import sys

if sys.version_info < (3, 11):
    sys.exit("Necesitas Python 3.11 o más nuevo. En el Mac: descárgalo de https://www.python.org/downloads/ "
             f"(ahora tienes {sys.version.split()[0]}).")

import argparse
import json

from trading import RAIZ, config

from .fuentes import RUGCHECK_URL, FuentesReales, _get_json, normalizar_rugcheck
from .observador import Observador

CARPETA = RAIZ / "diario" / "vivo"


def probar(direccion: str) -> int:
    """Diagnóstico: muestra lo que devuelven las dos fuentes para un token de Solana."""
    fuentes = FuentesReales()
    print(f"1) DexScreener para {direccion} …")
    try:
        pares = fuentes.precios("solana", [direccion])
        for p in pares[:3]:
            print(f"   par {p.get('pairAddress')} en {p.get('dexId')}: precio ${p.get('priceUsd')},"
                  f" liquidez ${(p.get('liquidity') or {}).get('usd')}")
        if not pares:
            print("   (no devolvió pares: ¿la dirección es de Solana?)")
    except Exception as e:
        print(f"   ❌ error: {e}")
    print("2) RugCheck …")
    try:
        crudo = _get_json(RUGCHECK_URL.format(direccion))
        print("   campos recibidos:", ", ".join(sorted(crudo)) if isinstance(crudo, dict) else type(crudo))
        billeteras, extra = normalizar_rugcheck(crudo)
        print("   lo que entendí:", json.dumps(billeteras, ensure_ascii=False))
        for m in extra:
            print("   ⚠️", m)
    except Exception as e:
        print(f"   ❌ error: {e}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vivo", description="Observador en modo sombra con precios reales.")
    parser.add_argument("accion", nargs="?", default="correr", choices=["correr", "resumen", "probar"])
    parser.add_argument("direccion", nargs="?", help="para 'probar': dirección de un token de Solana")
    parser.add_argument("--cada", type=int, default=120, help="segundos entre ciclos (mínimo 30)")
    args = parser.parse_args(argv)

    if args.accion == "probar":
        if not args.direccion:
            parser.error("falta la dirección del token: python3 -m vivo probar DIRECCION")
        return probar(args.direccion)
    if args.accion == "resumen":
        try:
            cfg = config.cargar()
        except config.ConfigError as e:
            print(f"⛔ {e}")
            return 1
        ruta = Observador(CARPETA).escribir_resumenes(cfg)
        print(ruta.read_text(encoding="utf-8"))
        return 0
    return Observador(CARPETA).correr(max(30, args.cada))


if __name__ == "__main__":
    sys.exit(main())
