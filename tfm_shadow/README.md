# Cuatro modelos TFM en modo demo EUR

LightGBM, MLP, LSTM y ARIMA se reimplementaron con correcciones de cronología para 31 símbolos del universo IBEX estudiado en el TFM. Se entrenan de nuevo tras cada cierre elegible con datos conocidos hasta entonces. No se publican el texto de la tesis, los scripts originales ni los modelos serializados antiguos. Esta campaña **no reproduce exactamente** las arquitecturas, hiperparámetros ni métricas de la tesis.

Cada familia recibe una cartera virtual independiente de 100.000 EUR. La regla común provisional selecciona hasta diez activos cuya subida prevista al cierre siguiente supere el 0,3 %, con máximo del 15 % por entrada y 95 % invertido. Compra acciones enteras en la siguiente apertura y liquida al cierre; se modela 0,1 % de comisión y 0,05 % de deslizamiento por lado. Si falta una barra, divisa o sesión, se detiene. Un cierre perdido queda señalado como recuperación retrospectiva y no se presenta como ejecución en tiempo real.

Los pronósticos, evaluaciones y diario están separados en `tfm_state/`. La primera jornada genera pronósticos; hace falta al menos una posterior para medirlos. Pruebas sin red: `python3 -m unittest discover -s tfm_shadow/tests -v`. El workflow `.github/workflows/tfm_es.yml` se programa tras el cierre de Madrid.
