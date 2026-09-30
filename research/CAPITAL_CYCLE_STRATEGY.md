# Estrategia MIDAS · Capital Cycle Inflection

Fecha de congelación metodológica: **2026-10-01**.

## 1. Objetivo

Formalizar en una estrategia cuantitativa, reproducible y prospectiva el método de inversión cíclica descrito por Albert Mendoza en el episodio de Inversión Racional analizado por MIDAS.

La regla no pretende traducir literalmente juicios cualitativos del gestor. Convierte sus ideas nucleares en proxies observables:

1. **capital atraído / repelido**;
2. **destrucción de oferta y depresión prolongada**;
3. **superviviente de bajo riesgo financiero**;
4. **precio/mercado confirmando que el giro ha empezado**;
5. **salida cuando vuelve el capital o se deteriora la tesis**.

## 2. Por qué el ciclo de capital tiene una base empírica

Marathon Asset Management define el capital cycle de forma muy cercana al podcast: retornos altos atraen capital y competencia; retornos bajos lo repelen; la inversión tiende a ser perjudicial para el accionista cuando la industria sobreinvierte, mientras que las oportunidades aparecen en industrias deprimidas donde la inversión cae. También da un papel central a la asignación de capital de la dirección.

Referencia:
- Marathon, *The Home of Capital Cycle Investing*: https://www.marathon.co.uk/the-home-of-capital-cycle-investing/

La literatura académica contiene varias piezas consistentes con ese mecanismo:

- **Titman, Wei y Xie (2004)**: las compañías que aumentan fuertemente la inversión de capital muestran posteriormente rentabilidades ajustadas peores.
  https://doi.org/10.1017/S0022109000003173
- **Cooper, Gulen y Schill (2008)**: el crecimiento de activos es un predictor negativo robusto de retornos futuros, incluso entre compañías de gran capitalización.
  https://doi.org/10.1111/j.1540-6261.2008.01370.x
- **Fama-French CMA**: el modelo de cinco factores incluye explícitamente *Conservative Minus Aggressive investment*.
  https://mba.tuck.dartmouth.edu/pages/faculty/Ken.french/Data_Library/f-f_5_factors_2x3.html

Esto no prueba que «comprar sectores hundidos» funcione siempre. De hecho, una evidencia reciente obliga a introducir una corrección importante: Chen, Dou, Guo y Ji (NBER 2026) documentan que **las industrias más distressed presentan menores retornos esperados** en su muestra. La estrategia por tanto no compra el máximo distress por sí mismo; exige calidad y señal de inflexión.

Referencia:
- *Industry Distress Anomaly*, NBER Working Paper 35513 (2026):
  https://www.nber.org/papers/w35513

## 3. No existe un reloj universal del ciclo

La estrategia no usa un único plazo porque el ciclo de precio y el ciclo de capacidad física operan a velocidades distintas.

El Banco Mundial estima, para commodities desde 1970, una duración media de los ciclos de aproximadamente **cuatro años**, con busts algo más largos que booms; entre 2020 y 2024 esa duración se redujo aproximadamente a la mitad. Esto descarta fijar mecánicamente «4 años» como regla de trading.

Referencia:
- World Bank, *Commodity Markets Outlook*, abril de 2025:
  https://www.worldbank.org/en/news/press-release/2025/04/29/commodity-markets-outlook-april-2025-press-release

A la vez, la respuesta de la **oferta física** puede ser muchísimo más lenta:
- IEA: una gran mina tarda de media **más de 16 años** desde descubrimiento a primera producción; más de 12 años en exploración/viabilidad y 4-5 años de construcción.
  https://www.iea.org/reports/the-role-of-critical-minerals-in-clean-energy-transitions/reliable-supply-of-minerals
- IEA 2025: los proyectos convencionales de petróleo han tardado cerca de **20 años** de licencia a primera producción; además, la producción convencional observada declina de media 5,6 % anual tras el pico y el deepwater ~10,3 %.
  https://www.iea.org/reports/the-implications-of-oil-and-gas-field-decline-rates/executive-summary

Conclusión: el algoritmo debe separar:
- **ciclo estructural de inversión:** años;
- **inflexión de cotización:** meses;
- **ejecución / revisión:** mensual.

## 4. Por qué se añade momentum a una estrategia contrarian

Comprar un sector solo porque lleva años cayendo es exactamente el error que se quiere evitar.

Jegadeesh y Titman (1993) documentaron persistencia de retornos a horizontes de 3-12 meses. MIDAS utiliza momentum no como tesis principal, sino como **filtro de confirmación** para no comprar una caída que todavía no ha girado.

Referencia:
- https://www.jstor.org/stable/2328882

El algoritmo exige dos de estas tres condiciones:
1. momentum 12-1 meses positivo;
2. momentum 6 meses positivo;
3. cotización sobre la media de 200 sesiones.

La consecuencia es deliberada: MIDAS renuncia a comprar el mínimo exacto a cambio de exigir evidencia de inflexión.

## 5. Por qué se añade calidad

La parte más peligrosa de un valle cíclico es que muchas compañías desaparecen. La señal correcta no es «empresa más rota», sino «superviviente capaz de llegar al siguiente ciclo».

La capa de calidad se inspira en dos familias de evidencia:
- Piotroski: la fortaleza de estados financieros ayuda a separar ganadores y perdedores dentro de acciones baratas.
- AQR *Quality Minus Junk*: rentabilidad, seguridad y disciplina financiera constituyen una dimensión económicamente relevante de calidad.
  https://www.aqr.com/Insights/Datasets/Quality-Minus-Junk-Factors-Daily

La v1 exige:
- flujo de caja operativo positivo;
- FCF positivo en al menos 2 de los últimos 3 ejercicios disponibles;
- deuda neta / OCF no extrema;
- cobertura de intereses razonable cuando el dato existe.

No se usa la calidad para buscar compounders; se usa para evitar quiebras antes del giro.

## 6. Horizonte concreto congelado en v1

| Capa | Ventana | Motivo |
| --- | --- | --- |
| Crecimiento de activos | 1 año + CAGR de 3-4 cuentas anuales | Detectar retirada de capital |
| CAPEX / ventas | último año vs mediana de los 2-3 anteriores | Detectar disciplina/capex descendente |
| Depresión relativa | ~3 años vs SPY | Capturar ciclo largo sin fijar 5 años rígidos |
| Drawdown | máximo disponible hasta 5 años | Señal complementaria de valoración/narrativa |
| Calidad | 3 ejercicios | Supervivencia |
| Valoración normalizada | FCF mediano 3 años + book-to-market | Evitar extrapolar un trimestre de pico |
| Inflexión | 6 meses, 12-1 meses, SMA200 | Confirmar giro |
| Ranking | mensual | Fundamentales no justifican rotación diaria |
| Holding mínimo | 3 meses, salvo salida dura | Histeresis/menos ruido |
| Holding máximo | no existe | Un ciclo no termina porque lo diga el calendario |

El último punto es importante: imponer un take-profit del 15 % o una venta obligatoria a 12 meses destruiría precisamente la convexidad que busca la estrategia cíclica.

## 7. Universo

Se reutiliza la lista S&P-derived congelada el 29/09/2026 para evitar que el universo cambie después del lanzamiento.

Primera criba por sectores:
- Energy
- Materials
- Industrials
- Utilities
- Consumer Discretionary
- Information Technology

Después se exige una mediana de CAPEX/ventas de al menos 2,5 %. Esto permite que entren, por ejemplo, negocios industriales/semiconductores/autos intensivos en capital y excluye buena parte de los negocios asset-light.

Limitación consciente de v1: el peer group congelado es **sector**, no GICS sub-industry. El capital cycle es conceptualmente más limpio a nivel industria. No se cambiará esta definición a mitad de campaña; una futura v2 podrá congelar subindustrias desde el día cero.

## 8. Scoring

### 8.1 Capital scarcity — 45 % del score final

A nivel compañía:
- crecimiento de activos 1 año: menor = mejor;
- CAGR de activos 3-4 años: menor = mejor;
- cambio de CAPEX/ventas frente a años previos: menor = mejor;
- retorno relativo ~3 años: peor histórico = mayor señal contrarian;
- drawdown desde máximo largo: mayor depresión = mayor señal.

A nivel sector se calcula la misma lógica sobre medianas. El `capital_scarcity_score` mezcla:
- 65 % posición de la empresa dentro de su sector;
- 35 % estado agregado del sector.

Así se evita llamar «ciclo de capital» a una mera acción individual barata dentro de una industria todavía sobreinvirtiendo.

### 8.2 Survivor quality — 30 %

Percentiles dentro de sector de:
- margen FCF normalizado;
- número de años con FCF positivo;
- margen operativo;
- deuda neta / OCF;
- cobertura de intereses.

Además existen gates absolutos de solvencia.

### 8.3 Valuation — 15 %

No se utiliza PER de último año porque en una cíclica puede ser más bajo justo en el pico.

Se usan:
- book-to-market;
- FCF yield calculado con FCF mediano de tres ejercicios.

Ambos se rankean contra pares de sector.

### 8.4 Inflection — 10 % + gate obligatorio

Tres votos:
- 12-1 momentum > 0;
- 6 meses > 0;
- precio > SMA200.

Entrada requiere 2/3.

## 9. Entradas

Una compañía solo puede entrar si:
- pasa el filtro de intensidad de capital;
- pasa supervivencia;
- quality score >= 40;
- sector scarcity >= 35;
- inflection >= 2/3;
- composite >= 60.

Luego se eligen las mejores hasta:
- máximo 12 compañías;
- máximo 4 por sector;
- máximo 10 % por compañía;
- máximo 95 % invertido;
- el efectivo no utilizado **se queda en cash**; no se fuerzan nombres mediocres.

## 10. Salidas

No hay stop/take-profit porcentual fijo.

Salida dura:
- deja de pasar supervivencia;
- las tres señales de inflexión son negativas;
- composite < 35.

Salida normal:
- una vez superados 3 meses de holding, composite < 45.

Ese descenso puede producirse porque:
- vuelve el crecimiento agresivo de activos/CAPEX;
- desaparece la baratura;
- empeora la calidad;
- se rompe la tendencia.

Esta es la traducción cuantitativa de «vender cuando el capital vuelve al sector», no de «vender porque la acción subió X %».

## 11. Ejecución

Señal: cierre de la última sesión XNYS de cada mes.

Fill: apertura de la siguiente sesión.

Costes:
- comisión 0,10 %;
- slippage 0,05 %;
- fracciones a 6 decimales;
- nominal mínimo 10 USD.

El motor corre cada día para:
- liquidar un rebalance pendiente en la apertura correcta;
- registrar NAV;
- procesar dividendos/splits;
- decidir únicamente cuando corresponde.

## 12. Por qué no se hace backtest fundamental retrospectivo ahora

Sería fácil producir un gráfico bonito y metodológicamente malo.

Yahoo entrega hoy estados financieros que pueden contener restatements; el universo congelado es el S&P actual y no su membresía histórica. Usar esos datos para «simular 2010-2026» introduce:
- look-ahead;
- survivorship bias;
- sesgo de restatement;
- potencial data snooping si se reajustan umbrales viendo resultados.

Por eso la v1 se pone a producir **prospectivamente**. El rendimiento solo empieza a contar desde su primer cierre registrado.

Para un backtest científico futuro hacen falta:
1. estados financieros point-in-time con fecha de publicación;
2. membresía histórica del universo;
3. delistings;
4. corporate actions históricas;
5. parámetros congelados antes de observar el periodo out-of-sample.

## 13. Hipótesis falsable

La estrategia no se da por válida por tener una historia económica convincente.

Hipótesis:
> el conjunto `underinvestment + supervivencia + valoración normalizada + inflexión` producirá, neto de costes simulados, una relación rentabilidad/drawdown competitiva frente a SPY/RSP y frente a las demás líneas MIDAS durante una muestra prospectiva suficientemente larga.

La comparación correcta se hará por:
- CAGR/anualización cuando exista suficiente historia;
- volatilidad;
- máximo drawdown;
- Sharpe/Sortino;
- turnover y costes;
- exposición media;
- hit-rate por posición;
- retorno vs SPY desde **la misma fecha de inicio**.

Hasta que no haya meses/años de observación, cualquier «ganador» es ruido.
