"""
================================================================================
  SP500 PORTFOLIO GENETIC AGENT
  ─────────────────────────────
  Investigación genética diaria sobre reglas técnicas del S&P 500.
  60 agentes, 35 generaciones y ventanas dinámicas IS/OOS.
  Capital inicial ficticio: 100.000 USD.
  Diario prospectivo: señal al cierre, ejecución simulada en la siguiente apertura.

  Dependencias: pip install pandas numpy yfinance
================================================================================
"""

import random
import math
import warnings
import json
import os
import tempfile
from copy import deepcopy
from datetime import datetime, timedelta
import time
from typing import Optional, List
# Public runtime intentionally has no personal notification channel or secrets.
class TelegramNotifier:
    @staticmethod
    def send_message(text: str):
        return

import numpy as np
import pandas as pd
import yfinance as yf
from forward_portfolio import FILE_NAME, ensure_before_next_open, latest_completed_session, run as run_forward

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN GLOBAL
# ─────────────────────────────────────────────────────────────────────────────
INITIAL_CAPITAL   = 100_000.0    # Capital ficticio en USD
DEATH_THRESHOLD   = 50_000.0     # Pérdida >50% → agente muere (fitness = 0)
COMMISSION        = 0.001        # Comisión por operación (0.1 %)
INVEST_FRACTION   = 0.95         # Fracción del cash asignado que se invierte por trade

N_AGENTS          = 60          # Tamaño de la población
N_GENERATIONS     = 35           # Generaciones de evolución
MAX_WEIGHT_PER_TRADE = 0.15      # Tope máximo de capital asignado a una sola acción (15%)

# Cálculo dinámico del período de entrenamiento (1 año, terminando el lunes de la semana pasada)
today = datetime.now()
days_since_monday = today.weekday()  # Lunes = 0, Domingo = 6
# Retrocedemos al lunes de esta semana, y luego 7 días para el lunes de la semana anterior
days_to_last_monday = days_since_monday + 7
train_oos_end_dt = today - timedelta(days=days_to_last_monday)

# OOS abarca los últimos 6 meses (180 días) antes del end_dt
train_oos_start_dt = train_oos_end_dt - timedelta(days=180)

# IS abarca los 24 meses restantes (730 días) antes de OOS
train_is_end_dt = train_oos_start_dt - timedelta(days=1)
train_is_start_dt = train_oos_start_dt - timedelta(days=730)

# Convertimos a string para yfinance
TRAIN_IS_START    = train_is_start_dt.strftime("%Y-%m-%d")
TRAIN_IS_END      = train_is_end_dt.strftime("%Y-%m-%d")
TRAIN_OOS_START   = train_oos_start_dt.strftime("%Y-%m-%d")
TRAIN_OOS_END     = train_oos_end_dt.strftime("%Y-%m-%d")
EXECUTION_DATE    = today.strftime("%Y-%m-%d")


ELITE_FRACTION    = 0.10         # Top 10 % pasan a la siguiente generación
CROSSOVER_FRAC    = 0.60         # 60 % se crea por crossover
MUTATION_RATE     = 0.15         # Probabilidad de mutar cada gen
MUTATION_STR      = 0.25         # Fuerza de la mutación (fracción del rango)

# ─────────────────────────────────────────────────────────────────────────────
# DIRECTORIO DE REGISTROS
# ─────────────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HISTORICO_DIR = os.path.join(BASE_DIR, "registro_historico")
os.makedirs(HISTORICO_DIR, exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# POOL DE ACCIONES S&P 500
# ─────────────────────────────────────────────────────────────────────────────
def get_sp500_tickers() -> List[str]:
    """Obtiene la lista completa de tickers del S&P 500 desde un CSV o lo descarga usando CSV seguro."""
    csv_path = os.path.join(BASE_DIR, "sp500_tickers.csv")
    
    if os.path.exists(csv_path):
        print(f"  Leyendo lista de S&P 500 desde CSV local ({csv_path})...")
        try:
            df = pd.read_csv(csv_path)
            return df['Symbol'].tolist()
        except Exception:
            pass

    print("  Descargando listado S&P 500 desde CSV público y guardando en local...")
    try:
        # Usamos read_csv en un repositorio estable. NO usa 'lxml' para html.
        url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/master/data/constituents.csv"
        df = pd.read_csv(url)
        
        tickers = df['Symbol'].tolist()
        tickers = [str(t).replace('.', '-') for t in tickers]
        
        # Guardar localmente
        df['Symbol'] = tickers
        df.to_csv(csv_path, index=False)
        print(f"  ✅ Listado guardado localmente en: {csv_path}")
        
        return tickers
    except Exception as e:
        raise RuntimeError("No se pudo obtener la lista S&P 500; no se sustituye el universo en silencio") from e

# Obtenemos la lista global
SP500_POOL = get_sp500_tickers()
POOL_SIZE = len(SP500_POOL)

# Rangos de los genes técnicos
TECH_RANGES = {
    "fast_ma":         (5,    30),
    "slow_ma":         (20,  100),
    "rsi_period":      (7,    21),
    "rsi_overbought":  (60,   85),   # NO entrar si RSI > este valor
    "rsi_oversold":    (15,   40),   # Cerrar largo si RSI < este valor
    "stop_loss_pct":   (0.01, 0.08),
    "take_profit_pct": (0.02, 0.20),
}

# Fin configuración directorios


# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO 1: DESCARGA DE DATOS (una sola vez para todos los agentes)
# ══════════════════════════════════════════════════════════════════════════════

def download_all(tickers: List[str], start: str, end: str) -> dict:
    """
    Descarga datos OHLCV en lotes (chunks) para evitar bloqueos por Rate Limiting.
    Devuelve un dict { ticker: DataFrame } con solo los tickers con datos válidos.
    """
    import time
    print(f"📥  Descargando datos ({start} a {end}) para {len(tickers)} acciones (en lotes)...")
    
    result = {}
    chunk_size = 50
    
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i:i + chunk_size]
        try:
            raw = yf.download(
                chunk, start=start, end=end,
                auto_adjust=True, progress=False, group_by="ticker",
                threads=False,
            )
            
            # Procesar el bloque descargado
            for tkr in chunk:
                try:
                    if isinstance(raw.columns, pd.MultiIndex):
                        df = raw[tkr].dropna()
                    else:
                        df = raw.dropna()
                    if len(df) >= 30:
                        result[tkr] = df
                except Exception:
                    pass
                    
        except Exception as e:
            print(f"    ⚠️ Error descargando lote {i//chunk_size + 1}: {e}")
            
        # Pausa para no saturar la API
        if i + chunk_size < len(tickers):
            time.sleep(2)

    valid = list(result.keys())
    print(f"    ✔  {len(valid)} acciones con datos válidos.\n")

    return result


# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO 2: INDICADORES TÉCNICOS
# ══════════════════════════════════════════════════════════════════════════════

def compute_indicators(df: pd.DataFrame, genes: dict) -> Optional[pd.DataFrame]:
    """Añade EMA rápida, EMA lenta y RSI al DataFrame. Devuelve None si hay error."""
    try:
        data  = df.copy()
        close = data["Close"].squeeze()

        fast = int(genes["fast_ma"])
        slow = int(genes["slow_ma"])
        if fast >= slow:
            fast = max(5, slow - 5)

        data["ema_fast"] = close.ewm(span=fast, adjust=False).mean()
        data["ema_slow"] = close.ewm(span=slow, adjust=False).mean()

        p     = int(genes["rsi_period"])
        delta = close.diff()
        gain  = delta.clip(lower=0).ewm(alpha=1/p, adjust=False).mean()
        loss  = (-delta.clip(upper=0)).ewm(alpha=1/p, adjust=False).mean()
        rs    = gain / loss.replace(0, np.nan)
        data["rsi"] = 100 - (100 / (1 + rs))

        data.dropna(inplace=True)
        return data if len(data) >= 2 else None
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO 3: GENOMA
# ══════════════════════════════════════════════════════════════════════════════

class Genome:
    """
    ADN de un agente de portfolio Dinámico:
      · genes técnicos: EMA rápida, lenta, RSI, SL y TP.
    Ya no elige "qué acciones operar estáticamente", sino que todos sus genes 
    se aplican al screener global cada día sobre las 500 empresas.
    """

    def __init__(self, tech_genes: Optional[dict] = None):
        if tech_genes is None:
            self.tech = self._random()
        else:
            self.tech = tech_genes

    # ── Inicialización aleatoria ───────────────────────────────────────────
    @staticmethod
    def _random():
        tech = {}
        for key, (lo, hi) in TECH_RANGES.items():
            tech[key] = (random.randint(lo, hi)
                         if isinstance(lo, int) and isinstance(hi, int)
                         else random.uniform(lo, hi))
        if tech["fast_ma"] >= tech["slow_ma"]:
            tech["fast_ma"] = max(5, tech["slow_ma"] - 5)
        return tech

    # ── Mutación ───────────────────────────────────────────────────────────
    def mutate(self) -> 'Genome':
        new_tech = deepcopy(self.tech)

        # Mutar genes técnicos
        for key, (lo, hi) in TECH_RANGES.items():
            if random.random() < MUTATION_RATE:
                span = (hi - lo) * MUTATION_STR
                if isinstance(lo, int) and isinstance(hi, int):
                    delta = random.randint(-max(1, int(span)), max(1, int(span)))
                    new_tech[key] = int(np.clip(new_tech[key] + delta, lo, hi))
                else:
                    new_tech[key] = float(np.clip(
                        new_tech[key] + random.gauss(0, span), lo, hi))
        if new_tech["fast_ma"] >= new_tech["slow_ma"]:
            new_tech["fast_ma"] = max(5, new_tech["slow_ma"] - 5)

        return Genome(new_tech)

    # ── Crossover ──────────────────────────────────────────────────────────
    @staticmethod
    def crossover(pa: 'Genome', pb: 'Genome') -> 'Genome':
        # Genes técnicos: crossover uniforme
        new_tech = {}
        for key in TECH_RANGES:
            new_tech[key] = (pa.tech[key] if random.random() < 0.5 else pb.tech[key])
        if new_tech["fast_ma"] >= new_tech["slow_ma"]:
            new_tech["fast_ma"] = max(5, new_tech["slow_ma"] - 5)

        return Genome(new_tech)

    def __repr__(self):
        return f"Genome(tech={self.tech})"


# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO 4: SIMULACIÓN DEL PORTFOLIO (FITNESS)
# ══════════════════════════════════════════════════════════════════════════════

def simulate_portfolio(genome: Genome, data_cache: dict) -> tuple:
    """
    Simula dinámicamente un screener sobre todo el S&P 500 durante 2025.
    Itera día por día:
      1. Vende posiciones que tocan SL, TP o pierden momentum de RSI.
      2. Escanea cruces dorados en todos los tickers no poseídos.
      3. Compra los que mayor fuerza tengan (hasta consumir el cash, max 15% de peso).
    """
    genes   = genome.tech
    sl_pct  = genes["stop_loss_pct"]
    tp_pct  = genes["take_profit_pct"]
    rsi_ob  = genes["rsi_overbought"]
    rsi_os  = genes["rsi_oversold"]

    # 1. Precomputar indicadores vectorizados para acciones y alinear fechas
    all_data = {}
    valid_dates_set = set()
    for tkr, df_raw in data_cache.items():
        if len(df_raw) < 10: continue
        data = compute_indicators(df_raw, genes)
        if data is not None and not data.empty:
            all_data[tkr] = data
            valid_dates_set.update(data.index.strftime("%Y-%m-%d"))

    if not all_data:
        return 0.0, INITIAL_CAPITAL, {}, []

    all_dates = sorted(list(valid_dates_set))
    
    cash = INITIAL_CAPITAL
    positions = {} # tkr -> {shares, entry_price, sl_price, tp_price}
    history_trades = []
    
    peak_val = INITIAL_CAPITAL
    max_dd_pct = 0.0

    # Arrays preextraídos para velocidad en O(1)
    tkr_states = {tkr: {
        "dates": all_data[tkr].index.strftime("%Y-%m-%d").values,
        "prices": all_data[tkr]["Close"].values,
        "open_prices": all_data[tkr]["Open"].values,
        "ema_fast": all_data[tkr]["ema_fast"].values,
        "ema_slow": all_data[tkr]["ema_slow"].values,
        "rsi": all_data[tkr]["rsi"].values,
        "current_idx": 0
    } for tkr in all_data}
    
    # Órdenes pendientes del día anterior (T) para ejecutar en la apertura de hoy (T+1)
    pending_buys = []
    pending_sells = []

    # Bucle día a día (Simulación Dinámica de Screener)
    for current_date in all_dates:
        # Recuperar precios activos de hoy (Open y Close)
        active_close = {}
        active_open = {}
        for tkr, state in tkr_states.items():
            idx = state["current_idx"]
            if idx < len(state["dates"]) and state["dates"][idx] == current_date:
                active_close[tkr] = state["prices"][idx]
                active_open[tkr] = state["open_prices"][idx]
            elif idx < len(state["dates"]) and state["dates"][idx] < current_date:
                # Catch up si falta una fecha en el dataset
                while idx < len(state["dates"]) and state["dates"][idx] < current_date:
                    idx += 1
                state["current_idx"] = idx
                if idx < len(state["dates"]) and state["dates"][idx] == current_date:
                    active_close[tkr] = state["prices"][idx]
                    active_open[tkr] = state["open_prices"][idx]

        # ----------------------------------------------------------------------
        # FASE 1: EJECUCIÓN (T+1) en la Apertura (OPEN)
        # ----------------------------------------------------------------------
        
        # A) Ejecutar VENDAS pendientes de T
        for order in pending_sells:
            tkr = order["ticker"]
            if tkr in positions and tkr in active_open:
                exec_price = active_open[tkr]
                pos = positions[tkr]
                amount = pos["shares"] * exec_price * (1 - COMMISSION)
                cash += amount
                history_trades.append({
                    "date": current_date, "ticker": tkr, "action": "VENDER",
                    "price": exec_price, "shares": pos["shares"], "reason": order["reason"]
                })
                del positions[tkr]
        pending_sells.clear()

        # Recalcular valor total antes de comprar con el cash liberado
        val_pos = sum(p["shares"] * active_open.get(t, p["entry_price"]) for t, p in positions.items())
        total_val = cash + val_pos

        # B) Ejecutar COMPRAS pendientes de T
        if pending_buys and cash > 0:
            pending_buys.sort(key=lambda x: x["momentum"], reverse=True)
            target_alloc = total_val * MAX_WEIGHT_PER_TRADE
            
            for candidate in pending_buys:
                tkr = candidate["ticker"]
                if tkr not in active_open: continue
                exec_price = active_open[tkr]
                
                invest = min(target_alloc, cash * INVEST_FRACTION)
                if invest > 100:
                    shares = invest * (1 - COMMISSION) / exec_price
                    cash -= invest
                    
                    # Los stops se fijan sobre el precio real de ejecución
                    sl_price = exec_price * (1 - sl_pct)
                    tp_price = exec_price * (1 + tp_pct)
                    
                    positions[tkr] = {
                        "shares": shares,
                        "entry_price": exec_price,
                        "sl_price": sl_price,
                        "tp_price": tp_price
                    }
                    history_trades.append({
                        "date": current_date, "ticker": tkr, "action": "COMPRAR",
                        "price": exec_price, "shares": shares, "reason": "Golden Cross",
                        "sl": sl_price, "tp": tp_price
                    })
        pending_buys.clear()

        # Recalcular el mark-to-market a Close para rastrear Drawdown y stops "mentales"
        val_pos = sum(p["shares"] * active_close.get(t, p["entry_price"]) for t, p in positions.items())
        total_val = cash + val_pos

        # ----------------------------------------------------------------------
        # FASE 2: DETECCIÓN (T) al Cierre (CLOSE)
        # ----------------------------------------------------------------------
        
        # C) Generar órdenes de VENTA para T+1 (Cortes a cierre)
        for tkr, pos in positions.items():
            if tkr not in active_close: continue
            price = active_close[tkr]
            idx = tkr_states[tkr]["current_idx"]
            rv = tkr_states[tkr]["rsi"][idx]

            if price <= pos["sl_price"] or price >= pos["tp_price"] or rv < rsi_os:
                reason = "SL" if price <= pos["sl_price"] else ("TP" if price >= pos["tp_price"] else "Momentum")
                # Se programa para vender mañana en Open
                pending_sells.append({"ticker": tkr, "reason": reason})

        # D) Generar órdenes de COMPRA para T+1 (Cruces a cierre)
        for tkr, state in tkr_states.items():
            if tkr in positions: continue
            
            # Tampoco agendamos compra de algo que ya va a comprarse mañana
            if any(pb["ticker"] == tkr for pb in pending_buys): continue
            
            idx = state["current_idx"]
            if idx == 0 or idx >= len(state["dates"]) or state["dates"][idx] != current_date:
                continue

            ef_prev = state["ema_fast"][idx - 1]
            es_prev = state["ema_slow"][idx - 1]
            ef_curr = state["ema_fast"][idx]
            es_curr = state["ema_slow"][idx]
            rv_curr = state["rsi"][idx]

            crossed_up = (ef_prev < es_prev) and (ef_curr >= es_curr)
            if crossed_up and rv_curr < rsi_ob:
                pending_buys.append({
                    "ticker": tkr,
                    "momentum": ef_curr - es_curr
                })

        # Avanzar el puntero index
        for tkr, state in tkr_states.items():
            if state["current_idx"] < len(state["dates"]) and state["dates"][state["current_idx"]] == current_date:
                state["current_idx"] += 1
                
        # D) TRACKEAR MÁXIMO DRAWDOWN
        if total_val > peak_val:
            peak_val = total_val
        elif peak_val > 0:
            dd_pct = (peak_val - total_val) / peak_val
            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct

    # Cierre final (vender todas las posesiones vivas al final del periodo de train para forzar materialización simple)
    final_date = all_dates[-1] if all_dates else TRAIN_IS_END
    for tkr, pos in positions.items():
        state = tkr_states[tkr]
        last_price = state["prices"][-1] if len(state["prices"]) > 0 else pos["entry_price"]
        amount = pos["shares"] * last_price * (1 - COMMISSION)
        cash += amount
        history_trades.append({
            "date": final_date, "ticker": tkr, "action": "VENDER",
            "price": last_price, "shares": pos["shares"], "reason": "Fin Competición"
        })
    positions.clear()

    if cash < DEATH_THRESHOLD:
        return 0.0, cash, max_dd_pct, history_trades

    total_return_pct = (cash - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
    
    if total_return_pct <= 0:
        fitness = 0.0
    else:
        # Fitness penalizado por el Drawdown (Modified Calmar Ratio relajado)
        fitness = total_return_pct / ((max_dd_pct * 15.0) + 1.0)
    
    return fitness, cash, max_dd_pct, history_trades


# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO 5: ALGORITMO GENÉTICO
# ══════════════════════════════════════════════════════════════════════════════

class GeneticAlgorithm:
    """100 agentes evolucionan durante 20 generaciones (IS). El Top 10 se valida (OOS)."""

    def __init__(self, data_cache_is: dict, data_cache_oos: dict):
        self.cache_is    = data_cache_is
        self.cache_oos   = data_cache_oos
        self.population  = [Genome() for _ in range(N_AGENTS)]
        
        # Guardará el mejor absoluto tras pasar el test OOS
        self.best_genome: Optional[Genome]   = None
        self.best_fitness: float             = -np.inf
        self.best_mdd:     float             = 0.0
        self.best_final:   float             = 0.0
        self.best_trades:  list              = []
        self.history                         = []

    # ── Evaluación de toda la población ───────────────────────────────────
    def _evaluate(self, population, cache):
        results = []
        for g in population:
            fit, final, mdd, tr = simulate_portfolio(g, cache)
            results.append((fit, final, mdd, tr))
        return results

    # ── Selección por torneo de tamaño 3 ──────────────────────────────────
    def _tournament(self, pop, fits):
        candidates = random.choices(list(zip(pop, fits)), k=3)
        return max(candidates, key=lambda x: x[1])[0]

    # ── Ciclo evolutivo ────────────────────────────────────────────────────
    def evolve(self):
        print("=" * 66)
        print("  🧬  COMPETICIÓN — ALGORITMO GENÉTICO DE PORTFOLIOS S&P 500")
        print(f"      {N_AGENTS} agentes  ·  {N_GENERATIONS} generaciones")
        print(f"      Capital por agente: ${INITIAL_CAPITAL:,.0f}")
        print(f"      Entrenamiento (IS) : {TRAIN_IS_START} → {TRAIN_IS_END}")
        print(f"      Validación (OOS)   : {TRAIN_OOS_START} → {TRAIN_OOS_END}")
        print("=" * 66)

        # 1. Fase de Entrenamiento (In-Sample)
        for gen in range(1, N_GENERATIONS + 1):
            if gen == 1:
                start_gen_time = time.time()
                
            results = self._evaluate(self.population, self.cache_is)
            fits    = [r[0] for r in results]
            
            survivors = [f for f in fits if f > 0]
            best_f    = max(fits)
            avg_f     = float(np.mean(survivors)) if survivors else 0.0

            self.history.append({
                "gen": gen, "best": best_f, "avg": avg_f,
                "survivors": len(survivors),
            })

            bar = ("█" * int((gen / N_GENERATIONS) * 34)).ljust(34)
            print(f"  Gen {gen:>3}/{N_GENERATIONS}  [{bar}]  "
                  f"Best (IS): {best_f:.4f}  "
                  f"Avg (IS): {avg_f:.4f}  "
                  f"Vivos: {len(survivors)}/{N_AGENTS}")

            if gen == 1:
                elapsed_gen = time.time() - start_gen_time
                remaining_gens = N_GENERATIONS - 1
                estimated_sec = elapsed_gen * remaining_gens
                est_min = max(1, int(estimated_sec // 60))
                TelegramNotifier.send_message(f"⏱️ Entrenamiento en curso. Tiempo estimado restante: {est_min} minutos.")

            if gen == N_GENERATIONS:
                break

            # ── Élite ──────────────────────────────────────────────────
            sorted_pairs = sorted(
                zip(fits, self.population), key=lambda x: x[0], reverse=True)
            n_elite = max(1, int(ELITE_FRACTION * N_AGENTS))
            elite   = [g for _, g in sorted_pairs[:n_elite]]

            # ── Crossover + mutación ───────────────────────────────────
            n_cross  = int(CROSSOVER_FRAC * N_AGENTS)
            children = [
                Genome.crossover(
                    self._tournament(self.population, fits),
                    self._tournament(self.population, fits),
                ).mutate()
                for _ in range(n_cross)
            ]

            # ── Nuevos agentes aleatorios ──────────────────────────────
            n_rand  = N_AGENTS - n_elite - n_cross
            randoms = [Genome() for _ in range(max(0, n_rand))]

            self.population = (elite + children + randoms)[:N_AGENTS]

        print("\n  ✅  Entrenamiento In-Sample completado.")
        
        # 2. Fase de Validación Estricta (Out-of-Sample)
        print("  🕵️   Iniciando fase de validación cruzada (Out-of-Sample) del Top-10...")
        
        # Sacar el Top 10 del IS actual
        final_results = self._evaluate(self.population, self.cache_is)
        fits_is = [r[0] for r in final_results]
        sorted_final = sorted(zip(fits_is, self.population), key=lambda x: x[0], reverse=True)
        top_10_pop = [g for _, g in sorted_final[:10]]
        
        # Evaluar el Top 10 puramente en OOS
        oos_results = self._evaluate(top_10_pop, self.cache_oos)
        
        for idx, (fit_oos, final_oos, mdd_oos, tr_oos) in enumerate(oos_results):
            if fit_oos > self.best_fitness:
                self.best_fitness = fit_oos
                self.best_final   = final_oos
                self.best_mdd     = mdd_oos
                self.best_trades  = deepcopy(tr_oos)
                self.best_genome  = deepcopy(top_10_pop[idx])

        if self.best_fitness > 0:
            print("  🏆  ¡Se ha encontrado un Campeón Absoluto de Validación OOS!")
        else:
            print("  💀  Catástrofe Estructural: Ningún agente del Top 10 sobrevivió al OOS.")
            print("      (Esto indica overfitting masivo en los peores meses del mercado).")


# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO 6: REPORTE DEL GANADOR
# ══════════════════════════════════════════════════════════════════════════════

def print_winner_summary(best_fitness: float, best_val: float, best_mdd: float, best_genome: Genome, trades: list = None):
    print(f"\n{'═'*66}")
    print(f"  🏆  GANADOR ABSOLUTO OOS S&P 500  ·  {TRAIN_OOS_START} a {TRAIN_OOS_END}")
    print(f"{'═'*66}\n")
    print(f"  Puntuación fitness        : {best_fitness:+.2f} (no es retorno ni Calmar)")
    print(f"  Maximum Drawdown (MDD)    : -{best_mdd * 100:.2f} %")
    print(f"  Capital inicial           : ${INITIAL_CAPITAL:12,.2f}")
    print(f"  Capital final             : ${best_val:12,.2f}")
    print(f"  Beneficio neto            : ${best_val - INITIAL_CAPITAL:+12,.2f}")
    
    if trades:
        total_trades = len([t for t in trades if t["action"] == "COMPRAR"])
        winning_sells = len([t for t in trades if t["action"] == "VENDER" and t["reason"] == "TP"])
        losing_sells = len([t for t in trades if t["action"] == "VENDER" and t["reason"] in ["SL", "Momentum"]])
        print(f"  Operaciones realizadas    : {total_trades}")
        print(f"  Take Profits detonados    : {winning_sells}")
        print(f"  Cortes de pérdida (SL/Mom): {losing_sells}")

    print("\n  ── Parámetros técnicos evolutivos ───────────────────────")
    print(f"  EMA Rápida                : {best_genome.tech['fast_ma']} periodos")
    print(f"  EMA Lenta                 : {best_genome.tech['slow_ma']} periodos")
    print(f"  RSI Periodo               : {best_genome.tech['rsi_period']}")
    print(f"  RSI Umbral entrada        : < {best_genome.tech['rsi_overbought']:.1f}")
    print(f"  RSI Umbral salida         : < {best_genome.tech['rsi_oversold']:.1f}")
    print(f"  Stop Loss                 : {best_genome.tech['stop_loss_pct']*100:.2f} %")
    print(f"  Take Profit               : {best_genome.tech['take_profit_pct']*100:.2f} %")
    
    if trades:
        trades_path = os.path.join(HISTORICO_DIR, f"ganador_competicion_{EXECUTION_DATE}.csv")
        df_trades = pd.DataFrame(trades)
        df_trades.to_csv(trades_path, index=False)
        print(f"\n  📝 Historial estricto de trades ({TRAIN_OOS_START} a {TRAIN_OOS_END}) guardado en: {trades_path}\n")

    print(f"\n{'═'*66}\n")
    print("  ⚠️   AVISO LEGAL: Este script es solo educativo y no constituye")
    print("      asesoramiento financiero. Opera siempre con capital que puedas")
    print("      permitirte perder.\n")
    print('═'*66)


def plot_winner_trades(trades: list, cache: dict, genome: Genome):
    """Genera gráficas vectoriales (.svg) para cada acción operada por el ganador."""
    if not trades:
        return
        
    graficas_dir = os.path.join(HISTORICO_DIR, f"graficas_competicion_{EXECUTION_DATE}")
    os.makedirs(graficas_dir, exist_ok=True)
    
    unique_tickers = len(set(t["ticker"] for t in trades))
    print(f"\n  📊 Generando {unique_tickers} gráficas vectoriales (.svg) de operaciones en:")
    print(f"     {graficas_dir}")

    genes = genome.tech
    fast_ma = int(genes["fast_ma"])
    slow_ma = int(genes["slow_ma"])
    
    # Agrupar trades por ticker
    trades_by_ticker = {}
    for t in trades:
        tkr = t["ticker"]
        if tkr not in trades_by_ticker:
            trades_by_ticker[tkr] = []
        trades_by_ticker[tkr].append(t)
        
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    
    # Configurar estilo visual limpio
    plt.style.use('seaborn-v0_8-darkgrid')
    
    for tkr, t_list in trades_by_ticker.items():
        if tkr not in cache:
            continue
            
        df_raw = cache[tkr]
        # Calcular los mismos indicadores para la visualización
        data = compute_indicators(df_raw, genes)
        if data is None or data.empty:
            continue
            
        # Filtrar fechas al rango OOS para la gráfica final
        data = data[(data.index >= TRAIN_OOS_START) & (data.index <= TRAIN_OOS_END)]
        if data.empty:
            continue
            
        fig, ax = plt.subplots(figsize=(14, 7))
        
        # Plotear precio y medias
        ax.plot(data.index, data["Close"], label=f"Precio (Close) {tkr}", color='#2c3e50', linewidth=1.5)
        ax.plot(data.index, data["ema_fast"], label=f"EMA Rápida ({fast_ma})", color='#2980b9', linestyle='--', alpha=0.8)
        ax.plot(data.index, data["ema_slow"], label=f"EMA Lenta ({slow_ma})", color='#e67e22', linestyle='--', alpha=0.8)
        
        # Extraer fechas y precios de los trades
        buy_dates, buy_prices = [], []
        sell_dates, sell_prices = [], []
        
        for t in t_list:
            t_date = pd.to_datetime(t["date"])
            if t["action"] == "COMPRAR":
                buy_dates.append(t_date)
                buy_prices.append(t["price"])
            elif t["action"] == "VENDER":
                sell_dates.append(t_date)
                sell_prices.append(t["price"])
                
        # Scatter para compras y ventas
        if buy_dates:
            ax.scatter(buy_dates, buy_prices, marker='^', color='#27ae60', s=150, zorder=5, label='Compra')
        if sell_dates:
            ax.scatter(sell_dates, sell_prices, marker='v', color='#c0392b', s=150, zorder=5, label='Venta')
            
        ax.set_title(f"Operaciones de {tkr} - Validación ({TRAIN_OOS_START} a {TRAIN_OOS_END})", fontsize=14, fontweight='bold')
        ax.set_ylabel("Precio (USD)", fontsize=12)
        ax.legend(loc='upper left', fontsize=10)
        ax.grid(True, linestyle=':', alpha=0.6)
        
        # Formato de fechas
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
        plt.tight_layout()
        
        # Guardar en SVG
        file_path = os.path.join(graficas_dir, f"{tkr}_trades.svg")
        fig.savefig(file_path, format="svg", bbox_inches='tight')
        plt.close(fig)
        
    print("  ✅ Gráficas completadas.")


# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO 7: SEÑALES EN VIVO (hoy)
# ══════════════════════════════════════════════════════════════════════════════

def generate_live_signals(best_genome: Genome, end_date: str = None, signal_session: str = None) -> tuple:
    """
    Escanea en tiempo real todo el S&P 500 con los genes del ganador.
    Genera órdenes pendientes desde una sesión completada; nunca las ejecuta a ese cierre.
    """
    print("📡  Escaneando S&P 500 completo con algoritmos del ganador …")
    
    hoy = datetime.now() if end_date is None else pd.to_datetime(end_date)
    hace_meses = (hoy - pd.Timedelta(days=180)).strftime("%Y-%m-%d")
    hoy_str    = hoy.strftime("%Y-%m-%d")

    current_data = download_all(SP500_POOL, start=hace_meses, end=hoy_str)
    genes = best_genome.tech
    
    buy_list = []
    sell_list = []
    wait_list = []
    
    # Capital máximo para comprar es un peso estricto del 15% 
    wt = MAX_WEIGHT_PER_TRADE
    
    # Límite de desliste: Si la última vela guardada es más vieja que 7 días, ignorar la acción
    limit_date = pd.to_datetime(hoy_str) - pd.Timedelta(days=7)

    for tkr, df_raw in current_data.items():
        if len(df_raw) < 10: continue
        
        last_date = df_raw.index[-1]
        if last_date < limit_date or (signal_session and last_date.strftime("%Y-%m-%d") != signal_session):
            continue
            
        data = compute_indicators(df_raw, genes)
        if data is None or len(data) < 2: continue

        cp = float(data["Close"].iloc[-1])
        ef_prev = data["ema_fast"].iloc[-2]
        es_prev = data["ema_slow"].iloc[-2]
        ef_curr = data["ema_fast"].iloc[-1]
        es_curr = data["ema_slow"].iloc[-1]
        rv      = data["rsi"].iloc[-1]

        sl_p = cp * (1 - genes["stop_loss_pct"])
        tp_p = cp * (1 + genes["take_profit_pct"])

        crossed_up = (ef_prev < es_prev) and (ef_curr >= es_curr)
        crossed_dn = (ef_prev > es_prev) and (ef_curr <= es_curr)

        if crossed_up and rv < genes["rsi_overbought"]:
            buy_list.append((tkr, wt, cp, rv, sl_p, tp_p, "🟢 COMPRAR"))
        elif crossed_dn or rv < genes["rsi_oversold"]:
            sell_list.append((tkr, wt, cp, rv, sl_p, tp_p, "🔴 VENDER"))
        else:
            trend = "📈" if ef_curr > es_curr else "📉"
            wait_list.append((tkr, wt, cp, rv, sl_p, tp_p, f"🟡 ESPERAR {trend}"))

    # Mostrar las señales accionables
    print(f"\n{ '═'*72 }")
    print(f"  📊  SEÑALES EN VIVO GLOBALES S&P 500  ·  {hoy_str}")
    print(f"  Estrategia maestra (EMA {genes['fast_ma']}/{genes['slow_ma']}, RSI({genes['rsi_period']})  SL {genes['stop_loss_pct']*100:.1f}%  TP {genes['take_profit_pct']*100:.1f}%)")
    print(f"{ '═'*72 }")
    print("    #  Ticker      Precio     RSI  Señal                 SL          TP")
    print("  ───  ────────  ──────────  ──────  ────────────  ──────────  ──────────")

    active_signals = buy_list + sell_list
    if not active_signals:
        active_signals = wait_list[:10]  # Muestra 10 de ejemplo si no hay activas
        
    for i, (tkr, wt, cp, rv, sl_p, tp_p, sig) in enumerate(active_signals, 1):
        print(f"  {i:>3}. {tkr:<8} $ {cp:8.2f}  {rv:5.1f}  {sig:<12}  $ {sl_p:8.2f}  $ {tp_p:8.2f}")
    
    return buy_list, sell_list, wait_list


# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO 8: DIARIO DE TRADING PERSISTENTE
# ══════════════════════════════════════════════════════════════════════════════

class PortfolioTracker:
    def __init__(self, journal_filename="diario_portfolio.json", allow_new=False):
        self.path = os.path.join(HISTORICO_DIR, journal_filename)
        self.csv_path = os.path.join(HISTORICO_DIR, "registro_operaciones_reales.csv")
        self.allow_new = allow_new
        self.state = {
            "initial_capital": INITIAL_CAPITAL,
            "cash": INITIAL_CAPITAL,
            "positions": {},
            "history": [],
            "equity_history": {}
        }
        self.load()

    def load(self):
        if not os.path.exists(self.path):
            if not self.allow_new:
                raise FileNotFoundError(f"Diario ausente; no se reinicia: {self.path}")
        else:
            with open(self.path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if (not isinstance(loaded, dict) or
                    not isinstance(loaded.get("positions"), dict) or
                    not isinstance(loaded.get("history"), list) or
                    not isinstance(loaded.get("equity_history"), dict) or
                    not isinstance(loaded.get("cash"), (int, float)) or
                    not math.isfinite(loaded["cash"]) or
                    loaded.get("initial_capital") != INITIAL_CAPITAL):
                raise ValueError(f"Diario inválido; no se reinicia: {self.path}")
            self.state = loaded
                
        # Estructura retrocompatible
        if "equity_history" not in self.state:
            self.state["equity_history"] = {}

    def save(self):
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=HISTORICO_DIR,
                                             prefix=".diario-", suffix=".tmp", delete=False) as f:
                temporary_path = f.name
                json.dump(self.state, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporary_path, self.path)
        finally:
            if temporary_path and os.path.exists(temporary_path):
                os.unlink(temporary_path)

    def get_performance_metrics(self, current_val_tot: float) -> dict:
        hoy = datetime.now()
        hist = self.state.get("equity_history", {})
        
        # Acumulado
        cum = ((current_val_tot / INITIAL_CAPITAL) - 1.0) * 100.0
        
        # YTD
        ytd_val = INITIAL_CAPITAL
        years = sorted([d for d in hist.keys() if d.startswith(str(hoy.year - 1))])
        if years:
            ytd_val = hist[years[-1]]
        else:
            this_year = sorted([d for d in hist.keys() if d.startswith(str(hoy.year))])
            if this_year:
                ytd_val = hist[this_year[0]]
        ytd = ((current_val_tot / ytd_val) - 1.0) * 100.0 if ytd_val else 0.0

        # Mes
        mtd_val = current_val_tot
        prev_month = (hoy.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
        this_month = hoy.strftime("%Y-%m")
        prev_months_keys = sorted([d for d in hist.keys() if d.startswith(prev_month)])
        this_months_keys = sorted([d for d in hist.keys() if d.startswith(this_month)])
        
        if prev_months_keys:
            mtd_val = hist[prev_months_keys[-1]]
        elif this_months_keys:
            mtd_val = hist[this_months_keys[0]]
            
        mtd = ((current_val_tot / mtd_val) - 1.0) * 100.0 if mtd_val else 0.0
        
        return {"val_tot": current_val_tot, "cum": cum, "ytd": ytd, "mtd": mtd}

    def process_today(self, buy_list, sell_list, wait_list, genome: Genome):
        today_str = datetime.now().strftime("%Y-%m-%d")
        executed = []
        trades_this_run = []
        
        sep = "═" * 72
        print(f"\n{sep}")
        print(f"  📒  DIARIO DE PORTFOLIO  ·  {today_str}")
        print(sep)

        # 1. AUTO-CIERRE SL/TP sobre posiciones actuales (usando precios de hoy que vienen en las listas)
        # Combinamos todo para tener los precios actuales
        all_signals = buy_list + sell_list + wait_list
        price_map = {t[0]: t[2] for t in all_signals if t[2] is not None}
        missing = [tkr for tkr in self.state["positions"]
                   if tkr not in price_map or not isinstance(price_map[tkr], (int, float, np.floating))
                   or not math.isfinite(price_map[tkr]) or price_map[tkr] <= 0]
        if missing:
            raise RuntimeError(f"Cartera sin cotización válida para {', '.join(sorted(missing))}; diario sin actualizar")
        
        to_remove = []
        for tkr, pos in self.state["positions"].items():
            price = price_map.get(tkr)
            if price:
                if price <= pos["sl"] or price >= pos["tp"]:
                    reason = "Stop Loss" if price <= pos["sl"] else "Take Profit"
                    shares = pos["shares"]
                    amount = shares * price * (1 - COMMISSION)
                    self.state["cash"] += amount
                    executed.append(f"🔴 VENDER {tkr} ({reason}) · {shares:.2f} acc × ${price:,.2f} = ${amount:,.2f}")
                    trade_info = {
                        "date": today_str, "action": "VENDER", "ticker": tkr, 
                        "price": price, "shares": shares, "reason": reason
                    }
                    self.state["history"].append(trade_info)
                    trades_this_run.append(trade_info)
                    to_remove.append(tkr)
            else:
                executed.append(f"⚠️ ATENCIÓN: La acción en cartera {tkr} no tiene datos de mercado recientes. Revísala manualmente (posible desliste o ticker inactivo).")
                    
        for tkr in to_remove:
            del self.state["positions"][tkr]

        # 2. SEÑALES VENDER (manuales por tech / momentum)
        sell_tickers = [s[0] for s in sell_list]
        for tkr, wt, price, rsi_v, sl_p, tp_p, sig in sell_list:
            if price and tkr in self.state["positions"]:
                pos = self.state["positions"][tkr]
                shares = pos["shares"]
                amount = shares * price * (1 - COMMISSION)
                self.state["cash"] += amount
                executed.append(f"🔴 VENDER {tkr} (Señal) · {shares:.2f} acc × ${price:,.2f} = ${amount:,.2f}")
                trade_info = {
                    "date": today_str, "action": "VENDER", "ticker": tkr, 
                    "price": price, "shares": shares, "reason": "Signal"
                }
                self.state["history"].append(trade_info)
                trades_this_run.append(trade_info)
                del self.state["positions"][tkr]

        # Resumen Portfolio Final (para saber cuánto vale el portfolio ahorita y usarlo en compras dinámicas)
        val_pos = sum(p["shares"] * price_map[t] for t, p in self.state["positions"].items())
        val_tot = self.state["cash"] + val_pos
        pct_tot = (val_tot - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100

        # 3. SEÑALES COMPRAR
        for tkr, wt, price, rsi_v, sl_p, tp_p, sig in buy_list:
            if price and tkr not in self.state["positions"]:
                # Check if we already sold or bought it today to prevent duplicate executions across runs
                if any(h["ticker"] == tkr and h["date"] == today_str for h in self.state["history"]):
                    continue
                
                # Max 15% del valor total actual del portfolio (wt está capado a 0.15 en Genome)
                target_alloc = val_tot * wt
                cash_avail = self.state["cash"] * INVEST_FRACTION
                invest = min(target_alloc, cash_avail)
                if invest > 100:  # Mínimo para invertir
                    shares = invest * (1 - COMMISSION) / price
                    self.state["cash"] -= invest
                    self.state["positions"][tkr] = {
                        "shares": shares,
                        "avg_price": price,
                        "weight": wt,
                        "sl": sl_p,
                        "tp": tp_p
                    }
                    executed.append(f"🟢 COMPRAR {tkr} · {shares:.2f} acc × ${price:,.2f} = ${invest:,.2f} (SL: ${sl_p:.2f} TP: ${tp_p:.2f})")
                    trade_info = {
                        "date": today_str, "action": "COMPRAR", "ticker": tkr, 
                        "price": price, "shares": shares, "reason": "Signal", "sl": sl_p, "tp": tp_p
                    }
                    self.state["history"].append(trade_info)
                    trades_this_run.append(trade_info)

        # Actualizamos val_pos y val_tot otra vez después de compras
        val_pos = sum(p["shares"] * price_map[t] for t, p in self.state["positions"].items())
        val_tot = self.state["cash"] + val_pos
        pct_tot = (val_tot - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
        
        # Guardar valor de portfolio diario
        self.state["equity_history"][today_str] = val_tot
        self.save()

        print(f"  💰 Cash disponible   : ${self.state['cash']:,.2f}")
        print(f"  📈 Valor posiciones  : ${val_pos:,.2f}")
        print(f"  🏦 Valor total        : ${val_tot:,.2f}  ({pct_tot:+.2f}% vs inicio)\n")

        print("  ── Posiciones abiertas ───────────────────────")
        if not self.state["positions"]:
            print("  (Ninguna)")
        else:
            for tkr, pos in self.state["positions"].items():
                price = price_map[tkr]
                pnl = (price - pos["avg_price"]) / pos["avg_price"] * 100
                emj = "🟢" if pnl >= 0 else "🔴"
                val = pos["shares"] * price
                print(f"  {tkr:<6} {pos['shares']:>6.2f} acc × ${price:,.2f} = ${val:,.0f}  | SL ${pos['sl']:,.0f} TP ${pos['tp']:,.0f}  | {emj} {pnl:+.1f}%")

        print("\n  ── Operaciones simuladas hoy ─────────────────")
        if not executed:
            print("  (Ninguna operación simulada hoy)")
        else:
            for line in executed:
                print(f"  {line}")
            
            # Guardar a CSV heredado de operaciones simuladas
            if trades_this_run:
                df_today = pd.DataFrame(trades_this_run)
                if not os.path.exists(self.csv_path):
                    df_today.to_csv(self.csv_path, index=False)
                else:
                    df_today.to_csv(self.csv_path, mode='a', header=False, index=False)
                print(f"\n  📝 Órdenes guardadas en el histórico: {self.csv_path}")
        print(f"\n{sep}\n")
        
        return executed, val_tot


# ══════════════════════════════════════════════════════════════════════════════
# PUNTO DE ENTRADA
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    start_time = time.time()
    signal_session = latest_completed_session(EXECUTION_DATE)
    ensure_before_next_open(signal_session)
    
    TelegramNotifier.send_message(f"🚀 Iniciando SP500 Genetic Agent. Población: {N_AGENTS}. Descargando datos...")

    # 1. Descargar datos diferenciados IS/OOS
    print("\n[ FASE 1: DESCARGA DE DATOS IN-SAMPLE ]", flush=True)
    data_cache_is = download_all(SP500_POOL, TRAIN_IS_START, TRAIN_IS_END)
    
    print("\n[ FASE 2: DESCARGA DE DATOS OUT-OF-SAMPLE ]")
    data_cache_oos = download_all(SP500_POOL, TRAIN_OOS_START, TRAIN_OOS_END)

    # Filtrar pool a tickers con datos válidos en al menos uno (generalmente IS manda)
    valid_tickers = list(data_cache_is.keys())
    if len(valid_tickers) < 20: 
        raise RuntimeError("No hay suficientes tickers con datos válidos IS.")

    # Reasignar el pool global a los tickers disponibles
    SP500_POOL[:] = valid_tickers
    globals()["POOL_SIZE"] = len(SP500_POOL)

    # 2. Evolucionar la población
    ga = GeneticAlgorithm(data_cache_is, data_cache_oos)
    ga.evolve()

    # 3. Imprimir ganador e historial
    if ga.best_genome is None or ga.best_fitness <= 0:
        print("⚠️  Ningún agente logró retorno positivo en el periodo Out-of-Sample.")
        if ga.best_fitness > -np.inf:
            print(f"    Mejor resultado OOS: {ga.best_fitness:.2f}")
    else:
        print_winner_summary(ga.best_fitness, ga.best_final, ga.best_mdd, ga.best_genome, ga.best_trades)
        
        # Generar gráficas vectoriales de operaciones (solo OOS para mayor legibilidad)
        if os.getenv("MIDAS_RENDER_CHARTS") == "1":
            plot_winner_trades(ga.best_trades, data_cache_oos, ga.best_genome)

    # 4. Liquidar la siguiente sesión disponible aunque no haya ganador hoy.
    # El diario heredado queda congelado: jamás se rellena al cierre de la señal.
    ensure_before_next_open(signal_session)
    buy_list, sell_list, wait_list = [], [], []
    if ga.best_genome is not None and ga.best_fitness > 0:
        buy_list, sell_list, wait_list = generate_live_signals(
            ga.best_genome, signal_session=signal_session)
    forward_path = os.path.join(HISTORICO_DIR, FILE_NAME)
    forward_state = run_forward(
        forward_path, signal_session,
        {row[0]: row[1] for row in buy_list}, [row[0] for row in sell_list],
        ga.best_genome.tech["stop_loss_pct"] if buy_list else None,
        ga.best_genome.tech["take_profit_pct"] if buy_list else None,
    )
    current_val_tot = forward_state["equity_history"][signal_session]
    executed_trades_today = [trade for trade in forward_state["trades"] if trade["session"] == signal_session]
    print(f"Diario heredado congelado; nuevo diario prospectivo: {forward_path}")

    if ga.best_genome is not None and ga.best_fitness > 0:
        # Mensaje Final Telegram
        retorno_str = f"{(ga.best_final - INITIAL_CAPITAL)/INITIAL_CAPITAL*100:.2f}"
        msg = (
            f"📈 <b>CARTERA FORWARD PROSPECTIVA · {signal_session}</b>\n"
            f"💰 Valor modelado: ${current_val_tot:,.2f}\n"
            f"📊 Rentabilidad forward acumulada: {(current_val_tot / INITIAL_CAPITAL - 1) * 100:+.2f}%\n"
            f"Las señales al cierre quedan pendientes hasta la siguiente apertura; no son órdenes reales.\n\n"
            f"🧬 <b>MODELO GENÉTICO SELECCIONADO HOY</b>\n"
            f"🧪 Backtest/validación OOS del modelo: {retorno_str}%\n"
            f"📉 MDD en esa validación: -{ga.best_mdd * 100:.2f}%\n"
            f"🔁 Operaciones en esa validación: {len(ga.best_trades)}\n"
            f"ℹ️ Estas métricas describen al modelo elegido; no son la rentabilidad de la cartera forward.\n\n"
            f"💼 <b>OPERACIONES FORWARD SIMULADAS (CARTERA FICTICIA)</b>\n"
        )
        
        if executed_trades_today:
            for trade in executed_trades_today:
                msg += f"• {trade['side']} {trade['ticker']}: {trade['shares']} acc × ${trade['fill']:.2f} ({trade['reason']})\n"
        else:
            msg += "• Ninguna orden ejecutada hoy.\n"
            
        msg += "\n📡 <b>RADAR GLOBAL S&P 500 (SEÑALES GENÉRICAS)</b>\n"
        if buy_list or sell_list:
            for tkr, wt, cp, rv, sl_p, tp_p, sig in (buy_list + sell_list):
                msg += f"• <b>{tkr}</b>: {sig} tras cierre ${cp:.2f}; pendiente próxima apertura\n"
        else:
            msg += "• No hay señales de Compra/Venta hoy.\n"
            
        TelegramNotifier.send_message(msg)

    end_time = time.time()
    elapsed_time = end_time - start_time
    hours, rem = divmod(elapsed_time, 3600)
    minutes, seconds = divmod(rem, 60)
    print(f"\n⏱️  Tiempo total de ejecución: {int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}\n")
