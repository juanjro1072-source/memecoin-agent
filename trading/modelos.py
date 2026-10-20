"""Datos que se pasan entre el simulador y el diario."""

from __future__ import annotations

from dataclasses import dataclass, field

from radar.scoring import Verdict

from .mercado import Ejecucion, Token


@dataclass
class Candidato:
    """Un token que el radar vio con hype suficiente."""
    token: Token
    veredicto: Verdict
    hora: str
    precio_visto: float


@dataclass
class Posicion:
    cand: Candidato
    compra: Ejecucion
    hora_entrada: str
    nota_monto: str
    eventos: list[str] = field(default_factory=list)
    comisiones_venta: float = 0.0  # comisiones de red de cada intento de venta, falle o no
    intentos_honeypot: int = 0
    atrapada: bool = False
    venta: Ejecucion | None = None
    hora_salida: str = ""
    motivo_salida: str = ""
    vendida_tras_rug: bool = False

    @property
    def costo(self) -> float:
        return self.compra.usd + self.compra.comision_red

    @property
    def cerrada(self) -> bool:
        return self.venta is not None

    def valor_actual(self) -> float:
        if self.venta:
            return self.venta.usd
        if self.atrapada:
            return 0.0  # no se puede vender: vale cero para ti
        return self.compra.cantidad * self.cand.token.precio

    def resultado_usd(self) -> float:
        return self.valor_actual() - self.costo - self.comisiones_venta
