# MIDAS market_data — fase 1, issue #58

Estado: productor prospectivo y contrato inmutable, con integración incremental
como respaldo de barras RAW ausentes. La extracción única para todos los lectores
y la recuperación completa de libros pausados siguen pendientes.

## Integraciones de valoración diaria (27/10/2026)

- Clásicas y TimesFM: respaldo read-only integrado en PR #63 y #64.
- Buy The Dip: respaldo diario integrado en PR #65; la decisión mensual conserva
  historial ajustado y fundamentales independientes.
- Weekly ML: respaldo diario integrado en PR #67; RSP sigue siendo independiente
  porque no pertenece al snapshot. No se cambian forecast ni señales congeladas.
- Capital Cycle: esta entrega añade respaldo para la sesión actual después de
  comprobar el replay histórico. Requiere el panel histórico del benchmark y
  bloquea cualquier sesión anterior sin precios obligatorios.

Los lectores conservan precios propios discrepantes y registran el conflicto.
Esto NO demuestra una extracción única ni la paridad de las cinco familias.
No se han ejecutado capturas ni conciliaciones reales para validar estas PR.

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
- PSKY->SKYD efectivo 2026-10-06 modifica solo ticker del proveedor.

## Operativa y calidad

Las PR solo ejecutan unit tests y comprobación del universo.
Workflow market_data_xnys.yml: schedule 23:07 UTC laborables o dispatch explícito
con capture_session=true. No capturar ni publicar durante eventos push o PR.

Comandos de validación:
python -m unittest discover -s market_data/tests -v
python market_data/collect.py --phase check

## Pendiente para cerrar #58

1. Primer capture realmente programado con hash y cobertura verificables.
2. Recuperación versionada de símbolos ausentes, sin sobrescribir original.
3. Adaptadores read-only opt-in para clásicas y TimesFM, luego Buy The Dip,
   Capital Cycle y Weekly ML: completar la transición desde el respaldo a una
   captura compartida y verificar consumidores reales. Mantener FX, históricos
   ajustados y fundamentales separados.
4. Demostrar paridad de OHLC e independencia de cada libro bajo fallos.
5. Telemetría de fuente en Segundo Cerebro y verificación próxima sesión schedule.
6. Coordinar captura y consumidores por finalización efectiva; un cron anterior
   no garantiza que el archivo ya esté publicado. Weekly ML daily intenta primero
   a las 22:17 UTC y la captura común está programada a las 23:07 UTC.

Nunca insertar fills a posteriori ni alterar históricos, NAV, pesos o decisiones.
