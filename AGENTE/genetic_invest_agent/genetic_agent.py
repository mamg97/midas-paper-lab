"""
================================================================================
  GENETIC TRADING AGENT
  ─────────────────────
  Implementa un Algoritmo Genético para encontrar la mejor estrategia de trading.
  Una vez evolucionado, el mejor agente analiza los datos recientes del mercado
  y emite una señal: COMPRAR, VENDER o ESPERAR con niveles de TP y SL.

  Dependencias: pip install pandas numpy yfinance
================================================================================
"""

import random
import math
import warnings
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

# ──────────────────────────────────────────────
# CONFIGURACIÓN GLOBAL
# ──────────────────────────────────────────────
TICKER = "BTC-USD"            # Activo a analizar
TRAINING_YEARS = 2            # Años de datos históricos para entrenamiento
POPULATION_SIZE = 50          # Número de agentes por generación
NUM_GENERATIONS = 20          # Generaciones de evolución
INITIAL_CAPITAL = 10_000.0    # Capital inicial por agente (USD)
DEATH_THRESHOLD = 5_000.0     # Portfolio mínimo; por debajo el agente muere
COMMISSION = 0.001            # Comisión por operación (0.1 %)
INVEST_FRACTION = 0.95        # Fracción del efectivo que se invierte por trade

# Rangos del genotipo
# Nota de diseño: cada gen codifica un parámetro numérico de la estrategia.
#   rsi_overbought → nivel por encima del cual NO compramos (filtro de sobrecompra)
#   rsi_oversold   → nivel de RSI por debajo del cual cerramos la posición larga
#                    (filtro de momentum de salida)
GENOME_RANGES = {
    "fast_ma":          (5, 30),      # Periodo EMA Rápida
    "slow_ma":          (20, 200),    # Periodo EMA Lenta
    "rsi_period":       (7, 21),      # Periodo RSI
    "rsi_overbought":   (60, 85),     # Umbral sobrecompra: NO entrar si RSI > este valor
    "rsi_oversold":     (15, 40),     # Umbral de salida: cerrar largo si RSI cae por debajo
    "stop_loss_pct":    (0.01, 0.08), # % Stop Loss  (1 – 8 %)
    "take_profit_pct":  (0.02, 0.20), # % Take Profit (2 – 20 %)
}

# Probabilidades evolutivas
MUTATION_RATE = 0.15           # Probabilidad de mutar cada gen
MUTATION_STRENGTH = 0.25       # Cuánto puede variar un gen: fracción del rango
ELITE_FRACTION = 0.1           # Top % que pasa directo a la siguiente generación
CROSSOVER_FRACTION = 0.6       # % de la nueva población creada por crossover


# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO 1: DESCARGA Y PREPARACIÓN DE DATOS
# ══════════════════════════════════════════════════════════════════════════════

def download_data(ticker: str, years: int) -> pd.DataFrame:
    """Descarga datos históricos OHLCV via yfinance."""
    end = datetime.today()
    start = end - timedelta(days=years * 365 + 30)
    print(f"📥  Descargando datos de {ticker} ({start.date()} → {end.date()}) …")
    df = yf.download(ticker, start=start.strftime("%Y-%m-%d"),
                     end=end.strftime("%Y-%m-%d"), auto_adjust=True, progress=False)
    if df.empty:
        raise ValueError(f"No se pudieron descargar datos para {ticker}.")
    df.dropna(inplace=True)
    print(f"    ✔  {len(df)} barras descargadas.\n")
    return df


def compute_indicators(df: pd.DataFrame, genome: dict) -> pd.DataFrame:
    """
    Calcula los indicadores del agente:
      - EMA rápida y lenta
      - RSI
    """
    data = df.copy()
    close = data["Close"].squeeze()

    fast = int(genome["fast_ma"])
    slow = int(genome["slow_ma"])
    if fast >= slow:
        fast = max(5, slow - 5)

    data["ema_fast"] = close.ewm(span=fast, adjust=False).mean()
    data["ema_slow"] = close.ewm(span=slow, adjust=False).mean()

    period = int(genome["rsi_period"])
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    data["rsi"] = 100 - (100 / (1 + rs))

    data.dropna(inplace=True)
    return data


# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO 2: GENOMA Y AGENTE
# ══════════════════════════════════════════════════════════════════════════════

class Genome:
    """Representa el ADN de un agente de trading."""

    def __init__(self, genes: Optional[dict] = None):
        self.genes = genes if genes is not None else self._random_genome()

    @staticmethod
    def _random_genome() -> dict:
        g = {}
        for key, (lo, hi) in GENOME_RANGES.items():
            g[key] = (random.randint(lo, hi)
                      if isinstance(lo, int) and isinstance(hi, int)
                      else random.uniform(lo, hi))
        if g["fast_ma"] >= g["slow_ma"]:
            g["fast_ma"] = max(5, g["slow_ma"] - 5)
        return g

    def mutate(self) -> 'Genome':
        new_genes = deepcopy(self.genes)
        for key, (lo, hi) in GENOME_RANGES.items():
            if random.random() < MUTATION_RATE:
                span = (hi - lo) * MUTATION_STRENGTH
                if isinstance(lo, int) and isinstance(hi, int):
                    delta = random.randint(-max(1, int(span)), max(1, int(span)))
                    new_genes[key] = int(np.clip(new_genes[key] + delta, lo, hi))
                else:
                    delta = random.gauss(0, span)
                    new_genes[key] = float(np.clip(new_genes[key] + delta, lo, hi))
        if new_genes["fast_ma"] >= new_genes["slow_ma"]:
            new_genes["fast_ma"] = max(5, new_genes["slow_ma"] - 5)
        return Genome(new_genes)

    @staticmethod
    def crossover(parent_a: 'Genome', parent_b: 'Genome') -> 'Genome':
        child_genes = {
            key: (parent_a.genes[key] if random.random() < 0.5 else parent_b.genes[key])
            for key in GENOME_RANGES
        }
        if child_genes["fast_ma"] >= child_genes["slow_ma"]:
            child_genes["fast_ma"] = max(5, child_genes["slow_ma"] - 5)
        return Genome(child_genes)

    def __repr__(self):
        return f"Genome({self.genes})"


# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO 3: SIMULACIÓN DE TRADING (FITNESS)
# ══════════════════════════════════════════════════════════════════════════════

def simulate_agent(df_raw: pd.DataFrame, genome: 'Genome') -> float:
    """
    Simula la estrategia de un agente sobre datos históricos.

    Reglas de trading (operativa LARGA únicamente):
    ─────────────────────────────────────────────────
    ENTRADA:
      EMA rápida cruza al alza la EMA lenta  AND  RSI < rsi_overbought
      (golden cross confirmado con RSI que no esté en sobrecompra)

    SALIDA (la primera condición que se cumpla):
      1. Price <= stop_loss   → cierre con pérdida limitada
      2. Price >= take_profit → cierre con beneficio
      3. RSI cae por debajo de rsi_oversold → señal de pérdida de momentum

    MUERTE:
      Portfolio total (cash + valor de la posición) < DEATH_THRESHOLD

    FITNESS: Sharpe Ratio anualizado aproximado.
    """
    genes = genome.genes
    data  = compute_indicators(df_raw, genes)
    if len(data) < 2:
        return 0.0

    cp       = data["Close"].squeeze().values
    ef       = data["ema_fast"].values
    es       = data["ema_slow"].values
    rsi_v    = data["rsi"].values

    capital  = INITIAL_CAPITAL
    position = 0.0
    sl_price = tp_price = 0.0
    sl_pct   = genes["stop_loss_pct"]
    tp_pct   = genes["take_profit_pct"]
    rsi_ob   = genes["rsi_overbought"]   # entrada: RSI < rsi_ob
    rsi_os   = genes["rsi_oversold"]     # salida:  RSI < rsi_os

    daily_ret   = []
    prev_port   = capital

    for i in range(1, len(cp)):
        price = float(cp[i])
        port  = capital + position * price

        # ── Muerte ──────────────────────────────────────────────────────
        if port < DEATH_THRESHOLD:
            return 0.0

        # ── Cierre de posición abierta ───────────────────────────────────
        if position > 0:
            exit_sl  = price <= sl_price
            exit_tp  = price >= tp_price
            exit_rsi = rsi_v[i] < rsi_os   # momentum perdido
            if exit_sl or exit_tp or exit_rsi:
                capital  += position * price * (1 - COMMISSION)
                position  = 0.0
                sl_price  = tp_price = 0.0

        # ── Apertura de posición (golden cross + RSI no sobrecomprado) ───
        if position == 0 and capital > 0:
            crossed_up = (ef[i - 1] < es[i - 1]) and (ef[i] >= es[i])
            if crossed_up and rsi_v[i] < rsi_ob:
                invest    = capital * INVEST_FRACTION
                position  = invest * (1 - COMMISSION) / price
                capital  -= invest
                sl_price  = price * (1 - sl_pct)
                tp_price  = price * (1 + tp_pct)

        # ── Retorno diario ───────────────────────────────────────────────
        port_now = capital + position * price
        daily_ret.append((port_now - prev_port) / (prev_port + 1e-9))
        prev_port = port_now

    # ── Cerrar posición al final ─────────────────────────────────────────
    if position > 0:
        capital += position * float(cp[-1]) * (1 - COMMISSION)

    if not daily_ret:
        return 0.0

    arr    = np.array(daily_ret)
    sharpe = (np.mean(arr) / (np.std(arr) + 1e-9)) * math.sqrt(252)

    # Penalizar si terminamos con menos que el capital inicial
    if capital < INITIAL_CAPITAL:
        sharpe *= max(0.0, capital / INITIAL_CAPITAL)

    return float(sharpe)


# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO 4: ALGORITMO GENÉTICO
# ══════════════════════════════════════════════════════════════════════════════

class GeneticAlgorithm:
    """Gestiona la evolución de la población de agentes."""

    def __init__(self, df: pd.DataFrame):
        self.df           = df
        self.population   = [Genome() for _ in range(POPULATION_SIZE)]
        self.best_genome: Optional[Genome] = None
        self.best_fitness = -np.inf
        self.history      = []

    def _evaluate(self):
        return [simulate_agent(self.df, g) for g in self.population]

    def _tournament(self, pop, fits) -> Genome:
        """Selección por torneo de tamaño 3."""
        candidates = random.choices(list(zip(pop, fits)), k=3)
        return max(candidates, key=lambda x: x[1])[0]

    def evolve(self):
        print("=" * 60)
        print("  🧬  INICIO DE LA EVOLUCIÓN")
        print(f"      Población: {POPULATION_SIZE} agentes | "
              f"Generaciones: {NUM_GENERATIONS}")
        print("=" * 60)

        for gen in range(1, NUM_GENERATIONS + 1):
            fits   = self._evaluate()
            valid  = [f for f in fits if f > 0]
            best_f = max(fits)
            avg_f  = float(np.mean(valid)) if valid else 0.0

            best_idx = int(np.argmax(fits))
            if best_f > self.best_fitness:
                self.best_fitness = best_f
                self.best_genome  = deepcopy(self.population[best_idx])

            self.history.append({
                "generation": gen, "best": best_f,
                "avg": avg_f, "survivors": len(valid),
            })

            bar = ("█" * int((gen / NUM_GENERATIONS) * 30)).ljust(30)
            print(f"  Gen {gen:>3}/{NUM_GENERATIONS}  [{bar}]  "
                  f"Best Sharpe: {best_f:+.4f}  "
                  f"Avg: {avg_f:+.4f}  "
                  f"Supervivientes: {len(valid)}/{POPULATION_SIZE}")

            if gen == NUM_GENERATIONS:
                break

            # Élite
            sorted_pairs = sorted(zip(fits, self.population),
                                  key=lambda x: x[0], reverse=True)
            n_elite  = max(1, int(ELITE_FRACTION * POPULATION_SIZE))
            elite    = [g for _, g in sorted_pairs[:n_elite]]

            # Crossover + mutación
            n_cross  = int(CROSSOVER_FRACTION * POPULATION_SIZE)
            children = [
                Genome.crossover(
                    self._tournament(self.population, fits),
                    self._tournament(self.population, fits)
                ).mutate()
                for _ in range(n_cross)
            ]

            # Relleno con nuevos genomas aleatorios
            n_rand  = POPULATION_SIZE - n_elite - n_cross
            randoms = [Genome() for _ in range(max(0, n_rand))]

            self.population = (elite + children + randoms)[:POPULATION_SIZE]

        print("\n  ✅  Evolución completada.\n")


# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO 5: GENERADOR DE SEÑALES EN TIEMPO REAL
# ══════════════════════════════════════════════════════════════════════════════

def get_signal(best_genome: 'Genome', ticker: str) -> dict:
    """
    Descarga los datos más recientes y emite una señal de trading
    usando los parámetros óptimos del mejor agente evolucionado.
    """
    genes    = best_genome.genes
    slow_ma  = int(genes["slow_ma"])
    lookback = slow_ma * 5 + 60
    end      = datetime.today()
    start    = end - timedelta(days=lookback)

    df_live = yf.download(ticker,
                          start=start.strftime("%Y-%m-%d"),
                          end=end.strftime("%Y-%m-%d"),
                          auto_adjust=True, progress=False)

    if df_live.empty or len(df_live) < 3:
        return {"signal": "ESPERAR", "reason": "Datos insuficientes"}

    data = compute_indicators(df_live, genes)
    if len(data) < 2:
        return {"signal": "ESPERAR", "reason": "Indicadores insuficientes"}

    ef  = data["ema_fast"].values
    es  = data["ema_slow"].values
    rsi = data["rsi"].values
    cp  = data["Close"].squeeze().values

    last_price = float(cp[-1])
    rsi_now    = float(rsi[-1])
    crossed_up = (ef[-2] < es[-2]) and (ef[-1] >= es[-1])
    crossed_dn = (ef[-2] > es[-2]) and (ef[-1] <= es[-1])

    sl_pct = genes["stop_loss_pct"]
    tp_pct = genes["take_profit_pct"]
    rsi_ob = genes["rsi_overbought"]
    rsi_os = genes["rsi_oversold"]

    if crossed_up and rsi_now < rsi_ob:
        signal = "COMPRAR"
        sl     = last_price * (1 - sl_pct)
        tp     = last_price * (1 + tp_pct)
    elif crossed_dn or rsi_now < rsi_os:
        signal = "VENDER / CERRAR"
        sl     = None
        tp     = None
    else:
        signal = "ESPERAR"
        sl     = None
        tp     = None

    return {
        "signal": signal, "last_price": last_price, "rsi": rsi_now,
        "ema_fast_last": float(ef[-1]), "ema_slow_last": float(es[-1]),
        "sl": sl, "tp": tp,
    }


# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO 6: REPORTE FINAL
# ══════════════════════════════════════════════════════════════════════════════

def print_report(ticker, best_genome, best_fitness, signal_data):
    genes = best_genome.genes
    sig   = signal_data["signal"]
    EMOJI = {"COMPRAR": "🟢", "VENDER / CERRAR": "🔴", "ESPERAR": "🟡"}
    emoji = EMOJI.get(sig, "⚪")
    sep   = "═" * 62

    print(f"\n{sep}")
    print("   📊  INFORME FINAL — AGENTE GENÉTICO DE TRADING")
    print(sep)
    print(f"\n  Activo analizado          : {ticker}")
    print(f"  Fecha de análisis         : {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("\n  ── Parámetros óptimos encontrados por la evolución ──────")
    print(f"  EMA Rápida (periodos)     : {int(genes['fast_ma'])}")
    print(f"  EMA Lenta  (periodos)     : {int(genes['slow_ma'])}")
    print(f"  RSI Periodo               : {int(genes['rsi_period'])}")
    print(f"  RSI Umbral sobrecompra    : {genes['rsi_overbought']:.1f}  ← NO entrar si RSI > este valor")
    print(f"  RSI Umbral salida         : {genes['rsi_oversold']:.1f}  ← Cerrar largo si RSI < este valor")
    print(f"  Stop Loss (%)             : {genes['stop_loss_pct'] * 100:.2f} %")
    print(f"  Take Profit (%)           : {genes['take_profit_pct'] * 100:.2f} %")
    print(f"  Fitness (Sharpe aprox.)   : {best_fitness:+.4f}")
    print("\n  ── Señal de mercado ─────────────────────────────────────")

    if sig == "COMPRAR":
        price = signal_data["last_price"]
        sl    = signal_data["sl"]
        tp    = signal_data["tp"]
        rr    = abs(tp - price) / (abs(sl - price) + 1e-9)
        print(f"  {emoji}  SEÑAL        : {sig}")
        print(f"  💵  Precio Entrada : ${price:>12,.2f}")
        print(f"  🛑  Stop Loss      : ${sl:>12,.2f}  "
              f"({abs(sl - price) / price * 100:.2f} % de riesgo)")
        print(f"  🎯  Take Profit    : ${tp:>12,.2f}  "
              f"({abs(tp - price) / price * 100:.2f} % de beneficio)")
        print(f"  ⚖️   Ratio R/R      : 1 : {rr:.2f}")
    else:
        print(f"  {emoji}  SEÑAL        : {sig}")
        print(f"  💵  Precio actual  : ${signal_data.get('last_price', 0):>12,.2f}")
        if sig == "VENDER / CERRAR":
            print("      Señal de cierre de posición larga / evitar entrada.")
        else:
            print("      No se cumplen las condiciones de entrada en este momento.")

    print(f"\n  RSI actual                : {signal_data.get('rsi', 0):.2f}")
    print(f"  EMA Rápida actual         : {signal_data.get('ema_fast_last', 0):,.2f}")
    print(f"  EMA Lenta actual          : {signal_data.get('ema_slow_last', 0):,.2f}")
    print(f"\n{sep}\n")
    print("  ⚠️   AVISO LEGAL: Este script es solo educativo y no constituye")
    print("      asesoramiento financiero. Opera siempre con capital que puedas")
    print("      permitirte perder.\n")
    print(sep)


# ══════════════════════════════════════════════════════════════════════════════
# PUNTO DE ENTRADA PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

def main():
    df_train = download_data(TICKER, TRAINING_YEARS)

    ga = GeneticAlgorithm(df_train)
    ga.evolve()

    if ga.best_genome is None:
        print("⚠️  No se encontró ningún agente con fitness > 0.")
        return

    print("📡  Analizando los datos más recientes del mercado …")
    signal_data = get_signal(ga.best_genome, TICKER)
    print_report(TICKER, ga.best_genome, ga.best_fitness, signal_data)


if __name__ == "__main__":
    main()
