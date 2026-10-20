"""El bucle del modo sombra: un día de mercado inventado, en pasos de 15 minutos.

En cada paso:
  1. comprueba PARAR.txt (y otra vez justo antes de cada operación)
  2. mueve los precios
  3. vende lo que llegó a su objetivo de ganancia o de pérdida
  4. mira los tokens nuevos: radar → revisión anti-estafa → límites → compra
Al final del día vende todo lo que pueda y escribe el resumen.
"""

from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta
from pathlib import Path

from radar.scoring import evaluate

from . import diario as diario_mod
from .config import Config
from .interruptor import RUTA_PARAR, hay_que_parar
from .mercado import PASO_MINUTOS, PASOS_POR_DIA, comprar, generar_tokens, vender
from .modelos import Candidato, Posicion
from .seguridad import revisar

MONTO_MINIMO_USD = 1.0
INTENTOS_HONEYPOT = 3  # tras 3 ventas bloqueadas, se da la posición por perdida


class Simulador:
    def __init__(self, cfg: Config, semilla: int, n_tokens: int, carpeta_diario: Path | None,
                 ruta_parar: Path = RUTA_PARAR, fecha: date | None = None):
        self.cfg = cfg
        self.semilla = semilla
        # Dos "dados" separados: el del mercado sólo depende de la semilla, así
        # el mismo día es idéntico para cualquier estrategia que lo opere.
        self.rng_mercado = random.Random(semilla)
        self.rng_ejecucion = random.Random(f"ejecucion-{semilla}")
        self.ruta_parar = ruta_parar
        self.fecha = (fecha or date.today()).isoformat()
        self.inicio = datetime.combine(fecha or date.today(), time())
        self.tokens = generar_tokens(self.rng_mercado, n_tokens, self.inicio.timestamp())
        # Sin carpeta no se escriben autopsias (el laboratorio guarda un registro compacto).
        self.diario = diario_mod.Diario(carpeta_diario, self.fecha) if carpeta_diario else diario_mod.DiarioNulo()

        self.caja = cfg.saldo_inicial
        self.gastado_hoy = 0.0
        self.comisiones = 0.0
        self.coste_slippage = 0.0
        self.posiciones: list[Posicion] = []
        self.rechazos: list[tuple[Candidato, str, list[str]]] = []
        self.fallidas: list[tuple[Candidato, str]] = []
        self.ventas_fallidas = 0
        self.vistos = 0
        self.candidatos = 0
        self.parado_en: str | None = None

    @property
    def abiertas(self) -> list[Posicion]:
        return [p for p in self.posiciones if not p.cerrada]

    def _hora(self, paso: int) -> str:
        return (self.inicio + timedelta(minutes=paso * PASO_MINUTOS)).strftime("%H:%M")

    def _puedo_operar(self, hora: str) -> bool:
        """Regla 3: se mira PARAR.txt justo antes de cada operación."""
        if self.parado_en is None and hay_que_parar(self.ruta_parar):
            self.parado_en = hora
        return self.parado_en is None

    # ---------- bucle principal ----------

    def correr(self) -> str:
        for paso in range(PASOS_POR_DIA):
            hora = self._hora(paso)
            if not self._puedo_operar(hora):
                break
            for t in self.tokens:
                t.avanzar(paso, self.rng_mercado)
            self._revisar_salidas(hora)
            for t in self.tokens:
                if t.paso_lanzamiento == paso and self.parado_en is None:
                    self._considerar(t, hora, paso)
            if self.parado_en:
                break
        else:
            self._cierre_del_dia()

        for p in self.abiertas:  # atrapadas en honeypot o abiertas por PARAR.txt
            self.diario.operacion(p)
        texto = diario_mod.texto_resumen(self)
        self.diario.resumen(texto)
        return texto

    # ---------- compras ----------

    def _considerar(self, t, hora: str, paso: int) -> None:
        ahora = self.inicio.timestamp() + paso * PASO_MINUTOS * 60
        veredicto = evaluate(t.par, now=ahora)
        self.vistos += 1
        if not self._interesa(veredicto):
            return  # no le interesa: no es una operación
        self.candidatos += 1
        cand = Candidato(t, veredicto, hora, t.precio)

        motivos = self._revision_seguridad(veredicto, t)
        if motivos:
            self._rechazar(cand, "seguridad", motivos)
            return
        monto, nota = self._monto_permitido()
        if monto < MONTO_MINIMO_USD:
            self._rechazar(cand, "límites", [f"no queda margen: se alcanzó el {nota}"])
            return
        if not self._puedo_operar(hora):
            return

        ej = comprar(self.rng_ejecucion, t, monto, self.cfg.slippage_maximo_pct)
        self.caja -= ej.comision_red
        self.comisiones += ej.comision_red + ej.comision_dex
        if not ej.ok:
            self.fallidas.append((cand, ej.motivo))
            self.diario.compra_fallida(cand, monto, ej)
            return
        self.caja -= ej.usd
        self.gastado_hoy += ej.usd
        self.coste_slippage += ej.usd * ej.slippage_pct / 100
        self.posiciones.append(Posicion(cand, ej, hora, nota))

    def _interesa(self, veredicto) -> bool:
        return veredicto.hype >= self.cfg.hype_minimo

    def _revision_seguridad(self, veredicto, t) -> list[str]:
        return revisar(veredicto, t.billeteras, self.cfg)

    def _monto_permitido(self) -> tuple[float, str]:
        """Regla 2: el monto es el menor de todos los límites de limites.toml."""
        cfg = self.cfg
        invertido = sum(p.compra.usd for p in self.abiertas)
        opciones = [
            (cfg.max_por_operacion, f"máximo por operación (${cfg.max_por_operacion:g})"),
            (cfg.max_por_dia - self.gastado_hoy, f"límite por día (${cfg.max_por_dia:g})"),
            (cfg.max_por_wallet - invertido, f"límite por wallet (${cfg.max_por_wallet:g})"),
            (self.caja - 5, "saldo ficticio disponible"),  # 5 $ de reserva para comisiones
        ]
        return min(opciones, key=lambda o: o[0])

    def _rechazar(self, cand: Candidato, tipo: str, motivos: list[str]) -> None:
        self.rechazos.append((cand, tipo, motivos))
        self.diario.rechazo(cand, tipo, motivos)

    # ---------- ventas ----------

    def _revisar_salidas(self, hora: str) -> None:
        for p in self.abiertas:
            if p.atrapada:
                continue
            cambio = (p.cand.token.precio / p.compra.precio - 1) * 100
            if cambio >= self.cfg.tomar_ganancia_pct:
                self._vender(p, hora, f"tomar ganancia ({cambio:+.0f}%)", self.cfg.slippage_maximo_pct)
            elif cambio <= -self.cfg.cortar_perdida_pct:
                self._vender(p, hora, f"cortar pérdida ({cambio:+.0f}%)", self.cfg.slippage_maximo_pct)

    def _vender(self, p: Posicion, hora: str, motivo: str, slippage_max: float) -> None:
        if not self._puedo_operar(hora):
            return
        t = p.cand.token
        ej = vender(self.rng_ejecucion, t, p.compra.cantidad, slippage_max)
        self.caja -= ej.comision_red
        p.comisiones_venta += ej.comision_red
        self.comisiones += ej.comision_red + ej.comision_dex
        if not ej.ok:
            self.ventas_fallidas += 1
            p.eventos.append(f"{hora} quiso vender ({motivo}) pero falló: {ej.motivo}")
            if ej.honeypot:
                p.intentos_honeypot += 1
                if p.intentos_honeypot >= INTENTOS_HONEYPOT:
                    p.atrapada = True
                    p.eventos.append(f"{hora} tras {INTENTOS_HONEYPOT} intentos se da por perdida")
            return
        self.caja += ej.usd
        self.coste_slippage += p.compra.cantidad * t.precio * ej.slippage_pct / 100
        p.venta, p.hora_salida, p.motivo_salida = ej, hora, motivo
        p.vendida_tras_rug = t.rugeado
        self.diario.operacion(p)

    def _cierre_del_dia(self) -> None:
        hora = self._hora(PASOS_POR_DIA - 1)
        for _ in range(INTENTOS_HONEYPOT):
            for p in self.abiertas:
                if not p.atrapada:
                    # Al cierre se vende a cualquier precio: tolerancia de slippage 100 %.
                    self._vender(p, hora, "cierre del día", 100.0)


class Mono(Simulador):
    """Grupo de control: elige tokens AL AZAR, sin radar ni revisión anti-estafa.

    Opera el mismo mercado, con los mismos límites, comisiones, slippage y
    reglas de venta. Si una estrategia no le gana claramente, sus filtros
    no aportan nada.
    """

    PROB_DARDO = 0.25  # cada token nuevo tiene un 25 % de recibir el dardo

    def __init__(self, *args, numero_mono: int = 0, **kwargs):
        super().__init__(*args, **kwargs)
        self.rng_mono = random.Random(f"mono-{self.semilla}-{numero_mono}")

    def _interesa(self, veredicto) -> bool:
        return self.rng_mono.random() < self.PROB_DARDO

    def _revision_seguridad(self, veredicto, t) -> list[str]:
        return []
