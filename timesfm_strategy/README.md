# MIDAS TimesFM 2.5 — 100.000 € paper trading

**Simulación únicamente. No transmite órdenes a bróker.**

## Horizonte y estrategia
TimesFM 2.5 (200 millones de parámetros, pesos Apache-2.0) con
512 cierres diarios ajustados y pronóstico de **cinco sesiones**. La
elección no significa que 5 días sea óptimo: 1 día aumenta ruido y costes,
10/21 días reduce operaciones pero también frecuencia de evaluación.
La ventaja de cualquier horizonte queda pendiente de validación
walk-forward; no se optimizan parámetros sobre la campaña prospectiva.

30 títulos estadounidenses congelados, ocho compras como máximo,
exposición máxima del 80% del capital, límite del 12,5% por acción,
sin cortos ni apalancamiento. El modelo pronostica cinco cierres futuros,
se puntúa por mediana prevista menos una penalización de volatilidad;
el filtro de SPY/SMA200 permite permanecer en efectivo. Se exige
previsión >1,5% y score superior al coste de ida y vuelta.
Las señales se congelan al cierre semanal; fills paper solo en la
**siguiente apertura**; cierre de posiciones el viernes siguiente.
El gap de apertura implica que el pronóstico no es un retorno
directamente ejecutable.

## EUR 100.000 y divisa
100.000 € ficticios; acciones USD. Entrada EUR calculada como
Open USD / cierre EURUSD de la sesión bursátil anterior; es una
aproximación causal, no FX instantáneo de las 09:30 ET. NAV y
liquidaciones usan Close USD / Close EURUSD del día. Acciones fraccionadas
con 6 decimales, comisión 0,10% y slippage 0,05% por cada lado.
Se computan dividendos y splits observados en tenencia.

Referencia SPY *buy and hold* en EUR, con fecha de inicio idéntica,
costes y FX idénticos; tiene cartera propia e independiente. No mezclar
rentabilidades USD de otras campañas con la cartera EUR: para comparación
económica homogénea habrá que expresar también la otra cartera en EUR.

## Operación
- Action diaria martes-sábado UTC: contabilidad a cierre; runtime ligero,
  sin descargar pesos.
- Action semanal sábado UTC: inferencia y congelación de la señal,
  checkpoint Google TimesFM 2.5 de revisión fija, cache si disponible.
- Ambas comparten control de concurrencia y publicación de estado.
- Tests no generan rentabilidad futura. Falta de barras, sesión o FX
  bloquea el estado (fail-closed), sin backfill.
- Primer resultado válido: tras la primera señal **y** primera valoración
  efectivamente persistidas. Antes se muestra «pendiente», jamás 0% ficticio.
- Comparar los retornos por periodos de 5, 21 y 63 sesiones **solo**
  si las dos fechas límite tienen NAV real y son las mismas en ambos
  algoritmos; el benchmark SPY EUR comparte las mismas fechas.

La API oficial del modelo es TimesFM 2.5:
https://github.com/google-research/timesfm/blob/master/timesfm-forecasting/references/api_reference.md
