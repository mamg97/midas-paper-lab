# MIDAS: todas las ideas en paralelo

Actualizado: 2026-09-29T02:41:44.709441+00:00. El tablero distingue resultados observados de ideas aún no ejecutadas.

Las rentabilidades de la campaña nueva, el TFM adaptado y el diario genético antiguo **no forman una clasificación común**: empiezan en fechas distintas, usan divisas o reglas de ejecución distintas.

| Estrategia | Procedencia | Estado | Primera fecha | Última fecha | Día | Acumulada |
| --- | --- | --- | --- | --- | ---: | ---: |
| Referencia SPY | Campaña nueva 2026 · referencia SPY | demo_con_diario | 2026-09-28 | 2026-09-28 | — | 0.00 % |
| Referencia ocho acciones equiponderadas | Campaña nueva 2026 · referencia equiponderada | demo_con_diario | 2026-09-28 | 2026-09-28 | — | 0.00 % |
| EMA/RSI fijo, adaptación nueva | Campaña nueva 2026 · señal técnica adaptada | demo_con_diario | 2026-09-28 | 2026-09-28 | — | 0.00 % |
| Genético nuevo congelado, ocho acciones | MIDAS nuevo 2026 · genético congelado | demo_con_diario | 2026-09-28 | 2026-09-28 | — | 0.00 % |
| MACD, adaptación nueva | Campaña nueva 2026 · señal técnica adaptada | demo_con_diario | 2026-09-28 | 2026-09-28 | — | 0.00 % |
| RSI reversión, adaptación nueva | Campaña nueva 2026 · señal técnica adaptada | demo_con_diario | 2026-09-28 | 2026-09-28 | — | 0.00 % |
| Bollinger ruptura, adaptación nueva | Campaña nueva 2026 · señal técnica adaptada | demo_con_diario | 2026-09-28 | 2026-09-28 | — | 0.00 % |
| Turtle 20/10 largo, adaptación nueva | Campaña nueva 2026 · señal técnica adaptada | demo_con_diario | 2026-09-28 | 2026-09-28 | — | 0.00 % |
| Turtle 55/20 largo, adaptación nueva | Campaña nueva 2026 · señal técnica adaptada | demo_con_diario | 2026-09-28 | 2026-09-28 | — | 0.00 % |
| Genético original S&P 500 | Agente genético S&P 500 original · 2026 | sin_diario_disponible | — | — | — | — |
| TFG 2021: filtros técnicos, AHP y rentabilidad/riesgo | TFG 2021 · MIDAS en R | sin_ejecucion_comparable | — | — | — | — |
| MIDAS R cripto | MIDAS en R · experimento cripto | sin_ejecucion_comparable | — | — | — | — |
| TFM: LightGBM (versión corregida 2026) | TFM · modelo reimplementado en 2026 | programada_sin_diario | — | — | — | — |
| TFM: red MLP (versión corregida 2026) | TFM · modelo reimplementado en 2026 | programada_sin_diario | — | — | — | — |
| TFM: red LSTM (versión corregida 2026) | TFM · modelo reimplementado en 2026 | programada_sin_diario | — | — | — | — |
| TFM: ARIMA (versión corregida 2026) | TFM · modelo reimplementado en 2026 | programada_sin_diario | — | — | — | — |
| MIDAS Python: LightGBM rentabilidad semanal | MIDAS Python · pipeline LightGBM semanal | sin_ejecucion_comparable | — | — | — | — |
| MIDAS Python: LightGBM dirección semanal | MIDAS Python · pipeline LightGBM semanal | sin_ejecucion_comparable | — | — | — | — |
| MIDAS Python: LightGBM precio semanal | MIDAS Python · pipeline LightGBM semanal | sin_ejecucion_comparable | — | — | — | — |
| MIDAS Python: filtro combinado de los tres LightGBM | MIDAS Python · filtro de los tres LightGBM | sin_ejecucion_comparable | — | — | — | — |
| Genético original de un solo activo | Agente genético · prototipo individual 2026 | sin_ejecucion_comparable | — | — | — | — |
| RSI original 70/30 sobre Inditex | Experimento histórico · trading | sin_ejecucion_comparable | — | — | — | — |
| Ichimoku original sobre AAPL | Experimento histórico · trading | sin_ejecucion_comparable | — | — | — | — |
| Gap alcista de apertura a cierre | Experimento histórico · trading intradía | sin_ejecucion_comparable | — | — | — | — |
| Turtle 20/10 corto original | Experimento histórico · trading en corto | sin_ejecucion_comparable | — | — | — | — |
| Turtle 55/20 corto original | Experimento histórico · trading en corto | sin_ejecucion_comparable | — | — | — | — |
| Screener momentum mensual S&P 500 | Experimento histórico · selección mensual | sin_ejecucion_comparable | — | — | — | — |
| Bot BTC Coinbase | Bot Coinbase histórico · cripto | sin_ejecucion_comparable | — | — | — | — |
| Markowitz | Módulo Markowitz · asignación de pesos | sin_ejecucion_comparable | — | — | — | — |
| Filtro fundamental MIDAS Python | MIDAS Python · filtro fundamental | sin_ejecucion_comparable | — | — | — | — |
| TimesFM: predictor zero-shot (hipótesis) | Idea nueva 2026 · TimesFM | sin_ejecucion_comparable | — | — | — | — |

## Qué impide activar las líneas restantes

- **TFG 2021: filtros técnicos, AHP y rentabilidad/riesgo**: Portar los tres filtros y pesos sobre el universo original de varios mercados, con divisas y calendario.
- **MIDAS R cripto**: Necesita campaña EUR y calendario 24/7; comprobar diferencias frente al TFG.
- **MIDAS Python: LightGBM rentabilidad semanal**: Los datos/Features llegan hasta 2024 y el entrenamiento mezclaba semanas; rehacer el pipeline cronológico.
- **MIDAS Python: LightGBM dirección semanal**: Rehacer features y entrenamiento cronológicos; no cargar pickle legado sin contrato verificado.
- **MIDAS Python: LightGBM precio semanal**: Rehacer features y entrenamiento cronológicos; no cargar pickle legado sin contrato verificado.
- **MIDAS Python: filtro combinado de los tres LightGBM**: Depende de tres predicciones y features semanales; exige datos actuales, versión de modelos y órdenes fechadas.
- **Genético original de un solo activo**: Separar entrenamiento y ejecución del mismo cierre, elegir activo y congelar versión antes de empezar.
- **RSI original 70/30 sobre Inditex**: El original usa posición -1/0/+1 sobre retornos al cierre; el motor actual es solo largo y no replica cortos/costes.
- **Ichimoku original sobre AAPL**: La referencia a close(-26) puede mirar al futuro; corregir y marcar una versión nueva antes de ejecutarla.
- **Gap alcista de apertura a cierre**: El gap se conoce en apertura; requiere ejecución intradía separada del ciclo cierre a apertura.
- **Turtle 20/10 corto original**: Requiere contabilidad de posiciones cortas y costes de préstamo.
- **Turtle 55/20 corto original**: Requiere contabilidad de posiciones cortas y costes de préstamo.
- **Screener momentum mensual S&P 500**: Documentar regla de salida y pesos antes de convertir la selección mensual en cartera.
- **Bot BTC Coinbase**: El original incluye llamadas a órdenes reales; portar solo reglas a simulador sin credenciales.
- **Markowitz**: Comparar como asignador de pesos; antes, normalizar divisas y frecuencia.
- **Filtro fundamental MIDAS Python**: Definir datos conocidos en cada fecha y cartera receptora; no es una señal independiente.
- **TimesFM: predictor zero-shot (hipótesis)**: Fijar universo, horizonte, versión del modelo y regla de órdenes; validar prospectivamente antes de activar una cartera.

La [hoja de ruta](../research/ROADMAP.md) documenta el estado de las adaptaciones. Ninguna fila pendiente recibe rentabilidad simulada retrospectivamente.
