# MIDAS Paper Lab

Comparador prospectivo de estrategias de inversión **solo en modo demo**. Este repositorio comienza con un historial nuevo y contiene únicamente código seleccionado para esta campaña, configuraciones públicas y resultados de carteras ficticias. No incluye los archivos históricos, credenciales, documentos académicos ni diarios privados del proyecto de origen. No conecta con ningún bróker ni envía órdenes.

## Estado

El repositorio ya está publicado y ambos workflows están habilitados. Las nueve carteras USD iniciaron su diario el 28/09/2026: la primera sesión registró señales sin compras ejecutadas. La primera ejecución TFM se detuvo por un dato histórico inválido del proveedor y se corrigió el lector para el siguiente intento. Consulta el [estado fechado de los modelos ML](research/ML_ESTADO_2026-09-29.md) y el [tablero generado](strategy_state/dashboard.md) para ver el estado más reciente y no confundir una cartera configurada con una operación observada. Un backtest, una prueba sintética o una señal calculada a posteriori no cuentan como rendimiento prospectivo.

Hay nueve carteras USD sobre ocho acciones estadounidenses y SPY, incluidas dos referencias y un genoma congelado antes de la campaña. También hay cuatro carteras EUR del universo IBEX del TFM: LightGBM, MLP, LSTM y ARIMA. Estas cuatro son **reimplementaciones corregidas de 2026** con la misma política de compraventa provisional; no reproducen literalmente la tesis. Las fechas, divisas y reglas difieren entre campañas, así que sus porcentajes no forman una clasificación común.

Las señales se calculan con información disponible al cierre. Las operaciones se modelan con la apertura o el cierre posterior, más comisión del 0,1 % y deslizamiento supuesto del 0,05 % por lado. Las campañas nuevas admiten **acciones fraccionadas** cuando su política lo declara; Weekly ML y TFM usan 6 decimales y un nominal mínimo de 10 unidades de su divisa. Se registran órdenes pendientes, patrimonio, errores y sesiones omitidas. No se modelan todos los detalles de un bróker real; consulta [paper_demo](paper_demo/README.md) y [tfm_shadow](tfm_shadow/README.md).

## MIDAS Capital Cycle

Desde el 01/10/2026 existe además una campaña **Capital Cycle Inflection** sobre el universo S&P-derived congelado. Traduce a reglas prospectivas el ciclo de capital: años de retirada de inversión + supervivencia financiera + valoración normalizada + confirmación de giro de 6-12 meses. La primera ejecución registra una señal de lanzamiento y, desde entonces, el ranking se recalcula al cierre de cada mes; las órdenes son siempre ficticias y se modelan en la apertura posterior.

La metodología, fuentes empíricas, horizontes y límites están documentados en [research/CAPITAL_CYCLE_STRATEGY.md](research/CAPITAL_CYCLE_STRATEGY.md). No se publica un backtest fundamental retrospectivo con datos actuales porque sin estados financieros point-in-time y membresía histórica introduciría look-ahead y survivorship bias.

## MIDAS Weekly ML

👉 **[Dashboard visual de modelos y predicciones](WEEKLY_ML_DASHBOARD.md)**

Desde el 29/09/2026 existe además una campaña **semanal** sobre un universo S&P-derived congelado de 503 acciones. Combina LightGBM (retorno, dirección y ranking), MLP, LSTM, ARIMA y un ensemble de consenso, con SPY y RSP como referencias. Predice el retorno ejecutable de la semana siguiente (primera apertura → último cierre), entrena solo con etiquetas conocidas y mantiene una cartera ficticia independiente por experto.

El código y contrato están en [weekly_ml](weekly_ml/README.md). El workflow se ejecuta tras el cierre semanal de EE. UU. y no crea resultados retroactivos: hasta la primera señal prospectiva sus filas deben mostrarse como programadas/sin diario.

## Ejecución y coste

Los dos workflows se programan tras los cierres de Madrid y Nueva York, con ejecución manual disponible. En un repositorio público, GitHub indica que el uso de runners estándar de Actions es gratuito; esto no garantiza puntualidad, disponibilidad de datos ni ausencia de límites de uso. No se instala TimesFM ni se descargan sus pesos en cada ejecución. Los cuatro modelos TFM sí se entrenan diariamente con los datos conocidos hasta ese cierre; el genoma estadounidense permanece congelado. Se impone un máximo de 45 minutos al TFM y 30 al ciclo estadounidense. Consulta la [documentación oficial de facturación](https://docs.github.com/en/billing/concepts/product-billing/github-actions).

Los resultados ficticios se guardan en `paper_state/`, `tfm_state/` y `strategy_state/`. Las capturas brutas de Yahoo se mantienen fuera de Git; el estado conserva hashes y datos necesarios para la contabilidad, pero un lector externo no podrá reconstruir exactamente cada descarga sin una fuente equivalente. Los resultados públicos mostrarán señales, operaciones simuladas y patrimonio de capital ficticio.

## Comprobación local

```sh
python3 -m unittest discover -s paper_demo/tests -v
python3 -m unittest discover -s tfm_shadow/tests -v
python3 -m unittest discover -s strategy_comparison/tests -v
```

El [plan técnico](research/ROADMAP.md) separa las estrategias activas de las pendientes. [TimesFM](research/TIMESFM.md) es una hipótesis de investigación, no una cartera activada.

No se concede una licencia de reutilización del código por el mero hecho de publicar este repositorio; la licencia se decidirá por separado.
