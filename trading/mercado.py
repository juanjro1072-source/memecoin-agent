"""Mercado inventado para el modo sombra.

Cada token tiene un DESTINO oculto que el bot no puede ver:
  - "sano":     se mueve al azar (como casi todas las memecoins, tiende a bajar)
  - "rug":      sube un rato y de golpe el creador se lleva la liquidez
  - "honeypot": deja comprar pero nunca vender; al final también se vacía

Lo que el bot SÍ ve son señales (liquidez, redes, wallets...). Las estafas
suelen tener malas señales, pero algunas se disfrazan de token sano, igual
que en la vida real.

Las operaciones son realistas: pagan comisión de la red (aunque fallen) y del
exchange, sufren slippage según el tamaño frente a la liquidez, y a veces
fallan porque la red está saturada.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

PASO_MINUTOS = 15
PASOS_POR_DIA = 24 * 60 // PASO_MINUTOS

COMISION_DEX = 0.003  # 0.3 % que se queda el pool en cada compra o venta
COMISION_RED_USD = {"solana": 0.05, "base": 0.10, "bsc": 0.15, "ethereum": 4.00}
PROB_FALLO_RED = 0.04  # 4 % de las transacciones expiran o fallan

_CADENAS = (("solana", 0.70), ("base", 0.15), ("bsc", 0.10), ("ethereum", 0.05))
_DESTINOS = (("sano", 0.65), ("rug", 0.25), ("honeypot", 0.10))
_ANIMALES = ("Capy", "Frog", "Doge", "Pengu", "Hamster", "Goat", "Sloth", "Llama",
             "Axolotl", "Otter", "Moose", "Panda", "Quokka", "Walrus", "Gecko")
_APELLIDOS = ("Inu", "Moon", "Rocket", "King", "Wif Hat", "Lord", "Classic",
              "Mars", "Turbo", "Coin", "Party", "Chad", "Gold", "Ninja")


def _elegir(rng: random.Random, opciones):
    valores, pesos = zip(*opciones)
    return rng.choices(valores, pesos)[0]


@dataclass
class Token:
    simbolo: str
    nombre: str
    cadena: str
    direccion: str
    destino: str
    paso_lanzamiento: int
    paso_rug: int | None
    precio: float
    liquidez: float
    tendencia: float
    volatilidad: float
    par: dict          # lo que vería DexScreener al aparecer (lo lee el radar)
    billeteras: dict   # datos de wallets para la revisión anti-estafa
    rugeado: bool = False

    @property
    def es_estafa(self) -> bool:
        return self.destino != "sano"

    def avanzar(self, paso: int, rng: random.Random) -> None:
        """Mueve el precio un paso (15 minutos)."""
        if paso <= self.paso_lanzamiento:
            return
        if paso == self.paso_rug:
            self.precio *= rng.uniform(0.01, 0.06)
            self.liquidez *= rng.uniform(0.005, 0.03)
            self.rugeado = True
            return
        mu, sigma = (-0.02, 0.05) if self.rugeado else (self.tendencia, self.volatilidad)
        r = rng.gauss(mu, sigma)
        self.precio *= math.exp(r)
        self.liquidez *= math.exp(r / 2)


def _perfil(rng: random.Random, parece_sano: bool, popularidad: float) -> dict:
    if parece_sano:
        liquidez = min(max(rng.lognormvariate(math.log(70_000), 0.8), 8_000), 2_000_000)
        fdv = liquidez * rng.uniform(6, 45)
        redes = rng.choices([0, 1, 2, 3], [0.05, 0.2, 0.4, 0.35])[0]
        web = rng.random() < 0.8
        edad = rng.uniform(60, 900)
        prop_compras = rng.uniform(0.5, 0.75)
        boosts = 0 if rng.random() < 0.7 else 100
    else:
        liquidez = min(max(rng.lognormvariate(math.log(9_000), 0.7), 1_500), 80_000)
        fdv = liquidez * rng.uniform(30, 260)
        redes = rng.choices([0, 1, 2], [0.55, 0.3, 0.15])[0]
        web = rng.random() < 0.3
        edad = rng.uniform(5, 120)
        prop_compras = rng.uniform(0.65, 0.95)
        boosts = 500 if rng.random() < 0.5 else 0
    tx_h1 = int(40 + 1500 * popularidad * rng.uniform(0.6, 1.4))
    tx_m5 = max(1, int(tx_h1 / 12 * rng.uniform(0.6, 1.6)))
    compras_h1, compras_m5 = int(tx_h1 * prop_compras), int(tx_m5 * prop_compras)
    return {
        "liquidez": liquidez, "fdv": fdv, "redes": redes, "web": web, "edad_min": edad,
        "boosts": boosts, "vol_h1": liquidez * (0.1 + 3.5 * popularidad) * rng.uniform(0.7, 1.3),
        "compras_h1": compras_h1, "ventas_h1": tx_h1 - compras_h1,
        "compras_m5": compras_m5, "ventas_m5": tx_m5 - compras_m5,
        "cambio_m5": rng.uniform(-8, 12), "cambio_h1": rng.uniform(-20, 40) + 250 * popularidad * rng.random(),
    }


def _billeteras(rng: random.Random, sanas: bool) -> dict:
    if sanas:
        datos = {"top10_pct": rng.uniform(15, 45), "creador_pct": rng.uniform(0, 7),
                 "liquidez_bloqueada": rng.random() < 0.85, "wallets_coordinadas": rng.randint(0, 3)}
    else:
        datos = {"top10_pct": rng.uniform(40, 90), "creador_pct": rng.uniform(5, 40),
                 "liquidez_bloqueada": rng.random() < 0.25, "wallets_coordinadas": rng.randint(2, 30)}
    for clave in datos:  # a veces la API no devuelve un dato
        if rng.random() < 0.04:
            datos[clave] = None
    return datos


def generar_tokens(rng: random.Random, cantidad: int, inicio_epoch: float) -> list[Token]:
    tokens: list[Token] = []
    usados: set[str] = set()
    for _ in range(cantidad):
        destino = _elegir(rng, _DESTINOS)
        estafa = destino != "sano"
        animal, apellido = rng.choice(_ANIMALES), rng.choice(_APELLIDOS)
        simbolo = (animal[:4] + apellido[:1]).upper()
        while simbolo in usados:
            simbolo += str(rng.randint(0, 9))
        usados.add(simbolo)

        paso = rng.randrange(0, PASOS_POR_DIA - 8)
        paso_rug = None
        if destino == "rug":
            paso_rug = paso + rng.randint(2, 40)
        elif destino == "honeypot":
            paso_rug = paso + rng.randint(12, 70)

        popularidad = rng.random()
        d = _perfil(rng, rng.random() < (0.85 if not estafa else 0.25), popularidad)
        if destino == "honeypot" and rng.random() < 0.6:
            d["ventas_h1"] = d["ventas_m5"] = 0  # nadie consigue vender
        if destino == "honeypot":
            tendencia, volatilidad = 0.015, 0.03
        elif destino == "rug":
            tendencia, volatilidad = 0.01, 0.06
        else:
            tendencia = rng.gauss(-0.003, 0.01) + 0.006 * (popularidad - 0.5)
            volatilidad = rng.uniform(0.04, 0.10)

        cadena = _elegir(rng, _CADENAS)
        direccion = "SIM" + "".join(rng.choices("0123456789abcdef", k=12))
        nombre = f"{animal} {apellido}"
        precio = rng.lognormvariate(math.log(0.0005), 1.5)
        momento = inicio_epoch + paso * PASO_MINUTOS * 60
        par = {
            "chainId": cadena,
            "url": "",
            "baseToken": {"address": direccion, "name": nombre, "symbol": simbolo},
            "priceUsd": str(precio),
            "liquidity": {"usd": d["liquidez"]},
            "fdv": d["fdv"],
            "volume": {"h1": d["vol_h1"], "h24": d["vol_h1"] * 6},
            "txns": {"m5": {"buys": d["compras_m5"], "sells": d["ventas_m5"]},
                     "h1": {"buys": d["compras_h1"], "sells": d["ventas_h1"]}},
            "priceChange": {"m5": d["cambio_m5"], "h1": d["cambio_h1"], "h24": d["cambio_h1"]},
            "info": {"websites": [{"url": "https://ejemplo.invalid"}] if d["web"] else [],
                     "socials": [{"type": "twitter"}] * d["redes"]},
            "boosts": {"active": d["boosts"]},
            "pairCreatedAt": (momento - d["edad_min"] * 60) * 1000,
        }
        tokens.append(Token(
            simbolo=simbolo, nombre=nombre, cadena=cadena, direccion=direccion, destino=destino,
            paso_lanzamiento=paso, paso_rug=paso_rug, precio=precio, liquidez=d["liquidez"],
            tendencia=tendencia, volatilidad=volatilidad, par=par,
            billeteras=_billeteras(rng, rng.random() < (0.9 if not estafa else 0.35)),
        ))
    return tokens


@dataclass
class Ejecucion:
    ok: bool
    motivo: str = ""
    precio: float = 0.0        # precio por token que de verdad se obtuvo
    cantidad: float = 0.0      # tokens comprados o vendidos
    usd: float = 0.0           # compra: dólares metidos al pool · venta: dólares recibidos
    comision_red: float = 0.0  # se paga aunque la operación falle
    comision_dex: float = 0.0
    slippage_pct: float = 0.0
    honeypot: bool = False


def _slippage_pct(rng: random.Random, token: Token, valor_usd: float) -> float:
    # Pool de producto constante: cuanto más grande la orden frente a la
    # liquidez, peor precio. Más un poco de ruido por el movimiento del mercado.
    reserva = max(token.liquidez / 2, 1.0)
    return valor_usd / (reserva + valor_usd) * 100 + abs(rng.gauss(0, 0.6))


def comprar(rng: random.Random, token: Token, monto_usd: float, slippage_max: float) -> Ejecucion:
    red = COMISION_RED_USD.get(token.cadena, 0.5)
    if rng.random() < PROB_FALLO_RED:
        return Ejecucion(False, "la red estaba saturada y la transacción expiró", comision_red=red)
    slip = _slippage_pct(rng, token, monto_usd)
    if slip > slippage_max:
        return Ejecucion(False, f"el precio empeoraba {slip:.1f}% (tu máximo es {slippage_max:g}%) y se canceló",
                         comision_red=red, slippage_pct=slip)
    dex = monto_usd * COMISION_DEX
    precio = token.precio * (1 + slip / 100)
    return Ejecucion(True, precio=precio, cantidad=(monto_usd - dex) / precio, usd=monto_usd,
                     comision_red=red, comision_dex=dex, slippage_pct=slip)


def vender(rng: random.Random, token: Token, cantidad: float, slippage_max: float) -> Ejecucion:
    red = COMISION_RED_USD.get(token.cadena, 0.5)
    if token.destino == "honeypot":
        return Ejecucion(False, "el contrato no deja vender: es un HONEYPOT", comision_red=red, honeypot=True)
    if rng.random() < PROB_FALLO_RED:
        return Ejecucion(False, "la red estaba saturada y la transacción expiró", comision_red=red)
    slip = _slippage_pct(rng, token, cantidad * token.precio)
    if slip > slippage_max:
        return Ejecucion(False, f"el precio empeoraba {slip:.1f}% (tu máximo es {slippage_max:g}%) y se canceló",
                         comision_red=red, slippage_pct=slip)
    precio = token.precio * (1 - slip / 100)
    bruto = cantidad * precio
    dex = bruto * COMISION_DEX
    return Ejecucion(True, precio=precio, cantidad=cantidad, usd=bruto - dex,
                     comision_red=red, comision_dex=dex, slippage_pct=slip)
