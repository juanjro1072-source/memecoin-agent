"""El ciclo del observador en vivo (MODO SOMBRA, sólo lectura).

Cada ciclo (por defecto cada 2 minutos):
  1. Si existe PARAR.txt, se detiene.
  2. Anota el precio a 1 h y a 24 h de las decisiones que ya cumplieron ese tiempo.
  3. Vuelve a leer limites.toml (si lo cambias, se aplica en el siguiente ciclo).
  4. Pide a DexScreener los tokens nuevos de Solana y decide sobre cada uno:
     radar → revisión anti-estafa (RugCheck) → límites → compra imaginaria.
     Antes de cada decisión vuelve a mirar PARAR.txt.
  5. Reescribe el resumen del día.
"""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from radar.scoring import evaluate
from trading import config
from trading.interruptor import RUTA_PARAR, hay_que_parar
from trading.seguridad import motivo_radar, revisar

from . import informes
from .costos import simular_compra, valor_venta
from .fuentes import CADENAS, SIN_DATOS, FuentesReales
from .registro import Registro

MONTO_MINIMO_USD = 1.0
_ERRORES_RED = (OSError, ValueError)  # sin conexión, servidor caído, respuesta rara


def _num(valor) -> float | None:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


class Observador:
    def __init__(self, carpeta: Path, fuentes=None, ruta_config: Path = config.RUTA_CONFIG,
                 ruta_parar: Path = RUTA_PARAR, ahora=time.time, dormir=time.sleep, salida=print):
        self.carpeta = carpeta
        self.db = Registro(carpeta / "sombra.db")
        self.fuentes = fuentes or FuentesReales()
        self.ruta_config = ruta_config
        self.ruta_parar = ruta_parar
        self.ahora = ahora
        self.dormir = dormir
        self.salida = salida
        self.cfg: config.Config | None = None

    def log(self, texto: str) -> None:
        self.salida(f"{informes.hora(self.ahora())}  {texto}")

    def _fecha(self, ts: float) -> str:
        return datetime.fromtimestamp(ts).date().isoformat()

    def _puedo(self) -> bool:
        return not hay_que_parar(self.ruta_parar)

    # ---------- bucle ----------

    def correr(self, cada: int) -> int:
        if not self._puedo():
            self.salida(f"⛔ Existe {self.ruta_parar.name}: no arranco. Bórralo cuando quieras seguir.")
            return 1
        self.salida(f"👀 Observador en MODO SOMBRA (precios reales, dinero ficticio). Ciclo cada {cada} s.\n"
                    f"   Para detenerlo: Ctrl+C, o crea el archivo {self.ruta_parar.name} en la carpeta del proyecto.\n")
        try:
            while self.ciclo():
                for _ in range(max(1, cada // 5)):  # dormir a ratos para notar PARAR.txt enseguida
                    if not self._puedo():
                        break
                    self.dormir(5)
            self.salida(f"\n⛔ Detenido porque existe {self.ruta_parar.name}. Bórralo para poder arrancar otra vez.")
        except KeyboardInterrupt:
            self.salida("\n👋 Detenido con Ctrl+C.")
        finally:
            if self.cfg:
                ruta = self.escribir_resumenes(self.cfg)
                self.salida(f"📓 Resumen del día: {ruta}")
        return 0

    def ciclo(self) -> bool:
        """Un ciclo completo. Devuelve False si hay que detenerse."""
        if not self._puedo():
            return False
        self.seguimiento()
        try:
            self.cfg = config.cargar(self.ruta_config)
        except config.ConfigError as e:
            self.log(f"⛔ No decido nada en este ciclo: {e}")
            return True
        if self.cfg.modo != "sombra":
            self.log("Aviso: limites.toml dice modo = \"real\", pero este observador es SÓLO sombra: nunca toca dinero.")
        try:
            pares = self.fuentes.descubrir()
        except _ERRORES_RED as e:
            self.log(f"⚠️ No pude hablar con DexScreener ({e}). Reintento en el próximo ciclo.")
            pares = []
        decisiones = 0
        for par in pares:
            if not self._puedo():
                return False
            decisiones += self.considerar(par, self.cfg)
        self.escribir_resumenes(self.cfg)
        self.log(f"🔍 {len(pares)} tokens revisados · {decisiones} decisiones nuevas")
        return True

    # ---------- decidir ----------

    def considerar(self, par: dict, cfg: config.Config) -> int:
        cadena = par.get("chainId")
        base = par.get("baseToken") or {}
        token = base.get("address")
        if cadena not in CADENAS or not token:
            return 0
        ahora = self.ahora()
        fecha = self._fecha(ahora)
        self.db.marcar_visto(fecha, cadena, token)
        if self.db.ya_decidido(cadena, token):
            return 0  # cada token se decide una sola vez
        v = evaluate(par, now=ahora)
        if v.hype < cfg.hype_minimo:
            return 0  # todavía no interesa; se volverá a mirar si aparece otra vez

        precio = _num(par.get("priceUsd"))
        liquidez = _num((par.get("liquidity") or {}).get("usd")) or 0.0
        fila = {
            "momento": ahora, "fecha": fecha, "cadena": cadena, "token": token,
            "simbolo": base.get("symbol") or "?", "nombre": base.get("name") or "?",
            "par": par.get("pairAddress"), "dex": par.get("dexId"), "url": par.get("url"),
            "hype": v.hype, "riesgo": v.risk, "arquetipo": v.archetype,
            "razones_hype": v.hype_reasons, "banderas": v.risk_flags,
            "precio": precio, "liquidez": liquidez, "fdv": v.snap.fdv,
        }
        radar = motivo_radar(v, cfg)
        if not precio or precio <= 0:
            fila.update(accion="rechazo", tipo="precio", motivos=["DexScreener no dio un precio válido: no se opera"])
        elif radar:
            fila.update(accion="rechazo", tipo="seguridad", motivos=[radar])
        else:
            try:
                billeteras, extra = self.fuentes.wallets(cadena, token)
            except _ERRORES_RED as e:
                billeteras, extra = dict(SIN_DATOS), [f"no se pudo consultar RugCheck ({e}): ante la duda no se opera"]
            fila["billeteras"] = billeteras
            motivos = revisar(v, billeteras, cfg) + extra
            monto, nota = self._monto(cfg, fecha)
            if motivos:
                fila.update(accion="rechazo", tipo="seguridad", motivos=motivos)
            elif monto < MONTO_MINIMO_USD:
                fila.update(accion="rechazo", tipo="límites", motivos=[f"no queda margen: se alcanzó el {nota}"])
            else:
                if not self._puedo():  # regla 3: justo antes de "operar"
                    return 0
                c = simular_compra(monto, precio, liquidez, cadena, fila["dex"], cfg.slippage_maximo_pct)
                fila.update(monto=monto, nota_monto=nota, comision_red=c.comision_red, slippage_pct=c.slippage_pct)
                if c.ok:
                    fila.update(accion="compra", precio_entrada=c.precio_entrada, cantidad=c.cantidad,
                                comision_dex=c.comision_dex)
                else:
                    fila.update(accion="fallida", motivos=[c.motivo])

        id_ = self.db.guardar(fila)
        self._autopsia(id_)
        detalle = {"compra": f"🟢 compra sombra ${fila.get('monto', 0):.2f}",
                   "fallida": "🟠 compra que fallaría", "rechazo": f"🔴 rechazada ({fila.get('tipo')})"}
        self.log(f"${fila['simbolo']}: {detalle[fila['accion']]} · hype {v.hype}, riesgo {v.risk}")
        return 1

    def _monto(self, cfg: config.Config, fecha: str) -> tuple[float, str]:
        """Regla 2: el menor de los límites de limites.toml."""
        efectivo, _ = informes.saldo(self.db.todas(), cfg.saldo_inicial)
        opciones = [
            (cfg.max_por_operacion, f"máximo por operación (${cfg.max_por_operacion:g})"),
            (cfg.max_por_dia - self.db.gastado(fecha), f"límite por día (${cfg.max_por_dia:g})"),
            (cfg.max_por_wallet - self.db.invertido_abierto(), f"límite por wallet (${cfg.max_por_wallet:g})"),
            (efectivo - 5, "saldo ficticio disponible"),
        ]
        return min(opciones, key=lambda o: o[0])

    # ---------- seguimiento a 1 h y 24 h ----------

    def seguimiento(self) -> None:
        ahora = self.ahora()
        pendientes = self.db.pendientes(ahora)
        por_cadena: dict[str, list[dict]] = defaultdict(list)
        for r in pendientes:
            por_cadena[r["cadena"]].append(r)
        for cadena, filas in por_cadena.items():
            try:
                pares = self.fuentes.precios(cadena, sorted({r["token"] for r in filas}))
            except _ERRORES_RED as e:
                self.log(f"⚠️ No pude actualizar precios ({e}). Reintento en el próximo ciclo.")
                continue
            for r in filas:
                p = self._par_de(r, pares)
                precio = _num(p.get("priceUsd")) if p else None
                liquidez = _num((p.get("liquidity") or {}).get("usd")) if p else None
                campos = {}
                for h, segundos in (("1h", 3600), ("24h", 86400)):
                    if r[f"momento_{h}"] is None and r["momento"] + segundos <= ahora:
                        campos.update({f"momento_{h}": ahora, f"precio_{h}": precio, f"liquidez_{h}": liquidez})
                        if r["accion"] == "compra":
                            campos[f"valor_{h}"] = valor_venta(r["cantidad"], precio, liquidez, cadena, r["dex"])[0]
                if campos:
                    self.db.actualizar(r["id"], **campos)
                    self._autopsia(r["id"])
                    r = self.db.obtener(r["id"])
                    if "momento_24h" in campos and r["accion"] == "compra":
                        self.log(f"${r['simbolo']}: resultado a 24 h {informes._con_signo(r['valor_24h'] - informes.costo(r))}")

    @staticmethod
    def _par_de(r: dict, pares: list[dict]) -> dict | None:
        del_token = [p for p in pares if (p.get("baseToken") or {}).get("address") == r["token"]]
        mismo = [p for p in del_token if p.get("pairAddress") == r["par"]]
        if mismo:
            return mismo[0]
        return max(del_token, key=lambda p: _num((p.get("liquidity") or {}).get("usd")) or 0, default=None)

    # ---------- archivos ----------

    def _autopsia(self, id_: int) -> None:
        r = self.db.obtener(id_)
        tp = self.cfg.tomar_ganancia_pct if self.cfg else 50
        if r["archivo"]:
            ruta = self.carpeta / r["archivo"]
        else:
            momento = datetime.fromtimestamp(r["momento"])
            dia = self.carpeta / r["fecha"]
            dia.mkdir(parents=True, exist_ok=True)
            base = f"{momento:%H%M}_{r['simbolo']}_{r['accion']}".replace("/", "-")
            ruta, n = dia / f"{base}.md", 2
            while ruta.exists():
                ruta, n = dia / f"{base}-{n}.md", n + 1
            self.db.actualizar(id_, archivo=str(ruta.relative_to(self.carpeta)))
        ruta.write_text(informes.autopsia(r, tp), encoding="utf-8")

    def escribir_resumenes(self, cfg: config.Config) -> Path:
        """Reescribe el resumen de hoy y el de ayer (sus 24 h se completan hoy)."""
        ahora = self.ahora()
        todas = self.db.todas()
        ruta = None
        for dias_atras in (1, 0):
            fecha = self._fecha(ahora - dias_atras * 86400)
            filas = [r for r in todas if r["fecha"] == fecha]
            if dias_atras and not filas:
                continue
            ruta = self.carpeta / f"resumen_{fecha}.md"
            ruta.write_text(informes.resumen_dia(fecha, filas, todas, self.db.vistos(fecha), cfg, ahora),
                            encoding="utf-8")
        return ruta
