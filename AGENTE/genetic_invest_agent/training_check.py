"""Exercise the original full-size genetic training without writing a paper session.

This checks execution, not performance or prospective continuity.
"""
import hashlib
from pathlib import Path
import sp500_portfolio_agent as agent


def main():
    folder = Path(__file__).parent / "registro_historico"
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.glob("diario*.json")}
    data_is = agent.download_all(agent.SP500_POOL, agent.TRAIN_IS_START, agent.TRAIN_IS_END)
    data_oos = agent.download_all(agent.SP500_POOL, agent.TRAIN_OOS_START, agent.TRAIN_OOS_END)
    if len(data_is) < 20:
        raise RuntimeError("Insufficient IS universe")
    agent.SP500_POOL[:] = list(data_is)
    agent.POOL_SIZE = len(agent.SP500_POOL)
    ga = agent.GeneticAlgorithm(data_is, data_oos)
    ga.evolve()
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.glob("diario*.json")}
    if before != after:
        raise RuntimeError("Read-only training changed a canonical diary")
    print(f"Full training completed: {agent.N_AGENTS} agents, {agent.N_GENERATIONS} generations; diaries unchanged")


if __name__ == "__main__":
    main()
