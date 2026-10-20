"""Comisiones y slippage realistas para las compras y ventas imaginarias.

Usa la misma fórmula de slippage que el simulador, con la liquidez REAL del
pool, más un 0.5 % por lo que se mueve el precio mientras se confirma la
transacción. No simula fallos de red al azar: sólo cancela si el slippage
pasa tu máximo de limites.toml.
"""

from __future__ import annotations

from dataclasses import dataclass

from trading.mercado import COMISION_DEX, COMISION_RED_USD, impacto_pct

COMISION_DEX_ESPECIAL = {"pumpfun": 0.01}  # pump.fun cobra 1 % antes de graduarse
MOVIMIENTO_PCT = 0.5
LIQUIDEZ_MINIMA_VENTA_USD = 100


def comision_dex(dex: str | None) -> float:
    return COMISION_DEX_ESPECIAL.get(dex or "", COMISION_DEX)


def comision_red(cadena: str) -> float:
    return COMISION_RED_USD.get(cadena, 0.5)


@dataclass
class Compra:
    ok: bool
    motivo: str
    precio_entrada: float
    cantidad: float
    comision_red: float
    comision_dex: float
    slippage_pct: float


def simular_compra(monto: float, precio: float, liquidez: float, cadena: str, dex: str | None,
                   slippage_max: float) -> Compra:
    red = comision_red(cadena)
    slip = impacto_pct(liquidez, monto) + MOVIMIENTO_PCT
    if slip > slippage_max:
        return Compra(False, f"el precio empeoraría {slip:.1f}% (tu máximo es {slippage_max:g}%)",
                      0.0, 0.0, red, 0.0, slip)
    fee = monto * comision_dex(dex)
    entrada = precio * (1 + slip / 100)
    return Compra(True, "", entrada, (monto - fee) / entrada, red, fee, slip)


def valor_venta(cantidad: float, precio: float | None, liquidez: float | None, cadena: str,
                dex: str | None) -> tuple[float, str]:
    """Dólares que recibirías vendiendo todo ahora, a cualquier precio."""
    if precio is None or not liquidez or liquidez < LIQUIDEZ_MINIMA_VENTA_USD:
        return 0.0, "sin liquidez: no se podría vender"
    bruto = cantidad * precio
    slip = min(impacto_pct(liquidez, bruto) + MOVIMIENTO_PCT, 100)
    neto = bruto * (1 - slip / 100) * (1 - comision_dex(dex)) - comision_red(cadena)
    return max(neto, 0.0), f"slippage de venta {slip:.1f}%"
