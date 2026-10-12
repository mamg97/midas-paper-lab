# MIDAS — Política canónica de universo S&P 500 (vigencia: 13/10/2026)

## Regla prospectiva obligatoria
Todas las **estrategias candidatas a competir** deben tomar como universo
elegible la misma instantánea congelada:
`weekly_ml/universe_sp500_2026-09-29.csv`, **503 símbolos de las acciones
de las empresas que forman el S&P 500** (algunas empresas tienen dos clases
de acciones). La lista verificada coincide con la instantánea mantenida
por el agente genético privado. No se permite sustituirla silenciosamente
por una selección de ocho, treinta, treinta y una o cien acciones.

**Evaluar el universo no equivale a comprarlo entero.** Filtros por sector,
calidad, liquidez o fundamentales son parte de cada estrategia, pero deben
ser registrados con denominadores auditables: símbolos elegibles, con datos,
excluidos y motivos, puntuados y finalmente comprados.

Cambios de constituyentes futuros requieren nueva instantánea fechada y
una transición de campaña acordada: los índices cambian con el tiempo.
La cobertura real debe acreditarse; señalar 'S&P500 configurado' no prueba
que el proveedor haya suministrado 503 cotizaciones.

## Campañas previas (nunca empalmar curvas)

* `paper_demo`: nueve carteras del conjunto de **8 acciones**. Continúan
  conservadas, pero sus filas son **no elegibles para la competición común**
  desde esta política, hasta construir una variante nueva S&P 500 con
  **nuevo capital ficticio de 100.000 USD**, nuevo ID y diario, y sin backfill.
* `tfm_shadow`: cuatro carteras de **31 valores IBEX**, mercado XMAD/EUR.
  Las originales son legado y no deben confundirse con los expertos
  ARIMA, MLP, LSTM y LightGBM **semanales S&P500** disponibles en el
  motor weekly ML. Una nueva adaptación estadounidense requiere nuevo
  motor/diario (calendario XNYS, USD, causalidad y costes homogéneos).
* `weekly_ml`, `tfg_ahp`, `capital_cycle`, `buy_the_dip_strategy`
  ya apuntan a la instantánea completa; sus reglas pueden restringir
  el conjunto final.
* El agente genético privado contiene la misma lista de 503 símbolos,
  pero su NAV no se mezcla con operaciones, símbolos o carteras de otros
  repositorios.
* TimesFM 2.5 semanal (5 sesiones) y diario (1 sesión) se amplían
  **antes de su primera ejecución de mercado** al archivo completo
  y exigen cobertura >=90% de series útiles para pronosticar.
  Ambos diarios EUR 100.000 quedan separados e irreconciliables entre sí
  sin registrar nuevas campañas.

## Regla de visualización y comparación
`strategy_state/dashboard.json` expone `comparison_eligible`,
`comparison_universe_id`, `comparison_universe_symbols` y
`comparison_exclusion_reason`. El laboratorio privado solo debe usar
filas elegibles en su **tabla de competición actual**. La biblioteca
histórica puede enseñar resultados antiguos con etiqueta de universo,
sin falsear comparaciones. Referencias como SPY/RSP son **benchmarks**
y no modelos que analicen 503 acciones.

Además del universo, comparabilidad de rentabilidad exige fechas,
divisas, NAV, comisiones y tipos de cambio en periodos comunes. No usar
retorno USD como si fuera retorno EUR.
