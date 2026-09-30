# MIDAS Capital Cycle

Cartera ficticia prospectiva que convierte el enfoque de **capital-cycle investing** explicado por Albert Mendoza en el episodio de Inversión Racional del 28/09/2026 en una regla auditable y repetible.

No replica una cartera del invitado ni intenta copiar sus posiciones. El objetivo es medir una hipótesis general:

> cuando una industria ha repelido capital durante años, la oferta futura queda disciplinada; si sobreviven compañías financieramente sólidas y el precio empieza a confirmar una inflexión, la recuperación del ciclo puede producir retornos extraordinarios.

## Qué hace

- parte del universo S&P-derived congelado de 503 acciones ya usado por MIDAS Weekly ML;
- limita el análisis inicial a sectores donde el ciclo de capital es económicamente interpretable;
- examina unas 3-4 cuentas anuales por empresa y ~3 años de comportamiento relativo;
- exige **supervivencia financiera** para no confundir destrucción de oferta con insolvencia;
- exige una **inflexión de precio** (2 de 3 señales: momentum 12-1, momentum 6 meses y precio sobre media de 200 sesiones);
- rankea mensualmente y mantiene como máximo 12 posiciones;
- registra señal al cierre y ejecuta la cartera ficticia en la siguiente apertura;
- no usa take-profit ni stop fijo: sale cuando se deteriora calidad/tendencia o cuando desaparece la señal de escasez de capital.

Capital inicial: 100.000 USD ficticios. Comisión 0,10 % y deslizamiento 0,05 % por lado. No existe conexión con ningún bróker.

## Frecuencias

- **fundamentales / ciclo de capital:** cada fin de mes;
- **ranking y rebalanceo:** cierre de la última sesión XNYS del mes;
- **fills ficticios:** apertura de la siguiente sesión;
- **valoración del diario:** cada sesión cerrada;
- **horizonte de señales:** 3 años para depresión/underinvestment y 6-12 meses para confirmar el giro;
- **histeresis:** una posición no se rota por ruido durante sus primeros 3 meses salvo fallo duro de calidad/ciclo.

No existe un «periodo correcto» único para un ciclo. La documentación de investigación explica por qué se usa un diseño multihorizonte.

## Archivos

- `config.json`: parámetros congelados de la campaña.
- `market.py`: calendario XNYS, precios y captura de estados financieros.
- `factors.py`: factores, rankings, filtros y selección.
- `engine.py`: contabilidad paper, corporate actions y ejecución next-open.
- `run.py`: orquestación diaria; solo descarga fundamentales cuando toca decisión mensual.
- `tests/`: pruebas sintéticas sin red.
- `../research/CAPITAL_CYCLE_STRATEGY.md`: fundamento académico y contrato metodológico.

## Criterio de honestidad experimental

La campaña **empieza hacia delante**. No se construye un backtest fundamental histórico con las cuentas actuales de Yahoo porque eso introduciría look-ahead/restatements y, usando el S&P actual, survivorship bias. Un backtest histórico solo se añadirá si MIDAS dispone de estados financieros *point-in-time* y membresía histórica del universo.

La estrategia queda congelada como `2026-10-01-capital-cycle-v1`; cualquier cambio de umbrales que pueda afectar resultados debe crear otra campaña y no reescribir el diario existente.
