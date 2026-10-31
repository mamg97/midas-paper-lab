# MIDAS Weekly ML — dashboard

> **Forward activo.** Última señal registrada: **2026-10-30**. Las predicciones mostradas abajo fueron congeladas antes de conocer la semana objetivo.

## Progreso

| Modelo | Función | Estado | NAV | Retorno acumulado | Posiciones/órdenes | Trades cerrados |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| **LightGBM Return** | Predice la rentabilidad semanal esperada de cada acción. | forward | 83,303.11 USD | -16.697% | 0 | 20 |
| **LightGBM Direction** | Estima la probabilidad de que la semana termine en positivo. | forward | 100,705.31 USD | 0.705% | 0 | 30 |
| **LightGBM Ranker** | Ordena el universo de mejor a peor oportunidad relativa. | forward | 91,590.01 USD | -8.410% | 10 | 40 |
| **MLP** | Red neuronal feed-forward sobre features tabulares. | forward | 88,626.43 USD | -11.374% | 10 | 40 |
| **LSTM** | Red temporal sobre la secuencia de las últimas 26 semanas. | forward | 94,154.92 USD | -5.845% | 10 | 40 |
| **ARIMA** | Modelo estadístico por acción sobre retornos semanales. | forward | 91,562.09 USD | -8.438% | 10 | 40 |
| **Ensemble** | Combina rankings y votos de los expertos anteriores. | forward | 81,698.70 USD | -18.301% | 10 | 40 |
| **SPY** | Benchmark S&P 500. | forward | 96,384.70 USD | -3.615% | 1 | 4 |
| **RSP** | Benchmark S&P 500 equiponderado. | forward | 102,241.57 USD | 2.242% | 1 | 4 |

## Predicciones del último forecast

**Cutoff:** 2026-10-30 · **Horizonte:** primera apertura → último cierre de la semana siguiente.

### LightGBM Return

Predice la rentabilidad semanal esperada de cada acción.

**Validación diagnóstica:** rank-IC -0.0108 · MAE 3.44 pp · iter 6

| # | Ticker | Retorno previsto |
| ---: | --- | ---: |
| 1 | **A** | 0.08% |
| 2 | **AAPL** | 0.08% |
| 3 | **ABBV** | 0.08% |
| 4 | **ABNB** | 0.08% |
| 5 | **ABT** | 0.08% |
| 6 | **ACGL** | 0.08% |
| 7 | **ACN** | 0.08% |
| 8 | **ADBE** | 0.08% |
| 9 | **ADI** | 0.08% |
| 10 | **ADM** | 0.08% |

### LightGBM Direction

Estima la probabilidad de que la semana termine en positivo.

**Validación diagnóstica:** accuracy 55.9% · Brier 0.2448 · iter 91

| # | Ticker | Prob. positiva |
| ---: | --- | ---: |
| 1 | **NEM** | 50.8% |
| 2 | **ERIE** | 50.7% |
| 3 | **FCX** | 50.6% |
| 4 | **RMD** | 50.5% |
| 5 | **RVTY** | 50.5% |
| 6 | **CRL** | 50.4% |
| 7 | **ALB** | 50.4% |
| 8 | **MSI** | 50.4% |
| 9 | **COIN** | 50.3% |
| 10 | **NOW** | 50.3% |

### LightGBM Ranker

Ordena el universo de mejor a peor oportunidad relativa.

**Validación diagnóstica:** rank-IC -0.0042 · iter 8

| # | Ticker | Rank score |
| ---: | --- | ---: |
| 1 | **AKAM** | 0.1305 |
| 2 | **NOW** | 0.1267 |
| 3 | **ORCL** | 0.1252 |
| 4 | **CRWD** | 0.1228 |
| 5 | **MRNA** | 0.1147 |
| 6 | **AMAT** | 0.1135 |
| 7 | **PANW** | 0.1118 |
| 8 | **STX** | 0.1103 |
| 9 | **MU** | 0.1092 |
| 10 | **HPE** | 0.1072 |

### MLP

Red neuronal feed-forward sobre features tabulares.

**Validación diagnóstica:** rank-IC -0.0001 · MAE 3.86 pp

| # | Ticker | Retorno previsto |
| ---: | --- | ---: |
| 1 | **INTU** | 10.53% |
| 2 | **PYPL** | 7.28% |
| 3 | **DXCM** | 6.80% |
| 4 | **DVA** | 6.61% |
| 5 | **PANW** | 5.52% |
| 6 | **BLDR** | 5.30% |
| 7 | **CRWD** | 5.16% |
| 8 | **DDOG** | 5.10% |
| 9 | **MRK** | 4.97% |
| 10 | **FICO** | 4.71% |

### LSTM

Red temporal sobre la secuencia de las últimas 26 semanas.

**Validación diagnóstica:** rank-IC 0.0300 · MAE 3.45 pp

| # | Ticker | Retorno previsto |
| ---: | --- | ---: |
| 1 | **MGM** | 1.14% |
| 2 | **NRG** | 1.10% |
| 3 | **AXON** | 1.05% |
| 4 | **CAT** | 1.01% |
| 5 | **ODFL** | 1.00% |
| 6 | **WYNN** | 0.99% |
| 7 | **APTV** | 0.96% |
| 8 | **LII** | 0.96% |
| 9 | **CHRW** | 0.95% |
| 10 | **CHTR** | 0.93% |

### ARIMA

Modelo estadístico por acción sobre retornos semanales.

**Validación diagnóstica:** —

| # | Ticker | Retorno previsto |
| ---: | --- | ---: |
| 1 | **NOW** | 8.39% |
| 2 | **FFIV** | 7.36% |
| 3 | **NCLH** | 6.00% |
| 4 | **MRNA** | 5.34% |
| 5 | **FTNT** | 4.70% |
| 6 | **HPQ** | 4.45% |
| 7 | **CRWD** | 3.84% |
| 8 | **BBY** | 3.80% |
| 9 | **ROP** | 3.78% |
| 10 | **MPC** | 3.63% |

### Ensemble

Combina rankings y votos de los expertos anteriores.

**Validación diagnóstica:** —

| # | Ticker | Score | Retorno previsto | Votos + | Dispersión |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | **PLTR** | 0.8575 | 1.82% | 4 | 0.1663 |
| 2 | **NOW** | 0.8258 | 0.52% | 5 | 0.2211 |
| 3 | **ERIE** | 0.7877 | 0.84% | 5 | 0.1670 |
| 4 | **MGM** | 0.7764 | 1.37% | 4 | 0.1733 |
| 5 | **ARE** | 0.7123 | 0.28% | 4 | 0.1641 |
| 6 | **MRK** | 0.7117 | 0.59% | 4 | 0.1808 |
| 7 | **COIN** | 0.7086 | 0.34% | 4 | 0.3504 |
| 8 | **AXON** | 0.7072 | 0.36% | 3 | 0.3013 |
| 9 | **FCX** | 0.7069 | 0.27% | 4 | 0.1934 |
| 10 | **MAR** | 0.7062 | 0.77% | 4 | 0.1553 |


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

