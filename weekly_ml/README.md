# MIDAS Weekly ML

Campaña prospectiva semanal de **machine learning en modo paper**, creada en 2026 a partir de dos líneas históricas distintas:

1. **MIDAS Python v2 (2023):** selección semanal mediante tres LightGBM y filtros técnicos.
2. **TFM:** familias LightGBM, MLP, LSTM y ARIMA usadas originalmente como modelos predictivos.

No es una reproducción literal de ninguna de las dos. Es una **adaptación corregida** para responder a la pregunta que MIDAS quiere medir prospectivamente: qué acciones de un universo amplio tienen mejor expectativa para la semana siguiente y si un ensemble de modelos aporta valor neto frente a modelos aislados y referencias simples.

## Qué corrige

El MIDAS Python v2 original:
- dividía semanas aleatoriamente con `GroupShuffleSplit`, mezclando pasado y futuro;
- entrenaba hasta 6.000 rondas sin early stopping activo;
- predecía además precio absoluto, una diana poco estable entre empresas;
- utilizaba un universo eToro/Nasdaq antiguo y rutas locales de Windows;
- evaluaba muchas variantes sobre el mismo test histórico.

Esta versión:
- usa separación cronológica para diagnóstico y luego reentrena solo con etiquetas ya conocidas;
- predice una **rentabilidad semanal ejecutable**: apertura de la semana siguiente → cierre de esa misma semana;
- sustituye el regresor de precio absoluto por un **ranker cross-sectional**;
- conserva por separado regresión de retorno y clasificación direccional;
- añade MLP, LSTM y ARIMA como expertos independientes;
- crea un ensemble por consenso y guarda también cada modelo aislado;
- congela un universo S&P 500 prospectivo antes de la primera señal;
- simula costes y ejecución, sin conexión a un bróker.

## Universo

`universe_sp500_2026-09-29.csv` congela 503 valores a partir de la lista ya usada por el agente genético privado en el commit disponible al 29/09/2026. Esto es adecuado para una campaña **prospectiva desde ahora**, pero introduce sesgo de supervivencia si se interpreta el entrenamiento histórico como backtest del S&P 500 real de cada año. Por eso las métricas históricas son diagnósticas y no cuentan como rentabilidad demo.

SPY y RSP se usan como referencias semanales adicionales.

## Features

Todas se calculan con datos conocidos al cierre de la semana de señal:

- retornos 1 semana, 1 mes, 3, 6 y 12 meses;
- volatilidad 20/63 sesiones;
- ratios frente a SMA 20/50/200;
- RSI 14;
- MACD normalizado;
- posición en Bollinger;
- ATR relativo;
- volumen relativo;
- gap reciente;
- fuerza relativa frente a SPY;
- régimen de SPY;
- sector GICS codificado one-hot;
- 26 retardos semanales para el LSTM.

No se usan fundamentales todavía. Esa capa entrará más adelante con datos point-in-time.

## Modelos

- `lgbm_return`: regresión del retorno open→close de la siguiente semana.
- `lgbm_direction`: probabilidad de retorno semanal positivo.
- `lgbm_ranker`: ranking cross-sectional por semana, sustituyendo el viejo modelo de precio absoluto.
- `mlp_return`: MLP sobre el mismo vector numérico.
- `lstm_return`: LSTM sobre los últimos 26 retornos semanales.
- `arima_return`: ARIMA(1,0,0) por acción sobre retornos semanales.
- `ensemble_consensus`: promedio de rangos de los expertos, con mínimo de votos positivos.

Cada experto tiene una cartera ficticia separada. También se registran SPY y RSP como referencias.

## Cronología

Al cierre de la última sesión de la semana:

```
datos conocidos hasta viernes/cierre semanal
  ↓
entrenamiento causal con etiquetas ya cerradas
  ↓
pronóstico de la semana siguiente
  ↓
orden paper pendiente
  ↓
compra: primera apertura de la semana siguiente
  ↓
venta: último cierre de esa semana
  ↓
comisión + slippage
```

La campaña no rellena semanas pasadas. Si una ejecución falla, se puede liquidar una orden previamente registrada con datos posteriores, pero la semana sin señal queda marcada como perdida.

## Acciones fraccionadas

La ejecución paper admite acciones fraccionadas porque el usuario opera con un bróker que permite fracciones. El sizing usa el capital objetivo de cada posición, redondea **hacia abajo a 6 decimales** para no exceder el presupuesto y exige un nominal mínimo de **10 USD**. Comisión y slippage se calculan sobre el nominal fraccionado exactamente igual que con acciones enteras.

Esta regla aplica también a SPY/RSP y evita que una acción de precio elevado quede infraponderada solo por el redondeo a unidades enteras.

## Interpretación

Un modelo que acierta la dirección no necesariamente produce una cartera rentable. Se registran por separado:

- métricas predictivas de validación;
- selecciones;
- operaciones simuladas;
- costes;
- NAV;
- comparación con SPY/RSP.

Los resultados de validación histórica no se presentan como rendimiento paper.

## Ejecución

Workflow semanal: `.github/workflows/weekly_ml.yml`.

Se programa después del cierre estadounidense del viernes y tiene un slot de respaldo el sábado. El estado vive en `weekly_ml_state/`.

**Limitación operativa (08/10/2026):** este motor solo asienta las compras y ventas paper al procesar el siguiente cierre semanal. Antes del viernes siguiente, `pending` indica **señales congeladas**, no compras confirmadas; `nav` sigue siendo el último valor liquidado y **no existe mark-to-market ni diario de fills lunes-jueves**. La rentabilidad aparece al liquidar el periodo completo. Este modo no debe presentarse como cartera con valoración diaria. Una futura variante con fills next-open y NAV diario deberá registrar ejecuciones prospectivamente y conservar el ledger anterior como tramo independiente, sin fabricar fills pasados.

No ejecuta dinero real.

## Seguimiento diario prospectivo (v2, desde señal 09/10/2026)

La simulación semanal clásica se conserva intacta en `weekly_ml_state/ledger.json`; sus liquidaciones diferidas no se mezclan con la cartera diaria. Tras un forecast semanal nuevo, `.github/workflows/weekly_ml.yml` congela las señales en `weekly_ml_daily_state/ledger.json`; `.github/workflows/weekly_ml_daily.yml` procesa cada cierre XNYS, registra las compras simuladas al siguiente open, valora NAV al cierre y liquida posiciones el último día bursátil de la semana. El dashboard público prioriza exclusivamente este ledger prospectivo desde su primera señal. No se retrotraen compras no registradas del 05/10. Nunca se envían órdenes reales.

## Exposición dual sin mezclar libros (09/10/2026)

El reporte canónico `strategy_comparison/report.py` conserva **dos campañas paper independientes por experto**:

- `weekly_ml_demo`: solo la cartera diaria next-open, identificadores canónicos `weekly_ml_*`. Hasta disponer de `weekly_ml_daily_state/ledger.json` muestra **esperando primera sesión**, sin heredar fecha, capital marcado, compras ni resultados de la campaña semanal. Las señales del viernes 09/10 solo podrán convertirse en fills paper prospectivos desde la apertura siguiente.
- `weekly_ml_legacy`: nueve filas de referencia con ID prefijado `weekly_legacy_`, alimentadas **exclusivamente** por `weekly_ml_state/ledger.json`, visibles en *Catálogo / histórico* y excluidas del ranking prospectivo. Tras observar **al menos dos puntos semanales en el ledger**, publica la rentabilidad semanal realmente liquidada. Antes de ello aparece como pendiente sin un retorno del 0 % inventado.

El conteo de estrategias competidoras no suma los nueve libros de referencia. Las dos curvas y P&L se calculan contra sus propios capitales iniciales; no se combinan, enlazan ni comparan como una campaña continuada. Se conserva el ledger semanal íntegro, incluidos sus pendientes, sin retroconstruir fills lunes-jueves ni intervenir en un bróker.

## Recovery guard · missing vendor quotes · 10/10/2026

- The weekly job failed on 10/10 while evaluating the 02/10 forecast: `KeyError('WBD')` from an unavailable historical OHLC series. The weekly ledger stayed at 02/10; the daily forward ledger has not opened.
- `run.evaluate` now computes diagnostic metrics only for tickers with observed **complete** next-week bars ending on the actual 09/10 close. Missing tickers and coverage are disclosed in `weekly_ml_state/evaluations/`; no missing return is set to zero or interpolated. If coverage drops below 90% for a >=100-ticker evaluation, abort rather than showing misleading metrics.
- `paper._settle` still requires actual next-week open and exact final closed-session prices for **every** previously committed order. If a purchased/pending ticker has no required price, abort all settlement atomically, preserving ledger and trade history unchanged. Never silently skip a required order.
- The workflow temporarily has a narrowly scoped push trigger for `weekly_ml/recovery/2026-10-10.trigger`. The trigger runs the real weekly pipeline **once on merge** of the fix while the native XNYS guard still places the execution before the next opening. It may legitimately fail if indispensable held quotes are absent, coverage is low, or the market window has expired; in that case do not fabricate results.
- A recovery **push** run must not be presented as a successful *scheduled* run in `strategy_runtime/weekly_ml.json`. The scheduled health record of the failed run remains historically factual until the next scheduled run, even if a separately documented recovery later succeeds.
