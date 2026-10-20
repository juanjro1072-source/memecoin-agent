"""Lee config/limites.toml. Si algo falta o está mal, no se opera."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from . import RAIZ

RUTA_CONFIG = RAIZ / "config" / "limites.toml"


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    modo: str
    saldo_inicial: float
    max_por_operacion: float
    max_por_dia: float
    max_por_wallet: float
    slippage_maximo_pct: float
    hype_minimo: float
    riesgo_maximo: float
    tomar_ganancia_pct: float
    cortar_perdida_pct: float
    max_top10_pct: float
    max_creador_pct: float
    exigir_liquidez_bloqueada: bool
    max_wallets_coordinadas: float


def _numero(tabla: dict, clave: str, minimo: float = 0, estricto: bool = True) -> float:
    valor = tabla.get(clave)
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ConfigError(f"Falta '{clave}' en limites.toml o no es un número.")
    if valor < minimo or (estricto and valor == minimo):
        signo = ">" if estricto else ">="
        raise ConfigError(f"'{clave}' tiene que ser {signo} {minimo} (ahora vale {valor}).")
    return float(valor)


def cargar(ruta: Path = RUTA_CONFIG) -> Config:
    try:
        datos = tomllib.loads(ruta.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError(f"No encuentro {ruta}. Sin límites no se opera.") from None
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"limites.toml está mal escrito: {e}") from None

    # Regla 1: si el modo no se entiende, se asume sombra.
    modo = datos.get("modo") if datos.get("modo") in ("sombra", "real") else "sombra"
    est = datos.get("estrategia") or {}
    seg = datos.get("seguridad") or {}
    bloqueada = seg.get("exigir_liquidez_bloqueada")
    if not isinstance(bloqueada, bool):
        raise ConfigError("'exigir_liquidez_bloqueada' tiene que ser true o false.")

    return Config(
        modo=modo,
        saldo_inicial=_numero(datos, "saldo_sombra_inicial_usd"),
        max_por_operacion=_numero(datos, "max_por_operacion_usd"),
        max_por_dia=_numero(datos, "max_por_dia_usd"),
        max_por_wallet=_numero(datos, "max_por_wallet_usd"),
        slippage_maximo_pct=_numero(datos, "slippage_maximo_pct"),
        hype_minimo=_numero(est, "hype_minimo", estricto=False),
        riesgo_maximo=_numero(est, "riesgo_maximo", estricto=False),
        tomar_ganancia_pct=_numero(est, "tomar_ganancia_pct"),
        cortar_perdida_pct=_numero(est, "cortar_perdida_pct"),
        max_top10_pct=_numero(seg, "max_top10_holders_pct"),
        max_creador_pct=_numero(seg, "max_creador_pct", estricto=False),
        exigir_liquidez_bloqueada=bloqueada,
        max_wallets_coordinadas=_numero(seg, "max_wallets_coordinadas", estricto=False),
    )
