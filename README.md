# 📡 memecoin-agent

Radar de memecoins: vigila los tokens recién lanzados o en tendencia en
[DexScreener](https://dexscreener.com), les pone dos notas y te avisa sólo
cuando vale la pena mirar.

- **HYPE (0-100)**: cuánta gente está entrando *ahora*: volumen vs. liquidez,
  presión compradora, operaciones por minuto, momentum y comunidad visible.
- **RIESGO (0-100)**: banderas rojas de rug-pull: liquidez mínima, token
  recién nacido, sin web ni redes, FDV inflado, **posible honeypot** (muchas
  compras y cero ventas), desplomes, curvas parabólicas, hype pagado.

Con esas dos notas, cada token cae en un arquetipo:

| Arquetipo | Hype | Riesgo | Qué significa |
|---|---|---|---|
| 🚀 COHETE | ≥ 60 | < 40 | Mucho movimiento real y pocas banderas rojas |
| 🌱 BROTE | 35-59 | < 40 | Empieza a moverse de forma sana: vigílalo |
| 🎰 CASINO | ≥ 60 | ≥ 40 | Mucho ruido y mucho peligro |
| 🪤 TRAMPA | < 60 | ≥ 60 | Huele a estafa: no tocar |
| 🧊 DORMIDO | resto | | No pasa nada |

> ⚠️ Es una herramienta de **detección**, no de inversión. No compra ni vende
> nada. Las memecoins son extremadamente volátiles y un riesgo bajo **no**
> significa que sea segura.

## Uso

Requiere Python 3.11+. No tiene dependencias externas.

```bash
# Prueba sin internet con 5 tokens de ejemplo (uno de cada arquetipo)
python -m radar scan --demo --all --warn-traps

# Una pasada en vivo
python -m radar scan --all

# Vigilancia continua de Solana cada 2 minutos
python -m radar watch --chain solana --every 120
```

Opciones útiles:

| Opción | Por defecto | Para qué |
|---|---|---|
| `--chain X` | todas | Filtrar por cadena (`solana`, `base`, `ethereum`, `bsc`…). Se puede repetir |
| `--min-hype N` | 60 | Hype mínimo para alertar |
| `--max-risk N` | 40 | Riesgo máximo para alertar |
| `--warn-traps` | apagado | Avisar también de CASINOS y TRAMPAS con la etiqueta ⛔ NO COMPRAR |
| `--all` | apagado | Mostrar además una tabla con todos los tokens analizados |
| `--every N` | 120 | Segundos entre pasadas en modo `watch` |

El radar recuerda lo que ya te avisó (en `.radar_state.json`, durante 24 h)
y sólo repite una alerta si el hype de ese token **sube 15 puntos o más**.

## Alertas al móvil

Pon estas variables de entorno y las alertas llegarán también ahí:

```bash
# Telegram: crea un bot con @BotFather y obtén tu chat id con @userinfobot
export TELEGRAM_BOT_TOKEN="123456:ABC..."
export TELEGRAM_CHAT_ID="123456789"

# Discord: Ajustes del canal → Integraciones → Webhooks
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
```

## Simulador del modo sombra

Un día entero de trading con **dinero ficticio** en un mercado inventado:

```bash
python -m trading                 # un día nuevo al azar
python -m trading --semilla 42    # repetir exactamente el mismo día
```

- Antes de cada operación lee `config/limites.toml` y revisa si existe `PARAR.txt`.
- Paga comisiones, sufre slippage y a veces la red falla, como en la vida real.
- Hay tokens trampa: **rug-pulls** (el creador se lleva el dinero) y
  **honeypots** (puedes comprar pero no vender). Algunos van disfrazados.
- Cada operación, rechazo o fallo deja una autopsia en `diario/sombra/`, más
  un `RESUMEN.md` con la ganancia o pérdida y los aciertos.

## Tests

```bash
python -m unittest discover -s tests -t .
```

## Estructura

```
radar/
  dexscreener.py   cliente de la API pública (sin API key)
  scoring.py       cálculo de HYPE, RIESGO y arquetipo
  alerts.py        formato de las tarjetas y envío a Telegram/Discord
  state.py         memoria anti-spam con re-alerta por escalada
  __main__.py      línea de comandos (scan / watch)
  fixtures/        datos de ejemplo para --demo
tests/
```
