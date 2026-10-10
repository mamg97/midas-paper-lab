# MIDAS: todas las ideas en paralelo

Actualizado: 2026-10-10T02:22:46.213086+00:00. El tablero distingue resultados observados de ideas aún no ejecutadas.

La comparación principal sigue **rentabilidad acumulada + riesgo realizado**. Las campañas diarias, TFM, Weekly ML, TFG corregido, Capital Cycle, Buy The Dip y el diario genético antiguo **no forman una clasificación común** si sus fechas, divisas o reglas difieren.

| Estrategia | Procedencia | Estado | Actividad actual | Primera fecha | Última fecha | Último periodo | Acumulada | Vol. anual. | Máx. DD | Sharpe 0rf |
| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| Referencia SPY | Campaña nueva 2026 · referencia SPY | demo_con_diario | 1 posición abierta | 2026-09-28 | 2026-10-08 | -0.40 % | 0.74 % | — | -0.66 % | — |
| Referencia ocho acciones equiponderadas | Campaña nueva 2026 · referencia equiponderada | demo_con_diario | 8 posiciones abiertas | 2026-09-28 | 2026-10-08 | -0.10 % | 0.72 % | — | -0.61 % | — |
| EMA/RSI fijo, adaptación nueva | Campaña nueva 2026 · señal técnica adaptada | demo_con_diario | Sin compras · en efectivo | 2026-09-28 | 2026-10-08 | 0.00 % | 0.00 % | — | 0.00 % | — |
| Genético nuevo congelado, ocho acciones | MIDAS nuevo 2026 · genético congelado | demo_con_diario | 2 posiciones abiertas | 2026-09-28 | 2026-10-08 | 0.07 % | 0.59 % | — | -0.00 % | — |
| MACD, adaptación nueva | Campaña nueva 2026 · señal técnica adaptada | demo_con_diario | 2 posiciones abiertas | 2026-09-28 | 2026-10-08 | 0.20 % | 0.31 % | — | -0.15 % | — |
| RSI reversión, adaptación nueva | Campaña nueva 2026 · señal técnica adaptada | demo_con_diario | Sin compras · en efectivo | 2026-09-28 | 2026-10-08 | 0.00 % | 0.00 % | — | 0.00 % | — |
| Bollinger ruptura, adaptación nueva | Campaña nueva 2026 · señal técnica adaptada | demo_con_diario | 1 posición abierta | 2026-09-28 | 2026-10-08 | -0.35 % | -0.35 % | — | -0.35 % | — |
| Turtle 20/10 largo, adaptación nueva | Campaña nueva 2026 · señal técnica adaptada | demo_con_diario | 1 posición abierta | 2026-09-28 | 2026-10-08 | -0.35 % | -0.35 % | — | -0.35 % | — |
| Turtle 55/20 largo, adaptación nueva | Campaña nueva 2026 · señal técnica adaptada | demo_con_diario | Sin compras · en efectivo | 2026-09-28 | 2026-10-08 | 0.00 % | 0.00 % | — | 0.00 % | — |
| ML semanal · referencia SPY | Campaña ML semanal 2026 · referencia SPY | programada_sin_diario | Esperando primera sesión | — | — | — | — | — | — | — |
| ML semanal · referencia SPY · liquidación diferida | Campaña ML semanal 2026 · referencia SPY · libro semanal independiente | weekly_awaiting_first_settlement | 1 señal congelada · liquidación semanal pendiente | 2026-10-02 | 2026-10-02 | — | — | — | 0.00 % | — |
| ML semanal · referencia RSP | Campaña ML semanal 2026 · referencia RSP equiponderada | programada_sin_diario | Esperando primera sesión | — | — | — | — | — | — | — |
| ML semanal · referencia RSP · liquidación diferida | Campaña ML semanal 2026 · referencia RSP equiponderada · libro semanal independiente | weekly_awaiting_first_settlement | 1 señal congelada · liquidación semanal pendiente | 2026-10-02 | 2026-10-02 | — | — | — | 0.00 % | — |
| ML semanal · LightGBM rentabilidad | MIDAS Python v2 · regresión semanal corregida 2026 | programada_sin_diario | Esperando primera sesión | — | — | — | — | — | — | — |
| ML semanal · LightGBM rentabilidad · liquidación diferida | MIDAS Python v2 · regresión semanal corregida 2026 · libro semanal independiente | weekly_awaiting_first_settlement | Sin compras · en efectivo | 2026-10-02 | 2026-10-02 | — | — | — | 0.00 % | — |
| ML semanal · LightGBM dirección | MIDAS Python v2 · clasificación semanal corregida 2026 | programada_sin_diario | Esperando primera sesión | — | — | — | — | — | — | — |
| ML semanal · LightGBM dirección · liquidación diferida | MIDAS Python v2 · clasificación semanal corregida 2026 · libro semanal independiente | weekly_awaiting_first_settlement | Sin compras · en efectivo | 2026-10-02 | 2026-10-02 | — | — | — | 0.00 % | — |
| ML semanal · LightGBM ranker | MIDAS nuevo 2026 · ranking cross-sectional que sustituye precio absoluto | programada_sin_diario | Esperando primera sesión | — | — | — | — | — | — | — |
| ML semanal · LightGBM ranker · liquidación diferida | MIDAS nuevo 2026 · ranking cross-sectional que sustituye precio absoluto · libro semanal independiente | weekly_awaiting_first_settlement | 10 señales congeladas · liquidación semanal pendiente | 2026-10-02 | 2026-10-02 | — | — | — | 0.00 % | — |
| ML semanal · MLP | TFM/ML · MLP adaptado al horizonte semanal | programada_sin_diario | Esperando primera sesión | — | — | — | — | — | — | — |
| ML semanal · MLP · liquidación diferida | TFM/ML · MLP adaptado al horizonte semanal · libro semanal independiente | weekly_awaiting_first_settlement | 10 señales congeladas · liquidación semanal pendiente | 2026-10-02 | 2026-10-02 | — | — | — | 0.00 % | — |
| ML semanal · LSTM | TFM/ML · LSTM adaptado al horizonte semanal | programada_sin_diario | Esperando primera sesión | — | — | — | — | — | — | — |
| ML semanal · LSTM · liquidación diferida | TFM/ML · LSTM adaptado al horizonte semanal · libro semanal independiente | weekly_awaiting_first_settlement | 10 señales congeladas · liquidación semanal pendiente | 2026-10-02 | 2026-10-02 | — | — | — | 0.00 % | — |
| ML semanal · ARIMA | TFM/ML · ARIMA adaptado al horizonte semanal | programada_sin_diario | Esperando primera sesión | — | — | — | — | — | — | — |
| ML semanal · ARIMA · liquidación diferida | TFM/ML · ARIMA adaptado al horizonte semanal · libro semanal independiente | weekly_awaiting_first_settlement | 10 señales congeladas · liquidación semanal pendiente | 2026-10-02 | 2026-10-02 | — | — | — | 0.00 % | — |
| ML semanal · ensemble consenso | MIDAS nuevo 2026 · consenso de expertos semanales | programada_sin_diario | Esperando primera sesión | — | — | — | — | — | — | — |
| ML semanal · ensemble consenso · liquidación diferida | MIDAS nuevo 2026 · consenso de expertos semanales · libro semanal independiente | weekly_awaiting_first_settlement | 10 señales congeladas · liquidación semanal pendiente | 2026-10-02 | 2026-10-02 | — | — | — | 0.00 % | — |
| TFG corregido 2026 · técnico + AHP + MAD | TFG 2021 · arquitectura portada y corregida para paper 2026 | demo_con_diario | Sin compras · esperando señal | 2026-10-02 | 2026-10-02 | — | 0.00 % | — | 0.00 % | — |
| Capital Cycle Inflection · underinvestment + calidad + giro | MIDAS 2026 · estrategia cíclica derivada del marco Capital Cycle | demo_con_diario | 12 posiciones abiertas | 2026-09-30 | 2026-10-08 | 0.71 % | 1.32 % | — | -1.33 % | — |
| Buy The Dip corpus v0 · deep value + special situations | MIDAS 2026 · Buy The Dip corpus v0 · deep value + special situations | demo_con_diario | 10 posiciones abiertas | 2026-10-01 | 2026-10-08 | 1.05 % | 1.20 % | — | -1.99 % | — |
| Genético original S&P 500 | Agente genético S&P 500 original · 2026 | sin_diario_disponible | Actividad actual no enlazada | — | — | — | — | — | — | — |
| TFG 2021: filtros técnicos, AHP y rentabilidad/riesgo | TFG 2021 · MIDAS en R | sin_ejecucion_comparable | Actividad actual no enlazada | — | — | — | — | — | — | — |
| MIDAS R cripto | MIDAS en R · experimento cripto | sin_ejecucion_comparable | Actividad actual no enlazada | — | — | — | — | — | — | — |
| TFM: LightGBM (versión corregida 2026) | TFM · modelo reimplementado en 2026 | demo_con_diario | 3 compras para próxima apertura | 2026-10-02 | 2026-10-09 | -0.35 % | 0.09 % | — | -0.35 % | — |
| TFM: red MLP (versión corregida 2026) | TFM · modelo reimplementado en 2026 | demo_con_diario | 10 compras para próxima apertura | 2026-10-02 | 2026-10-09 | -0.38 % | -2.32 % | — | -2.32 % | — |
| TFM: red LSTM (versión corregida 2026) | TFM · modelo reimplementado en 2026 | demo_con_diario | Sin compras · en efectivo | 2026-10-02 | 2026-10-09 | 0.45 % | -0.01 % | — | -0.46 % | — |
| TFM: ARIMA (versión corregida 2026) | TFM · modelo reimplementado en 2026 | demo_con_diario | Sin compras · en efectivo | 2026-10-02 | 2026-10-09 | 0.00 % | 0.00 % | — | 0.00 % | — |
| MIDAS Python: LightGBM rentabilidad semanal | MIDAS Python · pipeline LightGBM semanal | sin_ejecucion_comparable | Actividad actual no enlazada | — | — | — | — | — | — | — |
| MIDAS Python: LightGBM dirección semanal | MIDAS Python · pipeline LightGBM semanal | sin_ejecucion_comparable | Actividad actual no enlazada | — | — | — | — | — | — | — |
| MIDAS Python: LightGBM precio semanal | MIDAS Python · pipeline LightGBM semanal | sin_ejecucion_comparable | Actividad actual no enlazada | — | — | — | — | — | — | — |
| MIDAS Python v2: selección semanal de hasta 30 empresas | MIDAS Python · filtro de los tres LightGBM | sin_ejecucion_comparable | Actividad actual no enlazada | — | — | — | — | — | — | — |
| Genético original de un solo activo | Agente genético · prototipo individual 2026 | sin_ejecucion_comparable | Actividad actual no enlazada | — | — | — | — | — | — | — |
| RSI original 70/30 sobre Inditex | Experimento histórico · trading | sin_ejecucion_comparable | Actividad actual no enlazada | — | — | — | — | — | — | — |
| Ichimoku original sobre AAPL | Experimento histórico · trading | sin_ejecucion_comparable | Actividad actual no enlazada | — | — | — | — | — | — | — |
| Gap alcista de apertura a cierre | Experimento histórico · trading intradía | sin_ejecucion_comparable | Actividad actual no enlazada | — | — | — | — | — | — | — |
| Turtle 20/10 corto original | Experimento histórico · trading en corto | sin_ejecucion_comparable | Actividad actual no enlazada | — | — | — | — | — | — | — |
| Turtle 55/20 corto original | Experimento histórico · trading en corto | sin_ejecucion_comparable | Actividad actual no enlazada | — | — | — | — | — | — | — |
| Screener momentum mensual S&P 500 | Experimento histórico · selección mensual | sin_ejecucion_comparable | Actividad actual no enlazada | — | — | — | — | — | — | — |
| Bot BTC Coinbase | Bot Coinbase histórico · cripto | sin_ejecucion_comparable | Actividad actual no enlazada | — | — | — | — | — | — | — |
| Markowitz | Módulo Markowitz · asignación de pesos | sin_ejecucion_comparable | Actividad actual no enlazada | — | — | — | — | — | — | — |
| Filtro fundamental MIDAS Python | MIDAS Python · filtro fundamental | sin_ejecucion_comparable | Actividad actual no enlazada | — | — | — | — | — | — | — |
| TimesFM: predictor zero-shot (hipótesis) | Idea nueva 2026 · TimesFM | sin_ejecucion_comparable | Actividad actual no enlazada | — | — | — | — | — | — | — |

## Qué impide activar las líneas restantes

- **TFG 2021: filtros técnicos, AHP y rentabilidad/riesgo**: La réplica literal global de 20 mercados sigue pendiente por símbolos, divisas y calendarios; la variante TFG corregido 2026 se ejecuta por separado sobre un universo S&P-derived homogéneo.
- **MIDAS R cripto**: Necesita campaña EUR y calendario 24/7; comprobar diferencias frente al TFG.
- **MIDAS Python: LightGBM rentabilidad semanal**: Los datos/Features llegan hasta 2024 y el entrenamiento mezclaba semanas; rehacer el pipeline cronológico.
- **MIDAS Python: LightGBM dirección semanal**: Rehacer features y entrenamiento cronológicos; no cargar pickle legado sin contrato verificado.
- **MIDAS Python: LightGBM precio semanal**: Rehacer features y entrenamiento cronológicos; no cargar pickle legado sin contrato verificado.
- **MIDAS Python v2: selección semanal de hasta 30 empresas**: El código original sí proponía inversiones semanales: combina tres predicciones, RSI y ranking. Para medir rentabilidad demo faltan datos actuales, modelos causales, órdenes fechadas y contabilidad de ejecución.
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
