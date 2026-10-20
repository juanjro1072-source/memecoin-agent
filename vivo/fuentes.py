"""Fuentes de datos de SÓLO LECTURA: peticiones GET públicas, sin wallet ni claves.

- DexScreener: tokens nuevos, precios y liquidez.
- RugCheck.xyz: dueños del token, creador, liquidez bloqueada, wallets
  "insider" y permisos peligrosos. Sólo existe para Solana.

Si un dato no llega o no se entiende, se devuelve None: la revisión de
seguridad lo trata como "falta el dato" y NO se compra (regla 6).
"""

from __future__ import annotations

import json
import time
import urllib.request

from radar import dexscreener

RUGCHECK_URL = "https://api.rugcheck.xyz/v1/tokens/{}/report"
CADENAS = {"solana"}  # las únicas donde podemos revisar wallets sin claves
LIQUIDEZ_BLOQUEADA_MIN_PCT = 90
SIN_DATOS = {"top10_pct": None, "creador_pct": None, "liquidez_bloqueada": None, "wallets_coordinadas": None}


def _get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": dexscreener.USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def _num(valor) -> float | None:
    if isinstance(valor, bool):
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def normalizar_rugcheck(d: dict) -> tuple[dict, list[str]]:
    """Convierte el informe de RugCheck en los datos que pide la regla 6.

    Devuelve (billeteras, motivos_extra). Los motivos extra son peligros que
    por sí solos impiden comprar.
    """
    if not isinstance(d, dict):
        return dict(SIN_DATOS), ["RugCheck devolvió algo que no entiendo: ante la duda no se opera"]
    extra: list[str] = []
    billeteras = dict(SIN_DATOS)

    # Cuentas del pool de liquidez o de bloqueo: no son "dueños" de verdad.
    conocidas = d.get("knownAccounts") if isinstance(d.get("knownAccounts"), dict) else {}
    no_duenos = {dir_ for dir_, info in conocidas.items()
                 if isinstance(info, dict) and str(info.get("type", "")).upper() in ("AMM", "LOCKER")}

    holders = d.get("topHolders")
    if isinstance(holders, list) and holders:
        pcts_todos = [_num(h.get("pct")) for h in holders if isinstance(h, dict)]
        # Si todo suma <= 1, vienen como fracción (0.12) y no como porcentaje (12).
        escala = 100 if pcts_todos and None not in pcts_todos and sum(pcts_todos) <= 1 else 1
        reales = [h for h in holders if isinstance(h, dict)
                  and h.get("address") not in no_duenos and h.get("owner") not in no_duenos]
        pcts = [_num(h.get("pct")) for h in reales[:10]]
        if pcts and None not in pcts:
            billeteras["top10_pct"] = sum(pcts) * escala
            creador = d.get("creator")
            if creador:
                propios = [_num(h.get("pct")) for h in reales if creador in (h.get("owner"), h.get("address"))]
                if propios and None not in propios:
                    billeteras["creador_pct"] = sum(propios) * escala
                elif len(reales) >= 10:
                    # No está en el top 10: tiene, como mucho, lo del más pequeño del top.
                    billeteras["creador_pct"] = min(pcts) * escala

    mercados = d.get("markets")
    if isinstance(mercados, list):
        bloqueos = [_num((m.get("lp") or {}).get("lpLockedPct")) for m in mercados if isinstance(m, dict)]
        bloqueos = [b for b in bloqueos if b is not None]
        if bloqueos:
            billeteras["liquidez_bloqueada"] = max(bloqueos) >= LIQUIDEZ_BLOQUEADA_MIN_PCT

    insiders = d.get("graphInsidersDetected")
    if isinstance(insiders, int) and not isinstance(insiders, bool):
        billeteras["wallets_coordinadas"] = insiders

    if d.get("rugged") is True:
        extra.append("RugCheck lo marca como RUGGED (ya le hicieron rug-pull)")
    token = d.get("token") if isinstance(d.get("token"), dict) else {}
    for clave, peligro in (("freezeAuthority", "el creador puede CONGELAR tus tokens (no podrías vender)"),
                           ("mintAuthority", "el creador puede imprimir más tokens cuando quiera")):
        if clave in d:
            valor = d[clave]
        elif clave in token:
            valor = token[clave]
        else:
            extra.append(f"falta el dato «{clave}»: ante la duda no se opera")
            continue
        if valor:
            extra.append(peligro)
    return billeteras, extra


class FuentesReales:
    def __init__(self, pausa: float = 1.0):
        self.pausa = pausa  # segundos entre consultas a RugCheck, para no saturarlo

    def descubrir(self, limite: int = 60) -> list[dict]:
        return dexscreener.discover(CADENAS, limite)

    def precios(self, cadena: str, direcciones: list[str]) -> list[dict]:
        return dexscreener.pairs_for_tokens(cadena, direcciones)

    def wallets(self, cadena: str, direccion: str) -> tuple[dict, list[str]]:
        if cadena not in CADENAS:
            return dict(SIN_DATOS), [f"no sé revisar wallets en {cadena}: ante la duda no se opera"]
        time.sleep(self.pausa)
        return normalizar_rugcheck(_get_json(RUGCHECK_URL.format(direccion)))
