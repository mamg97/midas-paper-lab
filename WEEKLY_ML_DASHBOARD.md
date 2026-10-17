# MIDAS Weekly ML — dashboard

> **Forward activo.** Última señal registrada: **2026-10-16**. Las predicciones mostradas abajo fueron congeladas antes de conocer la semana objetivo.

## Progreso

| Modelo | Función | Estado | NAV | Retorno acumulado | Posiciones/órdenes | Trades cerrados |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| **LightGBM Return** | Predice la rentabilidad semanal esperada de cada acción. | forward | 88,064.38 USD | -11.936% | 10 | 10 |
| **LightGBM Direction** | Estima la probabilidad de que la semana termine en positivo. | forward | 99,314.10 USD | -0.686% | 10 | 10 |
| **LightGBM Ranker** | Ordena el universo de mejor a peor oportunidad relativa. | forward | 95,617.71 USD | -4.382% | 10 | 20 |
| **MLP** | Red neuronal feed-forward sobre features tabulares. | forward | 94,126.49 USD | -5.874% | 10 | 20 |
| **LSTM** | Red temporal sobre la secuencia de las últimas 26 semanas. | forward | 90,161.31 USD | -9.839% | 10 | 20 |
| **ARIMA** | Modelo estadístico por acción sobre retornos semanales. | forward | 90,891.33 USD | -9.109% | 10 | 20 |
| **Ensemble** | Combina rankings y votos de los expertos anteriores. | forward | 85,030.64 USD | -14.969% | 10 | 20 |
| **SPY** | Benchmark S&P 500. | forward | 98,617.27 USD | -1.383% | 1 | 2 |
| **RSP** | Benchmark S&P 500 equiponderado. | forward | 101,208.54 USD | 1.209% | 1 | 2 |

## Predicciones del último forecast

**Cutoff:** 2026-10-16 · **Horizonte:** primera apertura → último cierre de la semana siguiente.

### LightGBM Return

Predice la rentabilidad semanal esperada de cada acción.

**Validación diagnóstica:** rank-IC 0.0049 · MAE 3.41 pp · iter 72

| # | Ticker | Retorno previsto |
| ---: | --- | ---: |
| 1 | **HPE** | 1.47% |
| 2 | **SMCI** | 1.46% |
| 3 | **DELL** | 1.41% |
| 4 | **LRCX** | 1.40% |
| 5 | **TER** | 1.36% |
| 6 | **GLW** | 1.36% |
| 7 | **KLAC** | 1.36% |
| 8 | **ANET** | 1.35% |
| 9 | **JBL** | 1.34% |
| 10 | **CRWD** | 1.34% |

### LightGBM Direction

Estima la probabilidad de que la semana termine en positivo.

**Validación diagnóstica:** accuracy 54.4% · Brier 0.2464 · iter 54

| # | Ticker | Prob. positiva |
| ---: | --- | ---: |
| 1 | **GDDY** | 60.2% |
| 2 | **CDW** | 59.8% |
| 3 | **UPS** | 59.7% |
| 4 | **TYL** | 59.7% |
| 5 | **AAPL** | 59.7% |
| 6 | **ON** | 59.7% |
| 7 | **EIX** | 59.6% |
| 8 | **MO** | 59.6% |
| 9 | **DELL** | 59.5% |
| 10 | **KLAC** | 59.5% |

### LightGBM Ranker

Ordena el universo de mejor a peor oportunidad relativa.

**Validación diagnóstica:** rank-IC 0.0321 · iter 29

| # | Ticker | Rank score |
| ---: | --- | ---: |
| 1 | **DELL** | 0.4897 |
| 2 | **STX** | 0.4487 |
| 3 | **MU** | 0.4471 |
| 4 | **HPE** | 0.4378 |
| 5 | **MRNA** | 0.4143 |
| 6 | **WDC** | 0.3982 |
| 7 | **TER** | 0.3568 |
| 8 | **PLTR** | 0.3134 |
| 9 | **ORCL** | 0.3087 |
| 10 | **INTC** | 0.3068 |

### MLP

Red neuronal feed-forward sobre features tabulares.

**Validación diagnóstica:** rank-IC -0.0106 · MAE 3.87 pp

| # | Ticker | Retorno previsto |
| ---: | --- | ---: |
| 1 | **MU** | 10.13% |
| 2 | **GLW** | 9.16% |
| 3 | **STX** | 8.19% |
| 4 | **AMAT** | 6.42% |
| 5 | **APA** | 6.13% |
| 6 | **AMD** | 5.97% |
| 7 | **DELL** | 5.64% |
| 8 | **HPE** | 4.40% |
| 9 | **LRCX** | 4.31% |
| 10 | **SLB** | 4.28% |

### LSTM

Red temporal sobre la secuencia de las últimas 26 semanas.

**Validación diagnóstica:** rank-IC 0.0330 · MAE 3.44 pp

| # | Ticker | Retorno previsto |
| ---: | --- | ---: |
| 1 | **MGM** | 1.37% |
| 2 | **AXON** | 1.33% |
| 3 | **FICO** | 1.21% |
| 4 | **SMCI** | 1.19% |
| 5 | **NCLH** | 1.15% |
| 6 | **WYNN** | 1.13% |
| 7 | **UAL** | 1.12% |
| 8 | **BLDR** | 1.09% |
| 9 | **ORCL** | 1.04% |
| 10 | **FSLR** | 1.04% |

### ARIMA

Modelo estadístico por acción sobre retornos semanales.

**Validación diagnóstica:** —

| # | Ticker | Retorno previsto |
| ---: | --- | ---: |
| 1 | **DELL** | 9.39% |
| 2 | **MRNA** | 6.48% |
| 3 | **CRWD** | 5.58% |
| 4 | **SMCI** | 5.57% |
| 5 | **ANET** | 4.78% |
| 6 | **LW** | 4.77% |
| 7 | **WDC** | 4.71% |
| 8 | **MU** | 4.34% |
| 9 | **PANW** | 4.07% |
| 10 | **AMD** | 4.02% |

### Ensemble

Combina rankings y votos de los expertos anteriores.

**Validación diagnóstica:** —

| # | Ticker | Score | Retorno previsto | Votos + | Dispersión |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | **MU** | 0.9727 | 2.83% | 5 | 0.0353 |
| 2 | **WDC** | 0.9502 | 2.22% | 5 | 0.0408 |
| 3 | **DELL** | 0.9441 | 3.52% | 5 | 0.1088 |
| 4 | **STX** | 0.9116 | 1.54% | 5 | 0.0852 |
| 5 | **KLAC** | 0.8906 | 1.09% | 5 | 0.1280 |
| 6 | **CDW** | 0.8712 | 0.95% | 5 | 0.0842 |
| 7 | **IT** | 0.8647 | 1.05% | 5 | 0.0730 |
| 8 | **PTC** | 0.8628 | 1.05% | 5 | 0.0852 |
| 9 | **ANET** | 0.8522 | 2.06% | 5 | 0.1650 |
| 10 | **SMCI** | 0.8476 | 1.33% | 4 | 0.2938 |


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

