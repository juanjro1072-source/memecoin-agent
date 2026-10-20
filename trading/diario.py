"""Escribe las autopsias (regla 5) y el resumen del día en diario/."""

from __future__ import annotations

from pathlib import Path

from .mercado import Ejecucion
from .modelos import Candidato, Posicion

_VERDAD = {"sano": "un token SANO", "rug": "un RUG-PULL", "honeypot": "un HONEYPOT"}


def _usd(x: float) -> str:
    return f"{'-' if x < 0 else ''}${abs(x):,.2f}"


def _con_signo(x: float) -> str:
    return ("+" if x >= 0 else "") + _usd(x)


def _billeteras(b: dict) -> str:
    def dato(clave, formato):
        return "sin dato" if b.get(clave) is None else formato(b[clave])
    return (f"top 10 con {dato('top10_pct', lambda v: f'{v:.0f}%')}, "
            f"creador con {dato('creador_pct', lambda v: f'{v:.0f}%')}, "
            f"liquidez bloqueada: {dato('liquidez_bloqueada', lambda v: 'sí' if v else 'NO')}, "
            f"wallets coordinadas: {dato('wallets_coordinadas', str)}")


def _cabecera(c: Candidato, fecha: str, titulo: str = "") -> list[str]:
    t, v = c.token, c.veredicto
    s = v.snap
    return [
        f"# Autopsia: ${t.simbolo} · {fecha} {c.hora}{titulo}",
        "",
        "- **Modo:** sombra (dinero ficticio)",
        f"- **Token:** {t.nombre}, {t.cadena}, `{t.direccion}`",
        "",
        "## Qué vio",
        "",
        f"- Hype: {v.hype} · Riesgo: {v.risk} · Arquetipo: {v.archetype}",
        f"- Precio ${c.precio_visto:.8g} · liquidez ${s.liquidity_usd:,.0f} · "
        f"FDV ${s.fdv:,.0f} · edad {s.age_minutes:.0f} min",
        "- Por qué tenía hype: " + ("; ".join(v.hype_reasons) or "sin motivo claro"),
        "- Banderas rojas del radar: " + ("; ".join(v.risk_flags) or "ninguna"),
        "- Revisión de wallets: " + _billeteras(t.billeteras),
        "",
    ]


class Diario:
    def __init__(self, carpeta: Path, fecha: str):
        self.carpeta = carpeta
        self.fecha = fecha
        carpeta.mkdir(parents=True, exist_ok=True)

    def _guardar(self, hora: str, simbolo: str, tipo: str, lineas: list[str]) -> Path:
        base = f"{hora.replace(':', '')}_{simbolo}_{tipo}"
        ruta, n = self.carpeta / f"{base}.md", 2
        while ruta.exists():
            ruta, n = self.carpeta / f"{base}-{n}.md", n + 1
        ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")
        return ruta

    def rechazo(self, c: Candidato, tipo: str, motivos: list[str]) -> Path:
        lineas = _cabecera(c, self.fecha, " (rechazada)") + [
            "## Qué decidió",
            "",
            f"- Acción: **no operar** (lo frenó la revisión de {tipo})",
            *[f"- {m}" for m in motivos],
            "",
            "## Qué resultó",
            "",
            "- No se gastó nada.",
            "- Cómo le fue al token después aparece en `RESUMEN.md`.",
        ]
        return self._guardar(c.hora, c.token.simbolo, "rechazada", lineas)

    def compra_fallida(self, c: Candidato, monto: float, ej: Ejecucion) -> Path:
        lineas = _cabecera(c, self.fecha, " (compra fallida)") + [
            "## Qué decidió",
            "",
            f"- Acción: comprar {_usd(monto)}",
            "",
            "## Qué resultó",
            "",
            f"- La compra **falló**: {ej.motivo}.",
            f"- Se perdió la comisión de red: {_usd(ej.comision_red)}.",
            "- Lección: en cadenas congestionadas o pools pequeños, hasta intentar cuesta dinero.",
        ]
        return self._guardar(c.hora, c.token.simbolo, "fallida", lineas)

    def operacion(self, p: Posicion) -> Path:
        c, t, compra = p.cand, p.cand.token, p.compra
        resultado = p.resultado_usd()
        pct = resultado / p.costo * 100 if p.costo else 0
        if p.venta:
            salida = (f"salida {p.hora_salida} a ${p.venta.precio:.8g} "
                      f"(slippage {p.venta.slippage_pct:.1f}%) · motivo: {p.motivo_salida}")
        elif p.atrapada:
            salida = "**no se pudo vender**: tokens atrapados, valen $0 para ti"
        else:
            salida = f"sigue abierta: valor estimado {_usd(p.valor_actual())} a ${t.precio:.8g}"
        comisiones = compra.comision_red + compra.comision_dex + p.comisiones_venta + (p.venta.comision_dex if p.venta else 0)
        lineas = _cabecera(c, self.fecha) + [
            "## Qué decidió",
            "",
            f"- Acción: **comprar** {_usd(compra.usd)} ({p.nota_monto})",
            f"- Razón: hype {c.veredicto.hype} y riesgo {c.veredicto.risk}; pasó la revisión de wallets",
            "",
            "## Qué resultó",
            "",
            f"- Entrada {p.hora_entrada} a ${compra.precio:.8g} (slippage {compra.slippage_pct:.1f}%) → {salida}",
            f"- Resultado: **{_con_signo(resultado)} ({pct:+.1f}%)** contando todas las comisiones",
            f"- Comisiones pagadas: {_usd(comisiones)}",
            *[f"- {e}" for e in p.eventos],
            f"- La verdad (sólo el simulador la conoce): era {_VERDAD[t.destino]}.",
            f"- Lección: {_leccion(p)}",
        ]
        return self._guardar(p.hora_entrada, t.simbolo, "operacion", lineas)

    def resumen(self, texto: str) -> Path:
        ruta = self.carpeta / "RESUMEN.md"
        ruta.write_text(texto, encoding="utf-8")
        return ruta


class DiarioNulo:
    """No escribe autopsias. Lo usa el laboratorio, que guarda un registro compacto."""

    def rechazo(self, *args) -> None: ...
    def compra_fallida(self, *args) -> None: ...
    def operacion(self, *args) -> None: ...
    def resumen(self, *args) -> None: ...


def _leccion(p: Posicion) -> str:
    t = p.cand.token
    if p.atrapada:
        return ("caímos en un honeypot: se podía comprar pero no vender. "
                "Revisa qué señales tenía arriba para afinar los filtros.")
    if p.vendida_tras_rug:
        return "rug-pull: el creador retiró la liquidez y el precio se desplomó antes de poder salir."
    if t.destino == "rug" and p.cerrada:
        return "era un rug-pull, pero se salió antes de que pasara. Suerte más que mérito."
    if p.resultado_usd() > 0:
        return "el plan funcionó. Fíjate cuánto se llevaron las comisiones de la ganancia."
    if not p.cerrada:
        return "la simulación se detuvo con la posición abierta."
    return "pérdida controlada: el plan de salida evitó que fuera peor."


def texto_resumen(sim) -> str:
    cfg = sim.cfg
    abiertas_valor = sum(p.valor_actual() for p in sim.abiertas)
    final = sim.caja + abiertas_valor
    resultado = final - cfg.saldo_inicial
    cerradas = [p for p in sim.posiciones if p.cerrada]
    ganadoras = [p for p in cerradas if p.resultado_usd() > 0]
    seg = [r for r in sim.rechazos if r[1] == "seguridad"]
    esquivadas = [r for r in seg if r[0].token.es_estafa]
    honeypots = [p for p in sim.posiciones if p.cand.token.destino == "honeypot"]
    rugs = [p for p in sim.posiciones if p.vendida_tras_rug]
    pct = lambda a, b: f"{a / b * 100:.0f}%" if b else "—"

    lineas = [f"# Resumen del día · {sim.fecha} (modo sombra, semilla {sim.semilla})", ""]
    if sim.parado_en:
        lineas += [f"> ⛔ Simulación detenida a las {sim.parado_en} porque existe `PARAR.txt`.", ""]
    lineas += [
        "## Dinero (ficticio)",
        "",
        f"- Saldo inicial: {_usd(cfg.saldo_inicial)}",
        f"- Saldo final: {_usd(final)} (efectivo {_usd(sim.caja)} + posiciones abiertas {_usd(abiertas_valor)})",
        f"- **Ganancia/pérdida: {_con_signo(resultado)} ({resultado / cfg.saldo_inicial * 100:+.2f}%)**",
        f"- Comisiones pagadas: {_usd(sim.comisiones)} · dinero perdido por slippage: {_usd(sim.coste_slippage)}",
        "",
        "## Operaciones",
        "",
        f"- Tokens que vio el radar: {sim.vistos} · con hype suficiente: {sim.candidatos}",
        f"- Compras: {len(sim.posiciones)} hechas, {len(sim.fallidas)} fallidas",
        f"- Ventas: {len(cerradas)} hechas, {sim.ventas_fallidas} intentos fallidos",
        f"- Rechazadas por seguridad: {len(seg)} · por límites de dinero: {len(sim.rechazos) - len(seg)}",
        f"- Abiertas al final: {len(sim.abiertas)}",
        "",
        "## Aciertos",
        "",
        f"- Operaciones con ganancia: {len(ganadoras)} de {len(cerradas)} cerradas ({pct(len(ganadoras), len(cerradas))})",
        f"- Estafas esquivadas por la revisión: {len(esquivadas)} de {len(seg)} rechazos ({pct(len(esquivadas), len(seg))})",
        f"- Trampas en las que caímos: {len(honeypots)} honeypot(s), {len(rugs)} rug-pull(s)",
        "",
    ]
    if sim.posiciones:
        lineas += ["## Detalle de operaciones", "",
                   "| Entrada | Token | Resultado | Salida | Era |", "|---|---|---|---|---|"]
        for p in sim.posiciones:
            salida = p.motivo_salida or ("atrapada" if p.atrapada else "abierta")
            lineas.append(f"| {p.hora_entrada} | ${p.cand.token.simbolo} | {_con_signo(p.resultado_usd())} "
                          f"| {salida} | {p.cand.token.destino} |")
        lineas.append("")
    if seg:
        lineas += ["## Rechazos por seguridad: ¿acertamos?", "",
                   "| Hora | Token | Era | Veredicto |", "|---|---|---|---|"]
        for c, _, _ in seg:
            t = c.token
            if t.es_estafa:
                veredicto = "✅ estafa esquivada"
            else:
                cambio = (t.precio / c.precio_visto - 1) * 100
                veredicto = f"era sano: {cambio:+.0f}% hasta el final" + (" (oportunidad perdida)" if cambio > 0 else "")
            lineas.append(f"| {c.hora} | ${t.simbolo} | {t.destino} | {veredicto} |")
        lineas.append("")
    return "\n".join(lineas)
