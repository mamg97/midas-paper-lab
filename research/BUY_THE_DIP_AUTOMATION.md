# Buy The Dip · automatización de investigación

Fecha: 2026-10-01.

## Principio

Esta automatización es **solo investigación**. No modifica carteras paper existentes,
no cambia señales de Capital Cycle/Weekly ML/TFG y no escribe en ningún estado de
patrimonio. Su espacio persistente se limita a `buy_the_dip_state/`.

## Capas

1. `Buy The Dip corpus sync`
   - inventaría YouTube;
   - diagnostica captions con un vídeo canario;
   - mantiene la cola semántica;
   - cataloga el feed oficial de podcast como fuente secundaria de metadatos/audio
     para episodios largos inequívocamente emparejados;
   - nunca persiste audio ni transcripciones.

2. `Buy The Dip semantic review`
   - toma el siguiente episodio pendiente según prioridad;
   - descarga temporalmente el audio del feed oficial cuando el match con YouTube
     es inequívoco;
   - transcribe localmente con faster-whisper en CPU;
   - analiza la transcripción localmente con Qwen3-4B Q4 usando llama.cpp;
   - destruye audio y transcripción al terminar el job;
   - persiste únicamente paráfrasis estructuradas, timestamps de evidencia,
     reglas candidatas, dudas y proxies automatizables.

3. Consolidación
   - las salidas de un solo episodio son `machine_first_pass`;
   - ninguna mención aislada se convierte en regla canónica;
   - la estrategia final exige confirmación cruzada según
     `research/BUY_THE_DIP_SOURCE_STRATEGY.md`.

## Prioridad

`methodology -> portfolio_update -> sector_theme -> company_or_theme -> macro_market
-> guest_interview -> short`.

Así se aprende primero el proceso declarado y después se comprueba contra decisiones
de cartera.

## Frecuencia

El worker semántico corre dos veces al día y procesa un único episodio por ejecución.
La decisión limita consumo de CPU, evita jobs muy largos y reduce el riesgo de
conflictos de escritura. El corpus y el worker comparten un único grupo de
concurrencia `buy-the-dip-research-state`.

## Modelos locales

- ASR: `faster-whisper small`, CPU int8.
- Análisis: `Qwen/Qwen3-4B-GGUF`, cuantización Q4_K_M.

Ambos son descargados/cacheados por GitHub Actions. No requieren una API de pago.
Los runners estándar de este repositorio público se usan exclusivamente para esta
línea de investigación.

## Trazabilidad

Cada review persistente registra:
- vídeo canónico de YouTube;
- episodio del feed usado como transporte;
- score de matching;
- fecha;
- modelo ASR;
- modelo semántico;
- tipo de episodio;
- evidencia parafraseada con timestamps;
- regla candidata;
- nivel de confianza;
- proxy automatizable;
- necesidad de confirmación en otros vídeos.

No se versiona la transcripción completa.

## Cobertura y límites

El feed oficial cubre una parte, no la totalidad, de los 300 vídeos de YouTube.
Los episodios sin match seguro permanecen en cola. El sistema no inventa
equivalencias. Las vías de transporte pueden ampliarse posteriormente sin cambiar
la identidad canónica del corpus ni alterar reviews ya procesadas.

## Condición para paper trading

No se crea `buy_the_dip_corpus_2026` hasta que:
- los episodios metodológicos estén revisados;
- las actualizaciones de cartera relevantes estén contrastadas;
- exista matriz regla -> múltiples episodios;
- entradas, salidas y sizing estén especificados;
- las reglas sean convertibles a datos point-in-time;
- la configuración se congele antes del primer fill.

La futura campaña será independiente de `capital_cycle_inflection_2026`.
