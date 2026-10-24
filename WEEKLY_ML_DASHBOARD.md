# MIDAS Weekly ML — dashboard

> **Forward activo.** Última señal registrada: **2026-10-23**. Las predicciones mostradas abajo fueron congeladas antes de conocer la semana objetivo.

## Progreso

| Modelo | Función | Estado | NAV | Retorno acumulado | Posiciones/órdenes | Trades cerrados |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| **LightGBM Return** | Predice la rentabilidad semanal esperada de cada acción. | forward | 83,303.11 USD | -16.697% | 0 | 20 |
| **LightGBM Direction** | Estima la probabilidad de que la semana termine en positivo. | forward | 100,506.34 USD | 0.506% | 10 | 20 |
| **LightGBM Ranker** | Ordena el universo de mejor a peor oportunidad relativa. | forward | 92,121.11 USD | -7.879% | 10 | 30 |
| **MLP** | Red neuronal feed-forward sobre features tabulares. | forward | 90,217.00 USD | -9.783% | 10 | 30 |
| **LSTM** | Red temporal sobre la secuencia de las últimas 26 semanas. | forward | 90,535.57 USD | -9.464% | 10 | 30 |
| **ARIMA** | Modelo estadístico por acción sobre retornos semanales. | forward | 89,964.45 USD | -10.036% | 10 | 30 |
| **Ensemble** | Combina rankings y votos de los expertos anteriores. | forward | 84,004.64 USD | -15.995% | 10 | 30 |
| **SPY** | Benchmark S&P 500. | forward | 97,452.76 USD | -2.547% | 1 | 3 |
| **RSP** | Benchmark S&P 500 equiponderado. | forward | 101,877.34 USD | 1.877% | 1 | 3 |

## Predicciones del último forecast

**Cutoff:** 2026-10-23 · **Horizonte:** primera apertura → último cierre de la semana siguiente.

### LightGBM Return

Predice la rentabilidad semanal esperada de cada acción.

**Validación diagnóstica:** rank-IC 0.0196 · MAE 3.43 pp · iter 8

| # | Ticker | Retorno previsto |
| ---: | --- | ---: |
| 1 | **A** | 0.10% |
| 2 | **AAPL** | 0.10% |
| 3 | **ABBV** | 0.10% |
| 4 | **ABNB** | 0.10% |
| 5 | **ABT** | 0.10% |
| 6 | **ACGL** | 0.10% |
| 7 | **ACN** | 0.10% |
| 8 | **ADBE** | 0.10% |
| 9 | **ADI** | 0.10% |
| 10 | **ADM** | 0.10% |

### LightGBM Direction

Estima la probabilidad de que la semana termine en positivo.

**Validación diagnóstica:** accuracy 56.8% · Brier 0.2436 · iter 158

| # | Ticker | Prob. positiva |
| ---: | --- | ---: |
| 1 | **ROST** | 58.3% |
| 2 | **LMT** | 57.4% |
| 3 | **SOLV** | 57.4% |
| 4 | **LVS** | 57.3% |
| 5 | **WRB** | 57.1% |
| 6 | **TKO** | 56.9% |
| 7 | **WMT** | 56.6% |
| 8 | **MAR** | 56.6% |
| 9 | **KO** | 56.5% |
| 10 | **ESS** | 56.4% |

### LightGBM Ranker

Ordena el universo de mejor a peor oportunidad relativa.

**Validación diagnóstica:** rank-IC 0.0112 · iter 78

| # | Ticker | Rank score |
| ---: | --- | ---: |
| 1 | **STX** | 0.6406 |
| 2 | **MU** | 0.6069 |
| 3 | **TER** | 0.6026 |
| 4 | **MRNA** | 0.5422 |
| 5 | **GLW** | 0.5286 |
| 6 | **HPE** | 0.5170 |
| 7 | **AKAM** | 0.5160 |
| 8 | **WDC** | 0.4884 |
| 9 | **DELL** | 0.4830 |
| 10 | **VST** | 0.4622 |

### MLP

Red neuronal feed-forward sobre features tabulares.

**Validación diagnóstica:** rank-IC 0.0031 · MAE 3.85 pp

| # | Ticker | Retorno previsto |
| ---: | --- | ---: |
| 1 | **CEG** | 13.09% |
| 2 | **NRG** | 11.42% |
| 3 | **VST** | 6.60% |
| 4 | **AXON** | 6.42% |
| 5 | **QCOM** | 6.29% |
| 6 | **LUV** | 5.14% |
| 7 | **GDDY** | 4.22% |
| 8 | **HPQ** | 3.47% |
| 9 | **APH** | 3.38% |
| 10 | **TER** | 3.29% |

### LSTM

Red temporal sobre la secuencia de las últimas 26 semanas.

**Validación diagnóstica:** rank-IC 0.0301 · MAE 3.44 pp

| # | Ticker | Retorno previsto |
| ---: | --- | ---: |
| 1 | **SMCI** | 1.30% |
| 2 | **MGM** | 1.28% |
| 3 | **KLAC** | 1.20% |
| 4 | **LKQ** | 1.15% |
| 5 | **BLDR** | 1.14% |
| 6 | **NRG** | 1.11% |
| 7 | **F** | 1.03% |
| 8 | **AXON** | 1.03% |
| 9 | **WYNN** | 1.01% |
| 10 | **DECK** | 0.99% |

### ARIMA

Modelo estadístico por acción sobre retornos semanales.

**Validación diagnóstica:** —

| # | Ticker | Retorno previsto |
| ---: | --- | ---: |
| 1 | **HAS** | 12.40% |
| 2 | **LKQ** | 9.78% |
| 3 | **ROP** | 7.13% |
| 4 | **MRNA** | 7.10% |
| 5 | **POOL** | 6.92% |
| 6 | **VLO** | 5.15% |
| 7 | **MPC** | 4.82% |
| 8 | **PAYC** | 4.44% |
| 9 | **WDAY** | 3.62% |
| 10 | **EFX** | 3.45% |

### Ensemble

Combina rankings y votos de los expertos anteriores.

**Validación diagnóstica:** —

| # | Ticker | Score | Retorno previsto | Votos + | Dispersión |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | **DDOG** | 0.8366 | 0.96% | 5 | 0.1545 |
| 2 | **HPQ** | 0.8011 | 1.08% | 5 | 0.1602 |
| 3 | **AXON** | 0.7833 | 1.56% | 5 | 0.2633 |
| 4 | **VTRS** | 0.7587 | 0.31% | 4 | 0.1834 |
| 5 | **IBM** | 0.7409 | 1.02% | 5 | 0.1749 |
| 6 | **PTC** | 0.7232 | 0.96% | 5 | 0.1934 |
| 7 | **ZBRA** | 0.7225 | 0.43% | 5 | 0.1560 |
| 8 | **ROST** | 0.7184 | 0.42% | 5 | 0.1651 |
| 9 | **NTAP** | 0.7092 | 0.65% | 5 | 0.1532 |
| 10 | **GDDY** | 0.7088 | 0.55% | 5 | 0.1768 |


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

