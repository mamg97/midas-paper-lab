# MIDAS Weekly ML — dashboard

> **Forward activo.** Última señal registrada: **2026-10-02**. Las predicciones mostradas abajo fueron congeladas antes de conocer la semana objetivo.

## Progreso

| Modelo | Función | Estado | NAV | Retorno acumulado | Posiciones/órdenes | Trades cerrados |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| **LightGBM Return** | Predice la rentabilidad semanal esperada de cada acción. | forward | 100,000.00 USD | 0.000% | 0 | 0 |
| **LightGBM Direction** | Estima la probabilidad de que la semana termine en positivo. | forward | 100,000.00 USD | 0.000% | 0 | 0 |
| **LightGBM Ranker** | Ordena el universo de mejor a peor oportunidad relativa. | forward | 100,000.00 USD | 0.000% | 10 | 0 |
| **MLP** | Red neuronal feed-forward sobre features tabulares. | forward | 100,000.00 USD | 0.000% | 10 | 0 |
| **LSTM** | Red temporal sobre la secuencia de las últimas 26 semanas. | forward | 100,000.00 USD | 0.000% | 10 | 0 |
| **ARIMA** | Modelo estadístico por acción sobre retornos semanales. | forward | 100,000.00 USD | 0.000% | 10 | 0 |
| **Ensemble** | Combina rankings y votos de los expertos anteriores. | forward | 100,000.00 USD | 0.000% | 10 | 0 |
| **SPY** | Benchmark S&P 500. | forward | 100,000.00 USD | 0.000% | 1 | 0 |
| **RSP** | Benchmark S&P 500 equiponderado. | forward | 100,000.00 USD | 0.000% | 1 | 0 |

## Predicciones del último forecast

**Cutoff:** 2026-10-02 · **Horizonte:** primera apertura → último cierre de la semana siguiente.

### LightGBM Return

Predice la rentabilidad semanal esperada de cada acción.

**Validación diagnóstica:** MAE 3.51 pp · iter 5

| # | Ticker | Retorno previsto |
| ---: | --- | ---: |
| 1 | **A** | 0.14% |
| 2 | **AAPL** | 0.14% |
| 3 | **ABBV** | 0.14% |
| 4 | **ABNB** | 0.14% |
| 5 | **ABT** | 0.14% |
| 6 | **ACGL** | 0.14% |
| 7 | **ACN** | 0.14% |
| 8 | **ADBE** | 0.14% |
| 9 | **ADI** | 0.14% |
| 10 | **ADM** | 0.14% |

### LightGBM Direction

Estima la probabilidad de que la semana termine en positivo.

**Validación diagnóstica:** accuracy 53.6% · Brier 0.2486 · iter 99

| # | Ticker | Prob. positiva |
| ---: | --- | ---: |
| 1 | **CF** | 51.4% |
| 2 | **PCG** | 51.1% |
| 3 | **A** | 51.0% |
| 4 | **APA** | 51.0% |
| 5 | **COP** | 50.8% |
| 6 | **FANG** | 50.8% |
| 7 | **GLW** | 50.7% |
| 8 | **BKR** | 50.6% |
| 9 | **EOG** | 50.6% |
| 10 | **EIX** | 50.6% |

### LightGBM Ranker

Ordena el universo de mejor a peor oportunidad relativa.

**Validación diagnóstica:** rank-IC 0.0302 · iter 5

| # | Ticker | Rank score |
| ---: | --- | ---: |
| 1 | **APA** | 0.0880 |
| 2 | **DDOG** | 0.0815 |
| 3 | **HPE** | 0.0815 |
| 4 | **ON** | 0.0815 |
| 5 | **AMD** | 0.0805 |
| 6 | **CRWD** | 0.0805 |
| 7 | **MPWR** | 0.0805 |
| 8 | **SNPS** | 0.0769 |
| 9 | **INTC** | 0.0766 |
| 10 | **SWKS** | 0.0766 |

### MLP

Red neuronal feed-forward sobre features tabulares.

**Validación diagnóstica:** rank-IC 0.0102 · MAE 3.90 pp

| # | Ticker | Retorno previsto |
| ---: | --- | ---: |
| 1 | **INTC** | 10.80% |
| 2 | **QCOM** | 9.96% |
| 3 | **MRNA** | 8.04% |
| 4 | **PAYC** | 5.19% |
| 5 | **SWKS** | 4.75% |
| 6 | **ZBRA** | 4.72% |
| 7 | **IT** | 4.23% |
| 8 | **ADBE** | 4.21% |
| 9 | **JBL** | 3.96% |
| 10 | **UAL** | 3.44% |

### LSTM

Red temporal sobre la secuencia de las últimas 26 semanas.

**Validación diagnóstica:** rank-IC 0.0425 · MAE 3.52 pp

| # | Ticker | Retorno previsto |
| ---: | --- | ---: |
| 1 | **ENPH** | 1.37% |
| 2 | **QCOM** | 1.10% |
| 3 | **MGM** | 1.03% |
| 4 | **FICO** | 1.03% |
| 5 | **APTV** | 1.03% |
| 6 | **SMCI** | 1.02% |
| 7 | **FSLR** | 0.94% |
| 8 | **AKAM** | 0.87% |
| 9 | **ON** | 0.84% |
| 10 | **ORCL** | 0.82% |

### ARIMA

Modelo estadístico por acción sobre retornos semanales.

**Validación diagnóstica:** —

| # | Ticker | Retorno previsto |
| ---: | --- | ---: |
| 1 | **MRNA** | 5.78% |
| 2 | **DELL** | 5.62% |
| 3 | **MU** | 4.48% |
| 4 | **INCY** | 4.39% |
| 5 | **NTAP** | 4.26% |
| 6 | **CCL** | 4.12% |
| 7 | **AMD** | 4.10% |
| 8 | **HPE** | 4.09% |
| 9 | **WDC** | 3.97% |
| 10 | **DDOG** | 3.86% |

### Ensemble

Combina rankings y votos de los expertos anteriores.

**Validación diagnóstica:** —

| # | Ticker | Score | Retorno previsto | Votos + | Dispersión |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | **AMD** | 0.8750 | 0.98% | 5 | 0.1748 |
| 2 | **INTC** | 0.8677 | 1.01% | 4 | 0.1708 |
| 3 | **UAL** | 0.8423 | 0.70% | 4 | 0.1687 |
| 4 | **ON** | 0.8274 | 0.79% | 4 | 0.1746 |
| 5 | **DELL** | 0.8250 | 0.46% | 3 | 0.1967 |
| 6 | **MRNA** | 0.8243 | 3.22% | 4 | 0.2171 |
| 7 | **QCOM** | 0.8090 | 1.58% | 4 | 0.2284 |
| 8 | **CDNS** | 0.7985 | 0.72% | 4 | 0.1428 |
| 9 | **SMCI** | 0.7957 | 0.58% | 4 | 0.2477 |
| 10 | **MCHP** | 0.7886 | 0.71% | 4 | 0.1592 |


## Cómo interpretarlo

- **Predicción ≠ rentabilidad realizada.**
- La validación cronológica sirve para diagnóstico; no se suma al track record demo.
- El bootstrap está excluido del forward y fue generado antes de activar el sizing fraccionado; no se reescribe retrospectivamente.
- Cuando exista ledger forward, el NAV y los trades cerrados de cada experto se acumularán aquí.
- SPY y RSP son referencias, no modelos.

## Fuentes

- weekly_ml_state/forecasts/: forecasts forward inmutables.
- weekly_ml_state/ledger.json: NAV, órdenes y trades forward.
- weekly_ml_bootstrap_state/: bootstrap técnico inicial.
- strategy_state/dashboard.md: comparador global de todas las estrategias MIDAS.

