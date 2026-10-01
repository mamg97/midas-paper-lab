# Buy The Dip · corpus canónico para MIDAS

Este módulo usa como fuente primaria **solo** el canal de YouTube Buy The Dip
(`https://www.youtube.com/@Buy_The_Dip`) para reconstruir el proceso inversor de
sus autores y separar lo que es metodología recurrente de lo que es una idea
puntual, opinión macro o tesis de un invitado.

## Regla de copyright y trazabilidad

Las transcripciones/captions **nunca se versionan en Git**. Tras la validación del
01/10/2026, la ingestión operativa se ejecuta desde Google Colab y puede usar una
zona privada de staging en Drive para checkpoints y revisión. El repositorio solo
conserva metadatos y señales derivadas: recuentos de conceptos, topics, cobertura,
clasificación del vídeo y puntuación de relevancia metodológica.

El repositorio tampoco pretende atribuir a los autores una regla que no pueda
rastrearse a varios episodios o a un episodio explícitamente metodológico.

## Fases

1. **Inventario completo**: vídeos, directos y Shorts del canal.
2. **Cobertura de captions**: idioma y número de palabras; el texto no entra en Git
   y, cuando se usa staging privado, queda separado del estado de estrategias.
3. **Cribado de todo el corpus**: conceptos recurrentes, topic modelling y
   clasificación de cada episodio.
4. **Lectura semántica uno a uno**: los episodios con mayor señal metodológica se
   revisan manualmente y se documentan en Drive con resumen/paráfrasis.
5. **Contrato de estrategia**: solo entran reglas repetidas por los hosts o
   declaradas como parte de su proceso.
6. **Automatización**: cada regla debe poder expresarse con datos point-in-time.
7. **Paper trading**: se congela una campaña nueva y compite en MIDAS. No se
   retoca el diario al ver resultados.

La campaña `capital_cycle_inflection_2026` existente sigue siendo un experimento
separado, derivado de un marco cíclico concreto. No se renombra como si representase
todo el canal.

## Salidas

- `buy_the_dip_state/manifest.json`: catálogo de la fuente.
- `buy_the_dip_state/corpus_features.json`: señales derivadas por vídeo.
- `buy_the_dip_state/corpus_report.json`: cobertura y temas agregados.
- `buy_the_dip_state/corpus_report.md`: resumen auditable.


## Incidencia Colab 01/10/2026 y ruta operativa

La primera prueba de Colab recuperó correctamente 10/10 transcripciones mediante
`youtube-transcript-api`. Una ejecución posterior, en otra VM de Colab, quedó
bloqueada desde el primer vídeo pendiente con `RequestBlocked`. Por tanto, una
ejecución exitosa en Colab no garantiza que otra VM del pool de Google conserve
una IP aceptada por YouTube.

No se debe insistir con múltiples reintentos sobre la misma IP bloqueada, ni usar
cookies personales, proxies o mecanismos para eludir los controles de YouTube.

La ruta de contingencia estable es ejecutar la ingestión desde el Mac del usuario,
usando su conexión normal, con `buy_the_dip_corpus/local_transcribe.py`. El runner:

- carga el manifest canónico completo;
- reanuda por vídeo y conserva checkpoints;
- intenta transcript API, luego captions con yt-dlp y, solo si es necesario,
  audio + Whisper;
- se detiene si detecta que toda la conexión está bloqueada;
- escribe en el Drive local sincronizado cuando Google Drive for Desktop está
  disponible, o en un staging local configurable mediante `BTD_OUT`;
- no toca ninguna campaña paper ni los diarios de MIDAS.
