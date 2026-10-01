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


## Estrategia paper provisional v0 · 2026-10-01

El usuario ha autorizado iniciar una campaña prospectiva antes de completar el
corpus entero. Esta decisión **no convierte v0 en la estrategia canónica final del
canal**. La campaña queda identificada como `buy_the_dip_corpus_2026_v0` y sus
parámetros quedan congelados antes del primer fill.

### Evidencia fuente ya revisada que sí entra en v0

Los episodios recientes transcritos muestran de forma explícita y repetida estos
componentes de proceso:

- valoración centrada en FCF/earnings yield, caja neta, activos y descuento frente
  a comparables;
- preferencia por negocios que sobreviven el periodo malo y por estructuras de
  balance que permitan esperar;
- búsqueda de discrepancias: empresa/sector castigado aunque la economía del
  negocio o activo siga intacta;
- catalizadores identificables: recompras, monetización de activos, M&A,
  strategic review, entrada en producción, normalización operativa o recuperación
  sectorial;
- rotación por coste de oportunidad: una posición puede venderse aun conservando
  potencial si aparecen alternativas más atractivas;
- venta/reducción tras rerating cuando el precio deja de ofrecer el margen de
  seguridad buscado;
- caja como posición válida cuando faltan oportunidades claras;
- paciencia y prohibición práctica de perseguir precios;
- sizing menor cuando existe un riesgo no diversificable elevado, por ejemplo
  jurisdicción;
- aceptación de volatilidad si la tesis de largo plazo permanece intacta.

Vídeos de evidencia directa ya disponibles en el staging privado incluyen, entre
otros: `O_20WOPPhE4` (cartera septiembre 2026), `O-xScDlKoHE` (cartera julio
2026), `zSy6grQYrYU` (oportunidades actuales), `Vax3e_R44DI` (bonos/macro),
`Yze0sJEPHDg` y `aSL0Qx5AYUk` (petróleo), y `v-8ZPrcvIdM` (oro/activos
reales).

### Qué NO se atribuye a los hosts

Los pesos numéricos del score, umbrales, máximo de posiciones y proxies de
catalizador son decisiones de ingeniería para hacer el proceso ejecutable y
auditable. No se presentan como reglas textuales dichas por los autores.

La v0 usa:

- valoración 30 %;
- calidad/supervivencia 20 %;
- asignación de capital 15 %;
- dislocación 20 %;
- catalizador/inflection 15 %.

La señal se calcula mensualmente; el NAV se marca diariamente. No hay stop-loss
por porcentaje ni take-profit fijo: la salida depende de deterioro, rerating,
score o coste de oportunidad.

### Universo v0

Para no seleccionar retrospectivamente small caps internacionales después de ver
qué funcionó, v0 usa el universo S&P-derived ya congelado en MIDAS. Esto reduce la
fidelidad respecto a la parte internacional/special-situations del canal, pero
maximiza la auditabilidad de la primera campaña.

Una futura v1 global debe congelar su propio universo antes del primer fill y
arrancar con un diario nuevo.

### Criterio de competencia

Cada estrategia MIDAS conserva su frecuencia natural. La comparación se hace
sobre NAV observado y no obliga a Buy The Dip a operar semanal o diariamente.

Además de rentabilidad acumulada, el tablero debe registrar riesgo realizado:

- volatilidad anualizada adaptada a la cadencia observada;
- máximo drawdown;
- Sharpe realizado con rf=0 como estadístico descriptivo;
- número de observaciones.

Mientras no exista una ventana común suficiente, no se declara un ganador por
rentabilidad bruta entre campañas con fechas de inicio distintas.
