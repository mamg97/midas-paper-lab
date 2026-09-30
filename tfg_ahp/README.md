# TFG 2021 → TFG Corrected 2026

Esta carpeta convierte el algoritmo del TFG de 2021 en una **campaña paper prospectiva** sin modificar el script original.

Fuente histórica privada:

`MIDAS_GIT/SIMULACIONES INVERSIONES/SIMULACIONES PASADAS/CODIGO_TFG_simulacion.R`

La versión productiva mantiene la arquitectura de tres filtros del TFG, pero corrige las magnitudes que en 2021 estaban calculadas sobre niveles de precio o tenían una ejecución no reproducible.

## Qué conserva del TFG

### Filtro 1 — técnico

Se reproducen las cuatro familias y la misma lógica OR del original:

- MACD 12/26/9: proporción de las últimas 35 sesiones con histograma positivo > 0,80.
- RSI propio del TFG: proporción de las últimas 35 sesiones con RSI <= 30 > 0,90.
- Estocástico basado en cierres: proporción con slow-K <= 20 > 0,90.
- Bollinger 20/2: proporción con %B > 1 > 0,90.

Si cualquiera supera su umbral, el activo pasa.

No se relajan los umbrales para fabricar candidatos. Si no hay suficientes activos para construir la cartera, el sistema puede quedarse parcialmente o totalmente en efectivo.

### Filtro 2 — multicriterio AHP corregido

El TFG usaba:

- rentabilidad media diaria;
- inversa de la desviación típica de **niveles de precio**;
- una magnitud llamada beta calculada también con **niveles de precio**;
- comparaciones por pares interpoladas a escala Saaty.

La versión 2026 mantiene el espíritu multicriterio, pero usa magnitudes comparables y causales:

- rentabilidad media diaria de 40 sesiones;
- volatilidad de **retornos** de 252 sesiones, prefiriendo menor volatilidad;
- beta convencional de **retornos** frente a SPY, prefiriendo menor beta.

Cada criterio se transforma en percentil cross-sectional y recibe peso 1/3. Se conservan los 30 mejores candidatos. Esto se denomina **AHP-style corrected score**; no se presenta como una réplica bit a bit de `ahpsurvey::ahp`.

### Filtro 3 — retorno frente a MAD

Como en el TFG:

- riesgo = desviación absoluta media de los últimos 40 retornos diarios;
- utilidad = rentabilidad media diaria - MAD;
- se escogen hasta 15 activos;
- los pesos se obtienen por interpolación lineal respecto al siguiente candidato y se normalizan.

Se añade un límite de 15 % por posición, 95 % máximo invertido y acciones fraccionadas.

## Ejecución

La señal se genera solo después de una semana cerrada.

```
viernes/cierre semanal
  ↓
filtros 1 → 2 → 3
  ↓
pesos objetivo congelados
  ↓
primera apertura de la semana siguiente
  ↓
compra paper fraccionada
  ↓
seguimiento de cierres diarios
  ↓
si cartera <= -1,2 % desde entrada: salida en la apertura siguiente
  ↓
si no: salida en el último cierre de la semana
```

El stop de -1,2 % del TFG se hace causal: el cierre que detecta el umbral no puede ejecutarse retroactivamente; la salida se simula en la apertura siguiente.

Costes:

- comisión 0,10 % por lado;
- slippage 0,05 % por lado;
- fracciones a 6 decimales;
- nominal mínimo 10 USD.

## Universo inicial

Para poder ponerlo a trabajar con datos homogéneos se usa el snapshot S&P-derived de 503 valores congelado el 29/09/2026, el mismo utilizado por Weekly ML.

Esto **no es el universo global de 20 mercados del TFG original**. La versión global requiere reconciliar símbolos, divisas y calendarios y seguirá siendo un experimento separado.

## Qué NO se conserva deliberadamente

- riesgo medido con desviación de precios;
- beta sobre niveles de precio;
- mezcla de divisas sin FX;
- salida impresa a -1,2 % pero resultado final calculado como si se mantuviera toda la semana;
- compuestos a 10 años derivados directamente de una media diaria histórica;
- ejecución al mismo precio usado para tomar la decisión.

## Estado

Esta versión es una adaptación nueva y debe juzgarse únicamente por su track record paper prospectivo. El TFG original queda inmutable como referencia histórica.
