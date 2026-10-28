# MIDAS market_data — fuente común, issue #58

Estado: fuente RAW diaria común obligatoria para las cinco familias. Las señales
ajustadas, los fundamentales, FX y el benchmark RSP siguen independientes.
La coordinación encadena consumidores después de la publicación verificada.

## Integraciones de valoración diaria (27/10/2026)

- Clásicas y TimesFM: respaldo read-only integrado en PR #63 y #64.
- Buy The Dip: respaldo diario integrado en PR #65; la decisión mensual conserva
  historial ajustado y fundamentales independientes.
- Weekly ML: respaldo diario integrado en PR #67; RSP sigue siendo independiente
  porque no pertenece al snapshot. No se cambian forecast ni señales congeladas.
- Capital Cycle: esta entrega añade respaldo para la sesión actual después de
  comprobar el replay histórico. Requiere el panel histórico del benchmark y
  bloquea cualquier sesión anterior sin precios obligatorios.

Las PR #63–#68 introdujeron inicialmente un respaldo; la política actual lee las
barras RAW de una única captura. La prueba de integración compara los cinco
adaptadores con los mismos bytes y comprueba que no reextraigan precios comunes.
Un símbolo común ausente permanece ausente; no se inventa una cotización.

## Contrato

- Universo fijo 503 del CSV 2026-09-29 y benchmark SPY aparte (504 consultas).
- Solo sesión XNYS recién cerrada, sin retroactividad ni órdenes reales.
- Archivo por sesión: market_data/snapshots/XNYS/YYYY-MM-DD.json.
- OHLC RAW, volumen, dividendos, splits, ticker canónico y del proveedor.
- Metadata: procedencia Yahoo/yfinance, timestamp UTC, coberturas, checksum SHA-256.
- Barras con fecha incorrecta, 0/NaN o rangos imposibles quedan como missing.
- Reintento aislado acotado; no se inventa la última cotización.
- Si menos del 90% de los 503 constituyentes tiene barra válida, no publicar.
- Escritura exclusiva atómica; reintentos con idénticas observaciones no alteran
  snapshot, fecha de captura o hash.
- Si el archivo de sesión ya existe, se valida y reutiliza sin consultar Yahoo.
  Un hash inválido o un universo distinto bloquean el reintento sin sobrescribirlo.
- Una revisión real de precios exige un artefacto complementario con procedencia
  y hash padre; nunca reescribir el JSON canónico silenciosamente.
- `YYYY-MM-DD.revisions/<sha256>.json` solo añade símbolos ausentes: cadena de
  hash base/padre, fecha real de recuperación y misma procedencia. Se rechazan
  alteraciones de barras existentes, ramas ambiguas, fechas erróneas y acciones
  corporativas que requieran revisión. La telemetría conserva hash base y efectivo.
- PSKY->SKYD efectivo 2026-10-06 modifica solo ticker del proveedor.

## Operativa y calidad

Las PR solo ejecutan unit tests y comprobación del universo.
Workflow market_data_xnys.yml: schedule 23:07 UTC laborables o dispatch explícito
con capture_session=true. No capturar ni publicar durante eventos push o PR.
Los consumidores reutilizables arrancan tras publicar; `run_consumers=true` los
habilita también en un dispatch explícito. Cada consumidor verifica la sesión
elegible y hace checkout de main con los bytes ya publicados. Sus schedules
independientes quedan como respaldo; los contadores de runtime del coordinador
no sobrescriben los contadores de esos workflows. `source_health.json` informa
por separado de calidad de fuente, resultados y libros actualizados/pausados.

Comandos de validación:
python -m unittest discover -s market_data/tests -v
python market_data/collect.py --phase check
python market_data/collect.py --phase recover
python market_data/health.py --eligible

## Pendiente para cerrar #58

1. Primer capture realmente programado con hash y cobertura verificables.
2. Verificar recuperación versionada y cadena coordinada en ejecución real.
3. Verificar consumidores reales, manteniendo las fuentes de distinta frecuencia.
4. Conservar independencia de libros bajo fallos y omisiones explícitas. La
   recuperación pasiva no crea operaciones: expira BUYs no ejecutados, añade solo
   marcas fechadas y exige evidencia para dividendos; estrategias activas o ventas
   históricas sin decisión suficiente siguen en espera de revisión.
5. Telemetría de fuente en Segundo Cerebro y verificación próxima sesión schedule.
6. Confirmar la siguiente sesión programada después de los cambios. La ejecución
   manual reparada del 28/10 publicó la sesión 27/10 (490/503 + SPY); no sustituye
   la prueba schedule. La primera captura schedule se perdió por .gitignore:
   su hash del log no permite reconstruir sus bytes originales.

Nunca insertar fills a posteriori ni alterar históricos, NAV, pesos o decisiones.
