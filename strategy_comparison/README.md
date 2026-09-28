# Inventario y tablero

`registry.json` enumera las nueve carteras estadounidenses, las cuatro adaptaciones TFM, el agente genético privado heredado y otras ideas históricas. Una entrada en el inventario **no implica ejecución**. Las rutas de origen privadas se han omitido deliberadamente. El tablero público solo procesa los diarios de este repositorio; el legado aparece como referencia pendiente y no recibe rentabilidad inventada.

```sh
python3 strategy_comparison/report.py \
  --registry strategy_comparison/registry.json \
  --paper-config paper_demo/config.json \
  --paper-state paper_state/state.json \
  --tfm-config tfm_shadow/config.json \
  --tfm-state tfm_state/ledger.json \
  --output strategy_state
```

Los estados son opcionales hasta el primer día. Un archivo presente pero corrupto detiene la generación del tablero.
