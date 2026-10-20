"""Revisión anti-estafa antes de comprar (regla 6 de CLAUDE.md)."""

from __future__ import annotations

from radar.scoring import Verdict

from .config import Config

_NOMBRES = {
    "top10_pct": "concentración de los 10 mayores dueños",
    "creador_pct": "porcentaje del creador",
    "liquidez_bloqueada": "si la liquidez está bloqueada",
    "wallets_coordinadas": "wallets nuevas comprando juntas",
}


def motivo_radar(veredicto: Verdict, cfg: Config) -> str | None:
    """Motivo para no comprar según las señales de rug-pull del radar, o None."""
    if veredicto.risk <= cfg.riesgo_maximo:
        return None
    banderas = "; ".join(veredicto.risk_flags) or "sin detalle"
    return f"riesgo del radar {veredicto.risk} (máximo {cfg.riesgo_maximo:g}): {banderas}"


def revisar(veredicto: Verdict, billeteras: dict, cfg: Config) -> list[str]:
    """Devuelve los motivos para NO comprar. Lista vacía = pasa la revisión."""
    motivos: list[str] = []

    radar = motivo_radar(veredicto, cfg)
    if radar:
        motivos.append(radar)

    for clave, nombre in _NOMBRES.items():
        if billeteras.get(clave) is None:
            motivos.append(f"falta el dato «{nombre}»: ante la duda no se opera")

    top10 = billeteras.get("top10_pct")
    if top10 is not None and top10 > cfg.max_top10_pct:
        motivos.append(f"los 10 mayores dueños tienen el {top10:.0f}% (máximo {cfg.max_top10_pct:g}%)")
    creador = billeteras.get("creador_pct")
    if creador is not None and creador > cfg.max_creador_pct:
        motivos.append(f"el creador tiene el {creador:.0f}% (máximo {cfg.max_creador_pct:g}%)")
    if cfg.exigir_liquidez_bloqueada and billeteras.get("liquidez_bloqueada") is False:
        motivos.append("la liquidez no está bloqueada: el creador puede llevársela")
    coord = billeteras.get("wallets_coordinadas")
    if coord is not None and coord > cfg.max_wallets_coordinadas:
        motivos.append(f"{coord} wallets recién creadas compraron a la vez (máximo {cfg.max_wallets_coordinadas:g})")

    return motivos
