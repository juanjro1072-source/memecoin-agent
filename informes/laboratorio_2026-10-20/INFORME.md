# Laboratorio de estrategias · 2026-10-20

> ⚠️ **Datos INVENTADOS.** Los días salen del mercado simulado de
> `trading/mercado.py`, no del mercado real. Los resultados dicen cómo se
> portan las estrategias en ese mundo inventado, no cuánto ganarías de verdad.

## Cómo se hizo

- 200 días simulados de 60 tokens cada uno.
- **Entrenamiento:** días 0 a 139. Ahí se probaron 81 combinaciones de ajustes.
- **Validación:** días 140 a 199. No se usaron para elegir; se corrieron una sola vez al final.
- **Mono con dardos:** 10 monos por día compran tokens al azar, sin radar ni revisión,
  con los mismos límites de dinero, comisiones, slippage y reglas de venta.
- **«Le gana claramente»** = la ganancia diaria de la estrategia menos la del mono, en los
  mismos días, tiene un intervalo de confianza del 95 % completamente por encima de $0.
- Límites de dinero usados (de tu `limites.toml`, sin tocar): $10 por
  operación, $30 por día, $100 por wallet.

## Fase 1 · Entrenamiento: las 10 mejores combinaciones

| Estrategia | Media por día | Total | Días en positivo | Ventas con ganancia | Honeypots | Rug-pulls |
|---|---|---|---|---|---|---|
| 1. hype ≥ 50, riesgo ≤ 30, vender a +80% / -25% | +$0.22 | +$31.47 | 59% | 34% | 2 | 13 |
| 2. hype ≥ 70, riesgo ≤ 30, vender a +80% / -40% | -$0.20 | -$27.60 | 47% | 40% | 2 | 16 |
| 3. hype ≥ 70, riesgo ≤ 30, vender a +80% / -25% | -$0.25 | -$35.41 | 56% | 34% | 2 | 15 |
| 4. hype ≥ 50, riesgo ≤ 30, vender a +80% / -15% | -$0.51 | -$70.81 | 50% | 25% | 2 | 12 |
| 5. hype ≥ 60, riesgo ≤ 30, vender a +80% / -25% | -$0.56 | -$78.43 | 59% | 32% | 2 | 15 |
| 6. hype ≥ 50, riesgo ≤ 30, vender a +80% / -40% | -$0.60 | -$83.67 | 48% | 39% | 2 | 13 |
| 7. hype ≥ 50, riesgo ≤ 40, vender a +80% / -25% | -$0.69 | -$96.30 | 54% | 34% | 6 | 20 |
| 8. hype ≥ 60, riesgo ≤ 30, vender a +80% / -15% | -$0.92 | -$128.39 | 49% | 25% | 2 | 13 |
| 9. hype ≥ 70, riesgo ≤ 40, vender a +80% / -40% | -$1.01 | -$140.78 | 41% | 41% | 9 | 21 |
| 10. hype ≥ 70, riesgo ≤ 40, vender a +80% / -25% | -$1.02 | -$142.70 | 49% | 35% | 9 | 20 |

- Tu configuración actual quedó en el puesto 41 de 81 (-$2.29 por día).
- El mono (con las reglas de venta de la elegida) hizo -$9.72 por día.

## Fase 2 · Validación: 60 días nunca vistos

| Estrategia | Media por día | Total | Días en positivo | Ventas con ganancia | Honeypots | Rug-pulls |
|---|---|---|---|---|---|---|
| estrategia elegida | -$0.49 | -$29.46 | 50% | 34% | 4 | 10 |
| 🐒 mono (elegida, promedio de 10) | -$8.42 | -$505.19 | 15% | 28% | 23 | 32 |
| estrategia actual | -$1.79 | -$107.16 | 32% | 37% | 2 | 8 |
| 🐒 mono (actual, promedio de 10) | -$8.49 | -$509.38 | 10% | 33% | 23 | 26 |

### ¿Le ganan al mono?

- **Elegida** (hype ≥ 50, riesgo ≤ 30, vender a +80% / -25%): +$7.93 por día frente al mono (intervalo 95 %: +$5.39 a +$10.42) → ✅ le gana claramente.
- **Actual** (hype ≥ 60, riesgo ≤ 40, vender a +50% / -25%): +$6.70 por día frente al mono (intervalo 95 %: +$4.70 a +$8.79) → ✅ le gana claramente.

### ¿La elegida es mejor que tu configuración actual?

- +$1.30 por día a favor de la elegida (intervalo 95 %: -$1.05 a +$3.56) → ❌ **no** está claro: la diferencia puede ser suerte.

### ¿Gana dinero?

- **No.** En validación pierden dinero: elegida, actual. Ganarle al mono sólo demuestra que los filtros esquivan estafas, no que la estrategia sea rentable.

### ¿Se infló en el entrenamiento?

- La elegida ganaba +$0.22 por día en entrenamiento y -$0.49 en validación.
  Si baja mucho, parte de su «éxito» era suerte de esos días concretos.

## Qué podrías cambiar en `limites.toml` (lo decides tú)

- **Nada por ahora.** La elegida no le gana claramente a tu configuración actual en validación. Si aun así quisieras probarla, estos serían los cambios:
  - `hype_minimo`: de 60 a 50
  - `riesgo_maximo`: de 40 a 30
  - `tomar_ganancia_pct`: de 50 a 80

No se modificó `limites.toml`.
