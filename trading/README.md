# Trading: simulador del MODO SOMBRA

Simula un día entero de memecoins con **dinero ficticio**. No hay aquí
ninguna forma de operar con dinero real.

```bash
python -m trading                 # un día nuevo al azar
python -m trading --semilla 42    # repetir exactamente el mismo día
python -m trading --tokens 100    # un día con más lanzamientos
```

| Archivo | Qué hace |
|---|---|
| `config.py` | Lee `config/limites.toml`. Si falta algo o está mal, no opera. |
| `interruptor.py` | Mira si existe `PARAR.txt`. |
| `mercado.py` | El mercado inventado: tokens sanos, rug-pulls y honeypots; comisiones, slippage y fallos de red. |
| `seguridad.py` | Revisión anti-estafa antes de comprar (radar + wallets). |
| `simulador.py` | El bucle del día, en pasos de 15 minutos. |
| `diario.py` | Escribe las autopsias y el `RESUMEN.md` en `diario/sombra/`. |
| `modelos.py` | Las "fichas" de datos que se pasan entre las piezas. |
