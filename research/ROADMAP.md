# Hoja de ruta técnica

1. Auditar el paquete público y lanzar una ejecución manual sin publicar datos privados. Verificar que cada workflow tiene permiso para registrar únicamente estado ficticio, pronósticos y tablero.
2. Observar el primer pronóstico y la primera liquidación. Marcar claramente sesiones perdidas, fallos de proveedor y diferencias entre los mercados estadounidense y español.
3. Medir durante meses cada cartera contra su referencia, con fechas de inicio, divisa, costes, rotación y drawdown. No ordenar carteras de campañas distintas como si compartieran las mismas condiciones.
4. Portar TFG 2021 (filtros técnicos, AHP y riesgo/rentabilidad), MIDAS R cripto y las variantes LightGBM semanales (retorno, dirección, precio y filtro conjunto), cada una con contrato de datos, calendario, control de información disponible y política de órdenes propios. Incorporar RSI largo/corto, Ichimoku corregido, gap intradía, Turtle corto, momentum y filtro fundamental solo cuando sus diferencias de contabilidad estén resueltas.
5. Separar entrenamiento periódico de inferencia diaria en el agente genético heredado y medir su coste. No copiar sus diarios ni sus secretos al repositorio público. Mantener Markowitz como asignador independiente, no como fuente de señales.
6. Evaluar TimesFM como predictor de referencia en un experimento prospectivo aislado; activarlo como cartera solo si hay una política de órdenes congelada y ventaja neta frente a referencias simples.


7. **Capital Cycle Inflection**: campaña prospectiva v1 implementada el 01/10/2026. Mantener congelados universo, pesos y umbrales durante la campaña; registrar ranking mensual, fills next-open, cobertura de datos y causas de salida. No optimizar parámetros sobre el diario forward. Añadir backtest histórico únicamente cuando existan fundamentales point-in-time, membresía histórica y delistings.
