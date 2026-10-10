# MIDAS Weekly ML — dashboard

> **Forward activo.** Última señal registrada: **2026-10-09**. Las predicciones mostradas abajo fueron congeladas antes de conocer la semana objetivo.

## Progreso

| Modelo | Función | Estado | NAV | Retorno acumulado | Posiciones/órdenes | Trades cerrados |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| **LightGBM Return** | Predice la rentabilidad semanal esperada de cada acción. | forward | 100,000.00 USD | 0.000% | 10 | 0 |
| **LightGBM Direction** | Estima la probabilidad de que la semana termine en positivo. | forward | 100,000.00 USD | 0.000% | 10 | 0 |
| **LightGBM Ranker** | Ordena el universo de mejor a peor oportunidad relativa. | forward | 98,378.10 USD | -1.622% | 10 | 10 |
| **MLP** | Red neuronal feed-forward sobre features tabulares. | forward | 99,805.42 USD | -0.195% | 10 | 10 |
| **LSTM** | Red temporal sobre la secuencia de las últimas 26 semanas. | forward | 97,553.21 USD | -2.447% | 10 | 10 |
| **ARIMA** | Modelo estadístico por acción sobre retornos semanales. | forward | 102,080.32 USD | 2.080% | 10 | 10 |
| **Ensemble** | Combina rankings y votos de los expertos anteriores. | forward | 97,564.03 USD | -2.436% | 10 | 10 |
| **SPY** | Benchmark S&P 500. | forward | 100,808.17 USD | 0.808% | 1 | 1 |
| **RSP** | Benchmark S&P 500 equiponderado. | forward | 101,146.06 USD | 1.146% | 1 | 1 |

## Predicciones del último forecast

**Cutoff:** 2026-10-09 · **Horizonte:** primera apertura → último cierre de la semana siguiente.

### LightGBM Return

Predice la rentabilidad semanal esperada de cada acción.

**Validación diagnóstica:** rank-IC 0.0153 · MAE 3.43 pp · iter 146

| # | Ticker | Retorno previsto |
| ---: | --- | ---: |
| 1 | **AMAT** | 1.70% |
| 2 | **TER** | 1.39% |
| 3 | **STX** | 1.39% |
| 4 | **PLTR** | 1.38% |
| 5 | **WDC** | 1.36% |
| 6 | **ON** | 1.32% |
| 7 | **MPWR** | 1.24% |
| 8 | **MCHP** | 1.15% |
| 9 | **LRCX** | 1.12% |
| 10 | **ORCL** | 1.12% |

### LightGBM Direction

Estima la probabilidad de que la semana termine en positivo.

**Validación diagnóstica:** accuracy 54.4% · Brier 0.2465 · iter 112

| # | Ticker | Prob. positiva |
| ---: | --- | ---: |
| 1 | **CSCO** | 62.0% |
| 2 | **ADI** | 61.8% |
| 3 | **ROST** | 61.7% |
| 4 | **SBAC** | 61.6% |
| 5 | **PFE** | 61.3% |
| 6 | **RJF** | 61.3% |
| 7 | **JCI** | 61.3% |
| 8 | **TXN** | 61.3% |
| 9 | **ICE** | 61.2% |
| 10 | **MSCI** | 61.2% |

### LightGBM Ranker

Ordena el universo de mejor a peor oportunidad relativa.

**Validación diagnóstica:** rank-IC 0.0259 · iter 16

| # | Ticker | Rank score |
| ---: | --- | ---: |
| 1 | **CMCSA** | 0.2842 |
| 2 | **HPE** | 0.2700 |
| 3 | **HII** | 0.2620 |
| 4 | **SWKS** | 0.2266 |
| 5 | **EXPE** | 0.2262 |
| 6 | **IBM** | 0.2218 |
| 7 | **MU** | 0.2138 |
| 8 | **DELL** | 0.1991 |
| 9 | **LVS** | 0.1894 |
| 10 | **COO** | 0.1712 |

### MLP

Red neuronal feed-forward sobre features tabulares.

**Validación diagnóstica:** rank-IC 0.0081 · MAE 3.81 pp

| # | Ticker | Retorno previsto |
| ---: | --- | ---: |
| 1 | **SMCI** | 10.18% |
| 2 | **TPL** | 9.75% |
| 3 | **ALB** | 8.38% |
| 4 | **RCL** | 7.74% |
| 5 | **GDDY** | 7.65% |
| 6 | **CHTR** | 7.20% |
| 7 | **PLTR** | 6.78% |
| 8 | **TER** | 6.50% |
| 9 | **ORCL** | 6.20% |
| 10 | **APTV** | 5.68% |

### LSTM

Red temporal sobre la secuencia de las últimas 26 semanas.

**Validación diagnóstica:** rank-IC 0.0475 · MAE 3.45 pp

| # | Ticker | Retorno previsto |
| ---: | --- | ---: |
| 1 | **INTC** | 1.41% |
| 2 | **ENPH** | 1.41% |
| 3 | **FSLR** | 1.34% |
| 4 | **QCOM** | 1.24% |
| 5 | **MGM** | 1.12% |
| 6 | **SMCI** | 1.10% |
| 7 | **AKAM** | 1.06% |
| 8 | **APTV** | 1.05% |
| 9 | **MU** | 1.02% |
| 10 | **NXPI** | 0.99% |

### ARIMA

Modelo estadístico por acción sobre retornos semanales.

**Validación diagnóstica:** —

| # | Ticker | Retorno previsto |
| ---: | --- | ---: |
| 1 | **PTC** | 5.94% |
| 2 | **MRNA** | 5.00% |
| 3 | **DELL** | 4.49% |
| 4 | **MU** | 4.48% |
| 5 | **HUM** | 4.33% |
| 6 | **CRWD** | 4.14% |
| 7 | **HPE** | 4.12% |
| 8 | **AMD** | 3.96% |
| 9 | **DE** | 3.67% |
| 10 | **PANW** | 3.66% |

### Ensemble

Combina rankings y votos de los expertos anteriores.

**Validación diagnóstica:** —

| # | Ticker | Score | Retorno previsto | Votos + | Dispersión |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | **WDC** | 0.9588 | 1.60% | 5 | 0.0195 |
| 2 | **TER** | 0.8967 | 1.77% | 5 | 0.1546 |
| 3 | **SMCI** | 0.8906 | 1.99% | 5 | 0.1362 |
| 4 | **CSCO** | 0.8391 | 1.08% | 5 | 0.1405 |
| 5 | **ADI** | 0.8129 | 0.59% | 5 | 0.1330 |
| 6 | **GNRC** | 0.8102 | 1.06% | 5 | 0.1325 |
| 7 | **HPE** | 0.8098 | 1.93% | 5 | 0.2482 |
| 8 | **GLW** | 0.8078 | 0.73% | 5 | 0.1573 |
| 9 | **CDW** | 0.8074 | 0.61% | 5 | 0.1060 |
| 10 | **ANET** | 0.8013 | 0.65% | 5 | 0.1564 |


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

