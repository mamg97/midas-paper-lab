# MIDAS Weekly ML — dashboard

> **Estado actual:** bootstrap técnico completado. La campaña forward oficial todavía no ha generado su primera señal semanal. El bootstrap del 25/09/2026 se muestra aquí solo para visualizar y comprobar el sistema; está excluido del rendimiento prospectivo.

## Vista rápida

| Modelo | Qué hace | Posiciones | Resultado MTM bootstrap |
| --- | --- | ---: | ---: |
| **LightGBM Return** | Predice la rentabilidad semanal esperada (%) de cada acción. | 0 | 0.000% |
| **LightGBM Direction** | Estima la probabilidad de que la semana termine en positivo. | 10 | -0.578% |
| **LightGBM Ranker** | Ordena las acciones de mejor a peor oportunidad relativa sin exigir acertar el % exacto. | 10 | -1.416% |
| **MLP** | Red neuronal feed-forward que estima la rentabilidad semanal usando las features tabulares. | 10 | -1.492% |
| **LSTM** | Red recurrente que busca patrones en la secuencia de las últimas 26 semanas. | 10 | -1.200% |
| **ARIMA** | Modelo estadístico por acción que extrapola la dinámica reciente de retornos semanales. | 10 | -1.642% |
| **Ensemble** | Combina rankings, retornos previstos y votos positivos de los expertos. | 10 | -1.343% |
| **SPY** | Referencia de mercado S&P 500. | 1 | -0.479% |
| **RSP** | Referencia S&P 500 equiponderado. | 1 | -0.309% |

## Ensemble — selección bootstrap

Señal reconstruida al cierre del **2026-09-25**, entrada simulada en la apertura del **2026-09-28** y valoración al cierre del mismo día. No cuenta como forward.

| # | Ticker | Score | Retorno previsto | Votos positivos | Dispersión |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | **SMCI** | 0.8598 | 0.87% | 5 | 0.1721 |
| 2 | **KMX** | 0.8106 | 0.97% | 5 | 0.1559 |
| 3 | **AKAM** | 0.8077 | 0.60% | 5 | 0.2377 |
| 4 | **ANET** | 0.7872 | 1.24% | 5 | 0.1813 |
| 5 | **FDS** | 0.7804 | 0.60% | 5 | 0.1849 |
| 6 | **DASH** | 0.7789 | 0.78% | 5 | 0.1410 |
| 7 | **AMAT** | 0.7765 | 1.01% | 5 | 0.1895 |
| 8 | **META** | 0.7716 | 2.18% | 5 | 0.1969 |
| 9 | **PAYC** | 0.7678 | 0.92% | 5 | 0.1461 |
| 10 | **WDAY** | 0.7466 | 0.52% | 4 | 0.2241 |
| 11 | **CRL** | 0.7366 | 0.62% | 5 | 0.1725 |
| 12 | **ORCL** | 0.7335 | 0.56% | 4 | 0.2753 |
| 13 | **EXPE** | 0.7295 | 0.49% | 4 | 0.2224 |
| 14 | **AXON** | 0.7213 | 0.54% | 4 | 0.2632 |
| 15 | **LRCX** | 0.7211 | 0.91% | 5 | 0.2566 |
| 16 | **MTD** | 0.7200 | 0.36% | 5 | 0.1568 |
| 17 | **PYPL** | 0.7161 | 0.39% | 4 | 0.1756 |
| 18 | **HUM** | 0.7155 | 1.71% | 4 | 0.3552 |
| 19 | **TER** | 0.7106 | 0.64% | 5 | 0.2610 |
| 20 | **IBM** | 0.7088 | 0.51% | 4 | 0.2432 |

## Predicciones por modelo

### LightGBM Return

Predice la rentabilidad semanal esperada (%) de cada acción.

**Validación cronológica diagnóstica:** rank-IC -0.0110 · MAE 3.51 pp · best iteration 1

**Selección paper:** ninguna posición superó el umbral configurado.

### LightGBM Direction

Estima la probabilidad de que la semana termine en positivo.

**Validación cronológica diagnóstica:** accuracy 53.7% · Brier 0.2479 · best iteration 59

| # | Ticker | Señal/predicción | Entrada simulada | Cierre bootstrap | P&L MTM |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | **AKAM** | 59.9% prob. | 112.91 | 108.99 | -338.46 USD |
| 2 | **DDOG** | 59.9% prob. | 257.13 | 268.70 | 407.32 USD |
| 3 | **EFX** | 59.9% prob. | 146.75 | 145.78 | -71.69 USD |
| 4 | **EQIX** | 59.9% prob. | 1009.36 | 1011.07 | 6.27 USD |
| 5 | **GEN** | 59.9% prob. | 21.50 | 20.85 | -296.46 USD |
| 6 | **MSFT** | 59.9% prob. | 505.72 | 509.22 | 53.85 USD |
| 7 | **CMCSA** | 59.7% prob. | 21.93 | 21.79 | -70.37 USD |
| 8 | **JPM** | 59.7% prob. | 342.00 | 336.59 | -155.33 USD |
| 9 | **NEE** | 59.7% prob. | 76.07 | 75.49 | -81.11 USD |
| 10 | **PYPL** | 59.7% prob. | 54.41 | 54.28 | -31.60 USD |

### LightGBM Ranker

Ordena las acciones de mejor a peor oportunidad relativa sin exigir acertar el % exacto.

**Validación cronológica diagnóstica:** rank-IC 0.0397 · best iteration 7

| # | Ticker | Señal/predicción | Entrada simulada | Cierre bootstrap | P&L MTM |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | **FSLR** | 0.1840 | 178.22 | 172.97 | -287.65 USD |
| 2 | **FICO** | 0.1731 | 853.29 | 840.89 | -145.75 USD |
| 3 | **ENPH** | 0.1595 | 32.18 | 30.91 | -381.69 USD |
| 4 | **TER** | 0.1106 | 394.90 | 401.30 | 144.19 USD |
| 5 | **INTC** | 0.1102 | 120.74 | 116.03 | -376.82 USD |
| 6 | **AMAT** | 0.1015 | 482.44 | 486.76 | 72.89 USD |
| 7 | **MU** | 0.0953 | 1076.52 | 1053.98 | -188.92 USD |
| 8 | **SWKS** | 0.0935 | 89.44 | 87.59 | -206.08 USD |
| 9 | **KLAC** | 0.0932 | 186.80 | 189.17 | 108.99 USD |
| 10 | **DELL** | 0.0911 | 552.02 | 543.43 | -155.34 USD |

### MLP

Red neuronal feed-forward que estima la rentabilidad semanal usando las features tabulares.

**Validación cronológica diagnóstica:** rank-IC -0.0060 · MAE 3.96 pp

| # | Ticker | Señal/predicción | Entrada simulada | Cierre bootstrap | P&L MTM |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | **GNRC** | 16.42% | 207.51 | 205.21 | -113.00 USD |
| 2 | **COIN** | 9.24% | 196.19 | 191.79 | -220.52 USD |
| 3 | **META** | 5.94% | 750.41 | 715.62 | -426.55 USD |
| 4 | **ANET** | 5.68% | 205.69 | 204.92 | -45.01 USD |
| 5 | **DOW** | 5.38% | 28.32 | 27.89 | -153.25 USD |
| 6 | **HUM** | 5.24% | 397.63 | 389.63 | -193.12 USD |
| 7 | **AKAM** | 4.88% | 112.91 | 108.99 | -338.46 USD |
| 8 | **PSKY** | 4.74% | 9.90 | 10.28 | 349.81 USD |
| 9 | **SMCI** | 4.46% | 42.77 | 41.78 | -228.55 USD |
| 10 | **HWM** | 3.97% | 231.11 | 228.32 | -123.68 USD |

### LSTM

Red recurrente que busca patrones en la secuencia de las últimas 26 semanas.

**Validación cronológica diagnóstica:** rank-IC 0.0395 · MAE 3.51 pp

| # | Ticker | Señal/predicción | Entrada simulada | Cierre bootstrap | P&L MTM |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | **APTV** | 1.44% | 44.52 | 43.64 | -197.40 USD |
| 2 | **ENPH** | 1.25% | 32.18 | 30.91 | -381.69 USD |
| 3 | **NKE** | 1.14% | 35.48 | 36.39 | 234.10 USD |
| 4 | **FICO** | 1.08% | 853.29 | 840.89 | -145.75 USD |
| 5 | **BLDR** | 1.02% | 58.09 | 58.01 | -22.35 USD |
| 6 | **MGM** | 0.97% | 32.71 | 31.86 | -254.92 USD |
| 7 | **NCLH** | 0.94% | 14.46 | 14.31 | -106.06 USD |
| 8 | **FDS** | 0.93% | 270.20 | 267.67 | -97.83 USD |
| 9 | **AKAM** | 0.91% | 112.91 | 108.99 | -338.46 USD |
| 10 | **HRL** | 0.89% | 19.72 | 19.97 | 110.83 USD |

### ARIMA

Modelo estadístico por acción que extrapola la dinámica reciente de retornos semanales.

| # | Ticker | Señal/predicción | Entrada simulada | Cierre bootstrap | P&L MTM |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | **DELL** | 5.94% | 552.02 | 543.43 | -155.34 USD |
| 2 | **INTC** | 5.86% | 120.74 | 116.03 | -376.82 USD |
| 3 | **MRNA** | 4.99% | 195.25 | 197.28 | 87.94 USD |
| 4 | **MU** | 4.02% | 1076.52 | 1053.98 | -188.92 USD |
| 5 | **VLO** | 3.98% | 389.30 | 389.57 | -2.97 USD |
| 6 | **META** | 3.96% | 750.41 | 715.62 | -426.55 USD |
| 7 | **AMD** | 3.82% | 625.21 | 607.87 | -269.52 USD |
| 8 | **HPE** | 3.78% | 62.78 | 62.63 | -32.34 USD |
| 9 | **MPWR** | 3.76% | 1353.81 | 1351.20 | -27.72 USD |
| 10 | **ARE** | 3.47% | 49.92 | 48.66 | -249.83 USD |

## Cómo leer este dashboard

- **Predicción** no equivale a rentabilidad realizada.
- **Validación cronológica** es diagnóstico histórico; no se suma al track record demo.
- **Bootstrap** es una prueba retrospectiva única para verificar el pipeline.
- **Forward** empezará con el primer forecast creado automáticamente después de un cierre semanal real; desde entonces las selecciones y NAV quedarán congelados y acumulados.

## Archivos fuente

- Bootstrap completo: `weekly_ml_bootstrap_state/bootstrap_2026-09-25.md`
- JSON íntegro: `weekly_ml_bootstrap_state/bootstrap_2026-09-25.json`
- Campaña: `weekly_ml/`
- Comparador global: `strategy_state/dashboard.md`
