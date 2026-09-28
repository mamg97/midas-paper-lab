# MIDAS Paper Lab

Comparador prospectivo de estrategias de inversión **solo en modo demo**. Este repositorio comienza con un historial nuevo y contiene únicamente código seleccionado para esta campaña, configuraciones públicas y resultados de carteras ficticias. No incluye los archivos históricos, credenciales, documentos académicos ni diarios privados del proyecto de origen. No conecta con ningún bróker ni envía órdenes.

## Estado

La publicación y el primer registro con datos reales están pendientes. Un backtest, una prueba sintética o una señal calculada a posteriori no cuentan como rendimiento prospectivo. Cada línea del [registro](strategy_comparison/registry.json) indica si tiene diario propio o si todavía es una idea pendiente de adaptación.

Hay nueve carteras USD sobre ocho acciones estadounidenses y SPY, incluidas dos referencias y un genoma congelado antes de la campaña. También hay cuatro carteras EUR del universo IBEX del TFM: LightGBM, MLP, LSTM y ARIMA. Estas cuatro son **reimplementaciones corregidas de 2026** con la misma política de compraventa provisional; no reproducen literalmente la tesis. Las fechas, divisas y reglas difieren entre campañas, así que sus porcentajes no forman una clasificación común.

Las señales se calculan con información disponible al cierre. Las operaciones se modelan con la apertura o el cierre posterior, más comisión del 0,1 % y deslizamiento supuesto del 0,05 % por lado. Se registran órdenes pendientes, patrimonio, errores y sesiones omitidas. No se modelan todos los detalles de un bróker real; consulta [paper_demo](paper_demo/README.md) y [tfm_shadow](tfm_shadow/README.md).

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
