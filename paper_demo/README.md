# Nueve carteras demo USD

Cada cartera parte de 100.000 USD ficticios. El universo fijo tiene AAPL, AMZN, JNJ, JPM, KO, MSFT, NVDA y XOM; SPY sirve de referencia. Hay dos referencias de comprar y mantener, EMA/RSI fijo, genoma congelado, MACD, reversión RSI, ruptura Bollinger y Turtle largo 20/10 y 55/20. Estas reglas son adaptaciones nuevas; el genoma congelado se seleccionó antes de empezar el diario prospectivo y **no** reproduce el agente S&P 500 heredado. El test histórico de ese genoma obtuvo 10,61 % frente a 19,87 % de la referencia equiponderada bajo los supuestos de aquella prueba: no es una rentabilidad demo ni evidencia de superioridad.

Al cierre D se anota la señal; al conocerse la barra final D+1 se simula la apertura D+1 para las órdenes pendientes. Stop y objetivo se modelan con OHLC, suponiendo primero el stop si ambos son posibles en la misma barra. El cálculo admite fracciones y no modela spread real, liquidez, impuestos ni rechazos. Una sesión perdida queda marcada y nunca crea una señal retroactiva. Más de cinco sesiones omitidas bloquean el diario.

`state.json` conserva saldos, posiciones, eventos y hashes. Las capturas de mercado se guardan localmente en `snapshots/`, excluido de Git público. `leaderboard.csv` y `.json` se derivan del estado. El mismo día no duplica operaciones.

Pruebas sin red: `python3 -m unittest discover -s paper_demo/tests -v`. El workflow `.github/workflows/paper_us.yml` ejecuta la campaña tras el cierre de Nueva York. El primer día solo registra señales; las primeras operaciones se pueden contabilizar desde la siguiente sesión.
