"""Convierte un par de DexScreener en dos números: HYPE (0-100) y RIESGO (0-100).

El hype mide cuánta gente está entrando ahora mismo. El riesgo mide cuántas
señales clásicas de rug-pull, honeypot o pump-and-dump muestra el token.
Las dos cosas juntas dan un "arquetipo" fácil de leer de un vistazo.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _num(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


@dataclass
class Snapshot:
    symbol: str
    name: str
    chain: str
    address: str
    url: str
    price_usd: float
    liquidity_usd: float
    fdv: float
    age_minutes: float
    volume_h1: float
    volume_h24: float
    buys_m5: int
    sells_m5: int
    buys_h1: int
    sells_h1: int
    change_m5: float
    change_h1: float
    change_h24: float
    socials: int
    has_website: bool
    boosts: int

    @property
    def key(self) -> str:
        return f"{self.chain}:{self.address}"

    @classmethod
    def from_pair(cls, pair: dict, now: float | None = None) -> "Snapshot":
        now = now or time.time()
        base = pair.get("baseToken") or {}
        txns = pair.get("txns") or {}
        vol = pair.get("volume") or {}
        chg = pair.get("priceChange") or {}
        info = pair.get("info") or {}
        created_ms = _num(pair.get("pairCreatedAt"))
        age = (now - created_ms / 1000) / 60 if created_ms else 10_000.0
        return cls(
            symbol=base.get("symbol") or "?",
            name=base.get("name") or "?",
            chain=pair.get("chainId") or "?",
            address=base.get("address") or "",
            url=pair.get("url") or "",
            price_usd=_num(pair.get("priceUsd")),
            liquidity_usd=_num((pair.get("liquidity") or {}).get("usd")),
            fdv=_num(pair.get("fdv") or pair.get("marketCap")),
            age_minutes=max(age, 0.0),
            volume_h1=_num(vol.get("h1")),
            volume_h24=_num(vol.get("h24")),
            buys_m5=int(_num((txns.get("m5") or {}).get("buys"))),
            sells_m5=int(_num((txns.get("m5") or {}).get("sells"))),
            buys_h1=int(_num((txns.get("h1") or {}).get("buys"))),
            sells_h1=int(_num((txns.get("h1") or {}).get("sells"))),
            change_m5=_num(chg.get("m5")),
            change_h1=_num(chg.get("h1")),
            change_h24=_num(chg.get("h24")),
            socials=len(info.get("socials") or []),
            has_website=bool(info.get("websites")),
            boosts=int(_num((pair.get("boosts") or {}).get("active"))),
        )


@dataclass
class Verdict:
    snap: Snapshot
    hype: int
    risk: int
    archetype: str
    hype_reasons: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)


ARCHETYPES = {
    "COHETE": "🚀 COHETE",    # mucho hype, poco riesgo: lo que buscas
    "BROTE": "🌱 BROTE",      # hype moderado y sano: vigilar
    "CASINO": "🎰 CASINO",    # mucho hype pero muchas banderas rojas
    "TRAMPA": "🪤 TRAMPA",    # poco hype real y mucho riesgo: huir
    "DORMIDO": "🧊 DORMIDO",  # no pasa nada interesante
}


def hype_score(s: Snapshot) -> tuple[int, list[str]]:
    reasons: list[str] = []
    score = 0.0

    # Rotación: volumen de la última hora comparado con la liquidez del pool.
    turnover = s.volume_h1 / max(s.liquidity_usd, 1.0)
    pts = _clamp(turnover / 2) * 30
    score += pts
    if pts >= 15:
        reasons.append(f"volumen 1h = {turnover:.1f}x la liquidez")

    # Presión compradora en la última hora.
    total_h1 = s.buys_h1 + s.sells_h1
    if total_h1:
        ratio = s.buys_h1 / total_h1
        pts = _clamp((ratio - 0.5) / 0.3) * 20
        score += pts
        if pts >= 10:
            reasons.append(f"{ratio:.0%} de las operaciones son compras")

    # Velocidad: operaciones en los últimos 5 minutos.
    tx_m5 = s.buys_m5 + s.sells_m5
    pts = _clamp(tx_m5 / 100) * 20
    score += pts
    if pts >= 10:
        reasons.append(f"{tx_m5} operaciones en 5 min")

    # Momentum de precio (sólo cuenta subida).
    pts = _clamp(s.change_h1 / 200) * 20
    score += pts
    if pts >= 10:
        reasons.append(f"+{s.change_h1:.0f}% en 1h")

    # Comunidad visible.
    pts = _clamp(s.socials / 3) * 10
    score += pts
    if s.socials >= 2:
        reasons.append(f"{s.socials} redes sociales enlazadas")

    return round(score), reasons


def risk_score(s: Snapshot) -> tuple[int, list[str]]:
    flags: list[str] = []
    score = 0

    def flag(points: int, text: str) -> None:
        nonlocal score
        score += points
        flags.append(text)

    if s.liquidity_usd < 5_000:
        flag(35, f"liquidez microscópica (${s.liquidity_usd:,.0f})")
    elif s.liquidity_usd < 20_000:
        flag(20, f"liquidez baja (${s.liquidity_usd:,.0f})")
    elif s.liquidity_usd < 50_000:
        flag(10, f"liquidez modesta (${s.liquidity_usd:,.0f})")

    if s.age_minutes < 30:
        flag(15, f"recién nacido ({s.age_minutes:.0f} min)")
    elif s.age_minutes < 180:
        flag(8, f"muy joven ({s.age_minutes / 60:.1f} h)")

    if s.socials == 0 and not s.has_website:
        flag(15, "fantasma: sin web ni redes")

    if s.liquidity_usd > 0:
        fdv_liq = s.fdv / s.liquidity_usd
        if fdv_liq > 100:
            flag(15, f"FDV {fdv_liq:.0f}x la liquidez (valoración de papel)")
        elif fdv_liq > 40:
            flag(8, f"FDV {fdv_liq:.0f}x la liquidez")

    # Muchos compran y nadie vende: firma típica de un honeypot.
    if s.buys_h1 >= 25 and s.sells_h1 == 0:
        flag(40, f"{s.buys_h1} compras y 0 ventas en 1h: posible HONEYPOT")
    elif s.buys_h1 >= 25 and s.sells_h1 / s.buys_h1 < 0.05:
        flag(20, "casi nadie logra vender (¿impuesto de venta oculto?)")

    if s.change_m5 <= -25:
        flag(20, f"desplome en curso ({s.change_m5:.0f}% en 5 min)")
    if s.sells_m5 >= 10 and s.sells_m5 > 2 * s.buys_m5:
        flag(10, "ballenas saliendo: ventas duplican compras")
    if s.change_h1 >= 500:
        flag(10, f"parabólico (+{s.change_h1:.0f}% en 1h): late-buyers pagan la fiesta")
    if s.boosts and s.socials == 0:
        flag(10, "hype pagado (boosts) sin comunidad")

    return min(score, 100), flags


def archetype(hype: int, risk: int) -> str:
    if hype >= 60:
        return ARCHETYPES["COHETE"] if risk < 40 else ARCHETYPES["CASINO"]
    if risk >= 60:
        return ARCHETYPES["TRAMPA"]
    if hype >= 35 and risk < 40:
        return ARCHETYPES["BROTE"]
    return ARCHETYPES["DORMIDO"]


def evaluate(pair: dict, now: float | None = None) -> Verdict:
    snap = Snapshot.from_pair(pair, now)
    hype, reasons = hype_score(snap)
    risk, flags = risk_score(snap)
    return Verdict(snap, hype, risk, archetype(hype, risk), reasons, flags)
