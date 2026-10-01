# Buy The Dip · reconstrucción de estrategia desde fuente primaria

Fecha de inicio: **2026-10-01**.

Fuente canónica de esta línea de investigación:

- Canal: https://www.youtube.com/@Buy_The_Dip
- Channel ID: `UCS5I8A7UAu43QgFxxu8VRbQ`

Para esta línea concreta no se usarán artículos académicos, blogs de terceros,
hilos de redes ni interpretación de otros inversores como evidencia de qué hacen
los autores. Fuentes externas podrán utilizarse más adelante para **validar** una
regla ya extraída, pero nunca para introducir una regla ausente del canal.

## Objetivo

Reconstruir la estrategia real de los autores a partir de su historial completo de
vídeos y convertirla en una política paper auditable dentro de MIDAS.

La pregunta no es «qué acciones mencionan», sino:

1. cómo generan ideas;
2. qué entienden por empresa de calidad;
3. cómo valoran;
4. qué papel conceden a macro, ciclos y sectores odiados;
5. cuándo compran;
6. cómo construyen la cartera;
7. cuándo añaden;
8. qué les hace vender;
9. cómo tratan errores y tesis rotas;
10. qué partes de su proceso son repetibles con datos.

## Separación de evidencias

Cada vídeo se clasifica como una o más piezas de evidencia:

- `methodology`: describen explícitamente cómo buscan/analizan/invierten;
- `portfolio_update`: decisiones reales comunicadas sobre la cartera;
- `failures_lessons`: errores, pérdidas y revisiones de tesis;
- `sector_theme`: marco sectorial/cíclico;
- `company_or_theme`: análisis de empresa/idea;
- `macro_market`: contexto macro y de mercado;
- `guest_interview`: un invitado puede aportar ideas, pero **no define la
  estrategia de los hosts** salvo adopción posterior verificable;
- `short`: material auxiliar de baja prioridad metodológica.

## Regla para convertir una afirmación en regla canónica

Una regla solo entra en la estrategia automatizable si cumple al menos una de estas
condiciones:

- aparece explícitamente como parte del proceso en un episodio metodológico y no es
  contradicha posteriormente; o
- reaparece en al menos tres episodios de los hosts y en al menos dos periodos
  temporales diferentes; o
- puede observarse consistentemente en varias decisiones de cartera y además los
  hosts explican el criterio.

La frecuencia de una palabra no basta.

## Separar proceso de opinión

Se extraen por separado:

- **reglas invariantes**: calidad, valoración, deuda, tamaño, venta, etc.;
- **régimen/ciclo**: petróleo, oro, uranio, inflación, tipos, etc.;
- **tesis concretas**: empresas o sectores mencionados;
- **opiniones de invitados**.

Solo la primera capa puede formar el núcleo permanente de la estrategia. La segunda
puede actuar como filtro de régimen si se demuestra recurrente. La tercera no se
hardcodea. La cuarta requiere adopción explícita de los hosts.

## Qué se automatiza

Para cada regla canónica se exige:

- variable observable;
- fuente point-in-time;
- frecuencia;
- umbral o ranking;
- tratamiento de datos ausentes;
- regla de entrada;
- regla de mantenimiento;
- regla de salida;
- costes;
- timestamp de señal;
- timestamp de fill.

Si una idea esencial no puede expresarse con datos sin inventar un proxy débil,
permanece como componente discrecional y no se finge automatización.

## Corpus completo

El pipeline `buy_the_dip_corpus/build_corpus.py`:

1. inventaría las pestañas videos/directos/shorts del canal;
2. descarga captions a un directorio temporal;
3. elimina timestamps/markup;
4. calcula señales y temas;
5. destruye la transcripción al terminar;
6. persiste únicamente datos derivados.

Esto permite cubrir el canal entero sin almacenar una copia textual de contenido
ajeno.

## Política de transcripciones

Las transcripciones completas no se guardan en Git ni en Drive. Para el archivo de
trabajo se conservan **notas de análisis por vídeo**, paráfrasis, timestamps útiles
y extractos mínimos cuando sean necesarios. La transcripción literal se usa como
entrada temporal, no como archivo documental.

## Paper trading

La campaña actual `capital_cycle_inflection_2026` no se renombra ni se modifica
para hacerla encajar en el resultado del corpus.

Una vez cerrada la extracción, se creará una estrategia nueva, por ejemplo
`buy_the_dip_corpus_2026`, con:

- configuración congelada;
- diario separado;
- capital ficticio;
- next-open;
- costes explícitos;
- benchmark desde la misma fecha;
- integración en `strategy_comparison`;
- comparación en Segundo Cerebro.

No se lanzará una campaña diciendo que representa el canal completo hasta que la
cobertura de captions y la revisión semántica de episodios prioritarios sean
suficientes.

## Criterio de cierre de investigación

Antes de congelar v1:

- 100 % del catálogo público inventariado;
- captions disponibles contabilizados y faltantes documentados;
- 100 % de episodios metodológicos y de cartera revisados semánticamente;
- episodios de invitados separados;
- matriz regla → episodios de evidencia;
- entradas, mantenimiento y salidas explícitos;
- contradicciones históricas documentadas;
- parámetros definidos antes del primer fill.



## Validación de ingestión en Colab · 2026-10-01

La prueba controlada sobre los 10 últimos vídeos del canal terminó con **10/10
transcripciones recuperadas** y **0 fallos**, usando exclusivamente
`youtube-transcript-api` desde una sesión de Google Colab.

Resultados del lote:

- 65.198 palabras recuperadas;
- idioma español en los 10 casos;
- tiempo por vídeo entre ~0,9 s y ~11,4 s;
- sin necesidad de `yt-dlp` ni Whisper en el lote validado.

Esto confirma que el bloqueo observado en GitHub Actions era de red/IP cloud y no
una ausencia general de captions del canal.

Arquitectura operativa a partir de esta validación:

- **Colab** = ingestión desde YouTube y checkpoint reanudable;
- **Drive privado** = staging temporal/operativo del corpus;
- **GitHub/MIDAS** = metadatos, análisis derivado y estrategia, nunca dependencia
  directa de YouTube para la extracción;
- **Segundo Cerebro** = consumo de la campaña paper final, separada de las campañas
  existentes.

La expansión al corpus completo debe procesar únicamente vídeos pendientes,
reutilizar resultados previos, guardar checkpoint tras cada vídeo, espaciar
peticiones y detenerse temporalmente si aparecen errores consecutivos.

Esta validación no modifica ni reetiqueta ninguna campaña MIDAS activa.
