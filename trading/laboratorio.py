"""Laboratorio de estrategias: prueba ajustes en días simulados sin hacer trampa.

    python -m trading.laboratorio

1. ENTRENAMIENTO: prueba todas las combinaciones de ajustes en los primeros
   días y elige la que más gana.
2. VALIDACIÓN: sólo entonces corre la elegida (y tu configuración actual) en
   los últimos días, que nadie ha visto todavía.
3. Compara todo contra un "mono con dardos" que compra al azar con los mismos
   costos. Si no le gana claramente, la estrategia no sirve.

Sólo LEE config/limites.toml; nunca lo modifica. Los datos son INVENTADOS
(salen de trading/mercado.py), no del mercado real.
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import gzip
import hashlib
import itertools
import random
import statistics
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from . import RAIZ, config
from .interruptor import RUTA_PARAR, hay_que_parar
from .simulador import Mono, Simulador

TOKENS_POR_DIA = 60
REJILLA = {
    "hype_minimo": (50, 60, 70),
    "riesgo_maximo": (30, 40, 50),
    "tomar_ganancia_pct": (30, 50, 80),
    "cortar_perdida_pct": (15, 25, 40),
}
_COLUMNAS = ["fase", "estrategia", "semilla", "hora", "token", "tipo", "hype", "riesgo",
             "decision", "motivo", "resultado_usd", "era"]


class Detenido(Exception):
    pass


@dataclass
class Dia:
    semilla: int
    resultado: float
    compras: int
    cerradas: int
    ganadoras: int
    honeypots: int
    rugs: int


def nombre(cfg: config.Config) -> str:
    return (f"hype ≥ {cfg.hype_minimo:g}, riesgo ≤ {cfg.riesgo_maximo:g}, "
            f"vender a +{cfg.tomar_ganancia_pct:g}% / -{cfg.cortar_perdida_pct:g}%")


def huella(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _registrar(escritor, fase: str, etiqueta: str, sim: Simulador) -> None:
    """Registro compacto (regla 5): una línea por operación, rechazo o fallo."""
    for p in sim.posiciones:
        v = p.cand.veredicto
        escritor.writerow([fase, etiqueta, sim.semilla, p.hora_entrada, p.cand.token.simbolo, "operacion",
                           v.hype, v.risk, f"comprar {p.compra.usd:.2f}",
                           p.motivo_salida or ("atrapada" if p.atrapada else "abierta"),
                           f"{p.resultado_usd():.4f}", p.cand.token.destino])
    for c, tipo, motivos in sim.rechazos:
        escritor.writerow([fase, etiqueta, sim.semilla, c.hora, c.token.simbolo, "rechazada",
                           c.veredicto.hype, c.veredicto.risk, f"no operar ({tipo})",
                           "; ".join(motivos), "", c.token.destino])
    for c, motivo in sim.fallidas:
        escritor.writerow([fase, etiqueta, sim.semilla, c.hora, c.token.simbolo, "fallida",
                           c.veredicto.hype, c.veredicto.risk, "comprar", motivo, "", c.token.destino])


def correr_dia(cfg, semilla, escritor, fase, etiqueta, mono=None, carpeta=None) -> Dia:
    if hay_que_parar():  # regla 3: también antes de cada día del laboratorio
        raise Detenido
    if mono is None:
        sim = Simulador(cfg, semilla, TOKENS_POR_DIA, carpeta)
    else:
        sim = Mono(cfg, semilla, TOKENS_POR_DIA, carpeta, numero_mono=mono)
    sim.correr()
    if sim.parado_en:
        raise Detenido
    _registrar(escritor, fase, etiqueta, sim)
    cerradas = [p for p in sim.posiciones if p.cerrada]
    return Dia(
        semilla=semilla,
        resultado=sim.caja + sum(p.valor_actual() for p in sim.abiertas) - cfg.saldo_inicial,
        compras=len(sim.posiciones),
        cerradas=len(cerradas),
        ganadoras=sum(p.resultado_usd() > 0 for p in cerradas),
        honeypots=sum(p.cand.token.destino == "honeypot" for p in sim.posiciones),
        rugs=sum(p.vendida_tras_rug for p in sim.posiciones),
    )


def intervalo_95(valores: list[float], semilla: int = 0, repeticiones: int = 5000) -> tuple[float, float]:
    """Intervalo de confianza del promedio por remuestreo (bootstrap)."""
    rng = random.Random(semilla)
    medias = sorted(statistics.fmean(rng.choices(valores, k=len(valores))) for _ in range(repeticiones))
    return medias[int(0.025 * repeticiones)], medias[int(0.975 * repeticiones) - 1]


@dataclass
class Resultado:
    etiqueta: str
    cfg: config.Config
    dias: list[Dia]
    por_dia: int = 1  # el mono suma n monos por día: sus trampas se dividen entre n

    @property
    def media(self) -> float:
        return statistics.fmean(d.resultado for d in self.dias)

    def fila(self) -> str:
        cerradas = sum(d.cerradas for d in self.dias)
        ganadoras = sum(d.ganadoras for d in self.dias)
        positivos = sum(d.resultado > 0 for d in self.dias)
        trampas = lambda campo: f"{sum(getattr(d, campo) for d in self.dias) / self.por_dia:.4g}"
        return (f"| {self.etiqueta} | {_usd(self.media)} | {_usd(sum(d.resultado for d in self.dias))} "
                f"| {positivos / len(self.dias):.0%} | {ganadoras / cerradas:.0%} "
                f"| {trampas('honeypots')} | {trampas('rugs')} |"
                if cerradas else f"| {self.etiqueta} | {_usd(self.media)} | — | — | — | — | — |")


def _usd(x: float) -> str:
    return f"{'-' if x < 0 else '+'}${abs(x):,.2f}"


def promedio_monos(cfg, semillas, n_monos, escritor, fase, etiqueta, carpeta=None) -> Resultado:
    """Un 'día del mono' es el promedio de n monos distintos ese mismo día."""
    dias = []
    for s in semillas:
        monos = [correr_dia(cfg, s, escritor, fase, f"{etiqueta} #{m}", mono=m,
                            carpeta=carpeta / f"dia-{s}" if carpeta and m == 0 else None)
                 for m in range(n_monos)]
        dias.append(Dia(s, statistics.fmean(d.resultado for d in monos),
                        sum(d.compras for d in monos), sum(d.cerradas for d in monos),
                        sum(d.ganadoras for d in monos), sum(d.honeypots for d in monos),
                        sum(d.rugs for d in monos)))
    return Resultado(f"🐒 mono ({etiqueta}, promedio de {n_monos})", cfg, dias, por_dia=n_monos)


def comparar(estrategia: Resultado, otra: Resultado) -> tuple[float, float, float, bool]:
    """Compara día a día (mismos días). True si gana claramente (intervalo 95 % > 0)."""
    assert [d.semilla for d in estrategia.dias] == [d.semilla for d in otra.dias]
    difs = [a.resultado - b.resultado for a, b in zip(estrategia.dias, otra.dias)]
    bajo, alto = intervalo_95(difs)
    return statistics.fmean(difs), bajo, alto, bajo > 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="trading.laboratorio", description=__doc__.split("\n")[0])
    parser.add_argument("--dias", type=int, default=200)
    parser.add_argument("--entrenamiento", type=int, default=140, help="días para elegir ajustes")
    parser.add_argument("--monos", type=int, default=10, help="monos por día")
    args = parser.parse_args(argv)
    if not 0 < args.entrenamiento < args.dias:
        parser.error("--entrenamiento tiene que estar entre 1 y --dias - 1")

    if hay_que_parar():
        print(f"⛔ Existe {RUTA_PARAR.name}: no arranco.")
        return 1
    try:
        actual = config.cargar()
    except config.ConfigError as e:
        print(f"⛔ No arranco: {e}")
        return 1
    huella_inicial = huella(config.RUTA_CONFIG)

    entrenamiento = list(range(args.entrenamiento))
    validacion = list(range(args.entrenamiento, args.dias))
    assert not set(entrenamiento) & set(validacion)

    carpeta = RAIZ / "informes" / f"laboratorio_{date.today().isoformat()}"
    carpeta.mkdir(parents=True, exist_ok=True)
    claves = list(REJILLA)
    variantes = [dataclasses.replace(actual, **dict(zip(claves, valores)))
                 for valores in itertools.product(*REJILLA.values())]
    if actual not in variantes:
        variantes.append(actual)

    try:
        with gzip.open(carpeta / "registro_compacto.csv.gz", "wt", newline="", encoding="utf-8") as f:
            escritor = csv.writer(f)
            escritor.writerow(_COLUMNAS)

            # ---- Fase 1: entrenamiento (los días de validación no se tocan) ----
            ranking = []
            for i, v in enumerate(variantes, 1):
                dias = [correr_dia(v, s, escritor, "entrenamiento", nombre(v)) for s in entrenamiento]
                ranking.append(Resultado(nombre(v), v, dias))
                if i % 10 == 0 or i == len(variantes):
                    print(f"  entrenamiento: {i}/{len(variantes)} combinaciones", file=sys.stderr)
            ranking.sort(key=lambda r: r.media, reverse=True)
            elegida = ranking[0]
            actual_ent = next(r for r in ranking if r.cfg == actual)
            mono_ent = promedio_monos(elegida.cfg, entrenamiento, args.monos, escritor, "entrenamiento", "elegida")

            # ---- Fase 2: validación, una sola vez y al final ----
            print("  validación en los días nunca vistos…", file=sys.stderr)
            val = carpeta / "validacion"
            finalistas = [("elegida", elegida.cfg)] + ([("actual", actual)] if actual != elegida.cfg else [])
            resultados_val = {}
            for slug, cfg in finalistas:
                dias = [correr_dia(cfg, s, escritor, "validacion", slug, carpeta=val / slug / f"dia-{s}")
                        for s in validacion]
                mono = promedio_monos(cfg, validacion, args.monos, escritor, "validacion", slug,
                                      carpeta=val / f"mono_{slug}")
                resultados_val[slug] = (Resultado(f"estrategia {slug}", cfg, dias), mono)
    except Detenido:
        print(f"⛔ Laboratorio detenido: apareció {RUTA_PARAR.name}. No hay informe.")
        return 1

    if huella(config.RUTA_CONFIG) != huella_inicial:
        print("⚠️ limites.toml cambió mientras corría el laboratorio (no fue el laboratorio). "
              "Vuelve a correrlo para que los resultados correspondan a tu archivo.")

    texto = informe(args, actual, ranking, elegida, actual_ent, mono_ent, resultados_val)
    (carpeta / "INFORME.md").write_text(texto, encoding="utf-8")
    print(texto)
    print(f"📓 Informe en {(carpeta / 'INFORME.md').relative_to(RAIZ)}")
    return 0


def informe(args, actual, ranking, elegida, actual_ent, mono_ent, resultados_val) -> str:
    e, v0, v1 = args.entrenamiento, args.entrenamiento, args.dias - 1
    encabezado = "| Estrategia | Media por día | Total | Días en positivo | Ventas con ganancia | Honeypots | Rug-pulls |"
    separador = "|---|---|---|---|---|---|---|"
    lineas = [
        f"# Laboratorio de estrategias · {date.today().isoformat()}",
        "",
        "> ⚠️ **Datos INVENTADOS.** Los días salen del mercado simulado de",
        "> `trading/mercado.py`, no del mercado real. Los resultados dicen cómo se",
        "> portan las estrategias en ese mundo inventado, no cuánto ganarías de verdad.",
        "",
        "## Cómo se hizo",
        "",
        f"- {args.dias} días simulados de {TOKENS_POR_DIA} tokens cada uno.",
        f"- **Entrenamiento:** días 0 a {e - 1}. Ahí se probaron {len(ranking)} combinaciones de ajustes.",
        f"- **Validación:** días {v0} a {v1}. No se usaron para elegir; se corrieron una sola vez al final.",
        f"- **Mono con dardos:** {args.monos} monos por día compran tokens al azar, sin radar ni revisión,",
        "  con los mismos límites de dinero, comisiones, slippage y reglas de venta.",
        "- **«Le gana claramente»** = la ganancia diaria de la estrategia menos la del mono, en los",
        "  mismos días, tiene un intervalo de confianza del 95 % completamente por encima de $0.",
        f"- Límites de dinero usados (de tu `limites.toml`, sin tocar): ${actual.max_por_operacion:g} por",
        f"  operación, ${actual.max_por_dia:g} por día, ${actual.max_por_wallet:g} por wallet.",
        "",
        "## Fase 1 · Entrenamiento: las 10 mejores combinaciones",
        "",
        encabezado, separador,
        *[r.fila().replace(r.etiqueta, f"{i}. {r.etiqueta}" + (" ← tu config actual" if r.cfg == actual else ""), 1)
          for i, r in enumerate(ranking[:10], 1)],
        "",
        f"- Tu configuración actual quedó en el puesto {ranking.index(actual_ent) + 1} de {len(ranking)}"
        f" ({_usd(actual_ent.media)} por día).",
        f"- El mono (con las reglas de venta de la elegida) hizo {_usd(mono_ent.media)} por día.",
        "",
        f"## Fase 2 · Validación: {v1 - v0 + 1} días nunca vistos",
        "",
        encabezado, separador,
    ]
    for estrategia, mono in resultados_val.values():
        lineas += [estrategia.fila(), mono.fila()]
    lineas += ["", "### ¿Le ganan al mono?", ""]
    veredictos = {}
    for slug, (estrategia, mono) in resultados_val.items():
        media, bajo, alto, gana = comparar(estrategia, mono)
        veredictos[slug] = gana
        lineas.append(f"- **{slug.capitalize()}** ({nombre(estrategia.cfg)}): {_usd(media)} por día frente al mono "
                      f"(intervalo 95 %: {_usd(bajo)} a {_usd(alto)}) → "
                      + ("✅ le gana claramente." if gana else "❌ **no** le gana claramente: no sirve."))
    elegida_val = resultados_val["elegida"][0]
    supera_actual = None
    if "actual" in resultados_val:
        media, bajo, alto, supera_actual = comparar(elegida_val, resultados_val["actual"][0])
        lineas += ["", "### ¿La elegida es mejor que tu configuración actual?", "",
                   f"- {_usd(media)} por día a favor de la elegida (intervalo 95 %: {_usd(bajo)} a {_usd(alto)}) → "
                   + ("✅ sí, claramente." if supera_actual else "❌ **no** está claro: la diferencia puede ser suerte.")]
    perdedoras = [slug for slug, (r, _) in resultados_val.items() if r.media < 0]
    lineas += ["", "### ¿Gana dinero?", ""]
    if perdedoras:
        lineas.append(f"- **No.** En validación pierden dinero: {', '.join(perdedoras)}. Ganarle al mono sólo "
                      "demuestra que los filtros esquivan estafas, no que la estrategia sea rentable.")
    else:
        lineas.append("- En validación ninguna pierde dinero en promedio (recuerda: mercado inventado).")
    lineas += [
        "",
        "### ¿Se infló en el entrenamiento?",
        "",
        f"- La elegida ganaba {_usd(elegida.media)} por día en entrenamiento y {_usd(elegida_val.media)} en validación.",
        "  Si baja mucho, parte de su «éxito» era suerte de esos días concretos.",
        "",
        "## Qué podrías cambiar en `limites.toml` (lo decides tú)",
        "",
    ]
    cambios = [(k, getattr(actual, k), getattr(elegida.cfg, k)) for k in REJILLA if getattr(actual, k) != getattr(elegida.cfg, k)]
    if not cambios:
        lineas.append("- **Nada.** Tu configuración actual ya es la elegida.")
    elif not veredictos.get("elegida"):
        lineas.append("- **Nada.** La elegida no le gana claramente al mono en validación.")
    elif not supera_actual:
        lineas.append("- **Nada por ahora.** La elegida no le gana claramente a tu configuración actual en "
                      "validación. Si aun así quisieras probarla, estos serían los cambios:")
        lineas += [f"  - `{k}`: de {a:g} a {b:g}" for k, a, b in cambios]
    else:
        lineas.append("- La elegida le gana claramente al mono y a tu configuración actual. Cambios posibles:")
        lineas += [f"  - `{k}`: de {a:g} a {b:g}" for k, a, b in cambios]
    lineas += ["", "No se modificó `limites.toml`.", ""]
    return "\n".join(lineas)


if __name__ == "__main__":
    sys.exit(main())
