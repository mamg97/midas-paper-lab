# TimesFM: hipótesis para MIDAS

La publicación original de TimesFM describe un modelo preentrenado para pronosticar series temporales sin ajuste por cada serie. Google publicó TimesFM 3 en agosto de 2026 con soporte multivariante. Esa capacidad de pronóstico **no implica** rentabilidad bursátil después de comisiones ni sustituye una regla de entrada, salida y tamaño de posición.

La versión 2.5 (200 millones de parámetros) tiene pesos Apache-2.0; los pesos preentrenados de la versión 3 (330 millones) se distribuyen por ahora con restricciones de uso no comercial y no productivo. Para un primer experimento reproducible y separable de la campaña diaria, estudiar TimesFM 2.5 sin instalarlo en los workflows. Sus pesos requieren una descarga grande. No se incorporarán pesos a Git.

Diseño propuesto: fijar antes del primer pronóstico el universo, horizonte de una sesión, longitud de contexto, versión del modelo y reglas de cartera. Registrar predicciones fechadas antes de conocer el cierre siguiente. Comparar error y dirección con paseo aleatorio, así como rentabilidad neta ficticia frente a las referencias de MIDAS. Guardar fallos y latencia. Evitar usar una prueba histórica solapada con el preentrenamiento como evidencia de ventaja prospectiva.

Fuentes: [artículo original](https://arxiv.org/abs/2310.10688), [anuncio TimesFM 3 de Google Research](https://research.google/blog/timesfm-3-a-zero-shot-foundation-model-for-multivariate-forecasting/), [repositorio y licencias](https://github.com/google-research/timesfm), [estudio de predicción de rentabilidades financieras](https://arxiv.org/abs/2606.27100).
