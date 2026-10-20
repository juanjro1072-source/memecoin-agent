"""Autopsias de cada decisión (regla 5) y resumen diario sencillo."""

from __future__ import annotations

from datetime import datetime

from .costos import LIQUIDEZ_MINIMA_VENTA_USD

_ACCION = {"compra": "compra sombra", "rechazo": "rechazada", "fallida": "compra que fallaría"}


def hora(ts: float, segundos: bool = False) -> str:
    return datetime.fromtimestamp(ts).strftime("%H:%M:%S" if segundos else "%H:%M")


def dia_hora(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%d/%m %H:%M")


def _usd(x: float) -> str:
    return f"{'-' if x < 0 else ''}${abs(x):,.2f}"


def _con_signo(x: float) -> str:
    return ("+" if x >= 0 else "") + _usd(x)


def costo(r: dict) -> float:
    return (r["monto"] or 0) + (r["comision_red"] or 0)


def desaparecio(r: dict, h: str) -> bool:
    liq = r[f"liquidez_{h}"]
    return r[f"precio_{h}"] is None or liq is None or liq < LIQUIDEZ_MINIMA_VENTA_USD


def cambio_pct(r: dict, h: str) -> float | None:
    """Cambio del precio desde la decisión hasta 1h/24h; None si el pool desapareció."""
    if desaparecio(r, h) or not r["precio"]:
        return None
    return (r[f"precio_{h}"] / r["precio"] - 1) * 100


def punto(r: dict, h: str) -> str:
    if r[f"momento_{h}"] is None:
        return "⏳"
    c = cambio_pct(r, h)
    return "desapareció" if c is None else f"{c:+.0f}%"


def veredicto(r: dict, tomar_ganancia_pct: float) -> str:
    if r["momento_24h"] is None:
        return "⏳ pendiente"
    if r["accion"] == "compra":
        res = r["valor_24h"] - costo(r)
        return f"{'✅ ganó' if res > 0 else '❌ perdió'} {_con_signo(res)}"
    c = cambio_pct(r, "24h")
    if c is None or c <= -50:
        return "✅ bien evitado (se desplomó o desapareció)"
    if c >= tomar_ganancia_pct:
        return f"😬 oportunidad perdida ({c:+.0f}%)"
    return f"➖ neutral ({c:+.0f}%)"


def saldo(filas: list[dict], saldo_inicial: float) -> tuple[float, float]:
    """(efectivo ficticio, dinero aún 'en juego' a precio de compra)."""
    efectivo, en_juego = saldo_inicial, 0.0
    for r in filas:
        if r["accion"] == "compra":
            efectivo -= costo(r)
            if r["momento_24h"] is None:
                en_juego += r["monto"]
            else:
                efectivo += r["valor_24h"]
        elif r["accion"] == "fallida":
            efectivo -= r["comision_red"] or 0
    return efectivo, en_juego


def _billeteras(b: dict | None) -> str:
    if b is None:
        return "no se consultó (el radar ya lo descartó)"
    def dato(clave, formato):
        return "sin dato" if b.get(clave) is None else formato(b[clave])
    return (f"top 10 con {dato('top10_pct', lambda v: f'{v:.0f}%')}, "
            f"creador con {dato('creador_pct', lambda v: f'{v:.1f}%')}, "
            f"liquidez bloqueada: {dato('liquidez_bloqueada', lambda v: 'sí' if v else 'NO')}, "
            f"wallets insider: {dato('wallets_coordinadas', str)}")


def _linea_punto(r: dict, h: str, segundos: int) -> str:
    etiqueta = "A 1 hora" if h == "1h" else "A 24 horas"
    m = r[f"momento_{h}"]
    if m is None:
        return f"- {etiqueta}: ⏳ pendiente (el {dia_hora(r['momento'] + segundos)})"
    retraso = (m - r["momento"] - segundos) / 60
    nota = f" · medido con {retraso:.0f} min de retraso (¿el Mac estaba dormido?)" if retraso > 10 else ""
    if desaparecio(r, h):
        texto = f"el pool desapareció o se quedó sin liquidez (medido el {dia_hora(m)})"
    else:
        texto = f"${r[f'precio_{h}']:.10g} ({punto(r, h)}) el {dia_hora(m)}"
    if r["accion"] == "compra":
        valor = r[f"valor_{h}"]
        texto += f" · si vendías: {_usd(valor)} ({_con_signo(valor - costo(r))} con comisiones)"
    return f"- {etiqueta}: {texto}{nota}"


def autopsia(r: dict, tomar_ganancia_pct: float) -> str:
    momento = datetime.fromtimestamp(r["momento"])
    lineas = [
        f"# Autopsia: ${r['simbolo']} · {momento:%Y-%m-%d %H:%M} ({_ACCION[r['accion']]})",
        "",
        "- **Modo:** sombra con precios reales (dinero ficticio, sin wallet)",
        f"- **Token:** {r['nombre']}, {r['cadena']}, `{r['token']}`" + (f" · {r['url']}" if r["url"] else ""),
        "",
        "## Qué vio",
        "",
        f"- Hype: {r['hype']} · Riesgo: {r['riesgo']} · Arquetipo: {r['arquetipo']}",
        f"- Precio exacto al decidir: ${r['precio'] or 0:.10g} (DexScreener, {hora(r['momento'], True)})"
        f" · liquidez ${r['liquidez'] or 0:,.0f} · FDV ${r['fdv'] or 0:,.0f}",
        "- Por qué tenía hype: " + ("; ".join(r["razones_hype"] or []) or "sin motivo claro"),
        "- Banderas rojas del radar: " + ("; ".join(r["banderas"] or []) or "ninguna"),
        "- Revisión de wallets (RugCheck): " + _billeteras(r["billeteras"]),
        "",
        "## Qué decidió",
        "",
    ]
    if r["accion"] == "compra":
        lineas += [
            f"- Acción: **comprar {_usd(r['monto'])}** (imaginario; {r['nota_monto']})",
            f"- Ejecución simulada: ${r['precio_entrada']:.10g} (slippage {r['slippage_pct']:.1f}%) · "
            f"comisiones: red {_usd(r['comision_red'])} + exchange {_usd(r['comision_dex'])}",
        ]
    elif r["accion"] == "fallida":
        lineas += [f"- Acción: intentar comprar {_usd(r['monto'])}, pero **fallaría**: {m}" for m in r["motivos"]]
        lineas.append(f"- Se perdería la comisión de red: {_usd(r['comision_red'])}")
    else:
        lineas.append(f"- Acción: **no operar** (lo frenó: {r['tipo']})")
        lineas += [f"- {m}" for m in r["motivos"]]
    lineas += [
        "",
        "## Qué resultó",
        "",
        _linea_punto(r, "1h", 3600),
        _linea_punto(r, "24h", 86400),
        f"- Veredicto: {veredicto(r, tomar_ganancia_pct)}",
        "",
    ]
    return "\n".join(lineas)


def resumen_dia(fecha: str, filas_dia: list[dict], todas: list[dict], vistos: int, cfg, ahora: float) -> str:
    compras = [r for r in filas_dia if r["accion"] == "compra"]
    rechazos = [r for r in filas_dia if r["accion"] == "rechazo"]
    fallidas = [r for r in filas_dia if r["accion"] == "fallida"]
    por_tipo = lambda t: sum(r["tipo"] == t for r in rechazos)
    efectivo, en_juego = saldo(todas, cfg.saldo_inicial)
    total = efectivo + en_juego - cfg.saldo_inicial

    cerradas = [r for r in todas if r["accion"] == "compra" and r["momento_24h"] is not None]
    ganadoras = [r for r in cerradas if r["valor_24h"] > costo(r)]
    resultado_cerradas = sum(r["valor_24h"] - costo(r) for r in cerradas)
    rech_24 = [r for r in todas if r["accion"] != "compra" and r["momento_24h"] is not None]
    evitados = [r for r in rech_24 if veredicto(r, cfg.tomar_ganancia_pct).startswith("✅")]
    perdidas = [r for r in rech_24 if veredicto(r, cfg.tomar_ganancia_pct).startswith("😬")]
    pct = lambda a, b: f"{a / b:.0%}" if b else "—"

    lineas = [
        f"# Resumen del {fecha} · modo sombra con precios reales",
        "",
        f"_Actualizado a las {hora(ahora)}. Dinero ficticio: nada de esto es real._",
        "",
        "## Hoy",
        "",
        f"- Tokens revisados: {vistos} · con hype suficiente: {len(filas_dia)}",
        f"- Compras sombra: {len(compras)} (gastado {_usd(sum(r['monto'] for r in compras))}"
        f" de {_usd(cfg.max_por_dia)} permitidos)",
        f"- Rechazadas: {len(rechazos)} (seguridad {por_tipo('seguridad')}, límites {por_tipo('límites')},"
        f" sin precio {por_tipo('precio')}) · compras que fallarían: {len(fallidas)}",
        "",
    ]
    if filas_dia:
        lineas += ["## Decisiones del día", "",
                   "| Hora | Token | Decisión | Precio al decidir | A 1 h | A 24 h | Veredicto |",
                   "|---|---|---|---|---|---|---|"]
        for r in filas_dia:
            lineas.append(f"| {hora(r['momento'])} | ${r['simbolo']} | {_ACCION[r['accion']]} | ${r['precio'] or 0:.6g} "
                          f"| {punto(r, '1h')} | {punto(r, '24h')} | {veredicto(r, cfg.tomar_ganancia_pct)} |")
        lineas.append("")
    lineas += [
        "## Desde el primer día",
        "",
        f"- Saldo sombra: {_usd(efectivo + en_juego)} (efectivo {_usd(efectivo)} + en juego {_usd(en_juego)}"
        f" a precio de compra) · resultado {_con_signo(total)}",
        f"- Compras cerradas a las 24 h: {len(cerradas)} · resultado {_con_signo(resultado_cerradas)}"
        f" · con ganancia: {pct(len(ganadoras), len(cerradas))}",
        f"- Rechazos comprobados a las 24 h: {len(rech_24)} · bien evitados: {pct(len(evitados), len(rech_24))}"
        f" · oportunidades perdidas: {len(perdidas)}",
        "",
    ]
    return "\n".join(lineas)
