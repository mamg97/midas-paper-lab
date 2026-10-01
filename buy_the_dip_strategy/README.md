# MIDAS · Buy The Dip corpus v0

Campaña paper prospectiva derivada **solo** del corpus primario del canal Buy The Dip.

## Qué representa

La v0 automatiza la parte repetible observada en los episodios ya transcritos:

- comprar negocios/activos que el mercado ofrece a valoraciones exigentes a la baja;
- priorizar FCF/earnings yield, caja o balance razonable y descuento frente a pares;
- buscar dislocaciones y sectores/negocios temporalmente castigados;
- exigir alguna señal de catalizador/inflection antes de entrar;
- premiar recompras y penalizar dilución;
- mantener caja cuando faltan oportunidades;
- rotar una posición todavía barata cuando aparece una oportunidad claramente mejor;
- vender por deterioro de tesis cuantificable o por rerating suficiente;
- evitar perseguir precios y permitir periodos de espera.

No hardcodea empresas mencionadas en el canal ni tesis concretas de petróleo, oro,
uranio, cine, bancos o mineras. Esas menciones sirvieron para extraer el proceso,
no para preseleccionar ganadores.

## Limitación deliberada de v0

El canal opera con small/mid caps internacionales y situaciones especiales que no
quedan bien representadas por un universo S&P 500. Para poder lanzar una campaña
prospectiva auditable sin introducir un universo retrospectivamente seleccionado,
v0 usa el mismo universo S&P-derived congelado que otras líneas MIDAS.

Una futura v1 nativa puede ampliar a un universo global congelado. Eso deberá
iniciar **otra campaña**, sin reescribir el diario v0.

## Frecuencia

- cierre diario: valoración NAV y riesgo;
- fin de mes: reranking fundamental;
- excepción de lanzamiento: primera señal en el primer cierre elegible;
- fill: siguiente apertura XNYS;
- permanencia mínima orientativa: 3 meses salvo hard exit.

## Cartera

- 100.000 USD ficticios;
- máximo 10 posiciones;
- máximo 15 % por posición;
- máximo 3 nombres y 30 % por sector;
- exposición variable según oportunidades: 0/50/70/90/95 %;
- comisión 0,10 % + slippage 0,05 %;
- acciones fraccionadas;
- sin stop-loss porcentual ni take-profit mecánico.

## Score v0

Los pesos son decisiones de automatización congeladas **antes del primer fill**,
no porcentajes declarados por los hosts:

- valoración: 30 %;
- calidad/supervivencia: 20 %;
- asignación de capital: 15 %;
- dislocación: 20 %;
- catalizador/inflection: 15 %.

Financials se puntúa con earnings yield + book-to-market + ROE/beneficio, porque
FCF corporativo no es una métrica equivalente para bancos.

## Integridad

No se hace backtest fundamental con estados financieros actuales. La campaña
empieza forward-only para evitar look-ahead, restatements y survivorship.
