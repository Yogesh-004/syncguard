"""Benchmark: reconciliation performance."""
import time
import random
from backend.app.services.reconciliation import ReconciliationEngine
from backend.app.services.matching import MatchingEngine


def benchmark_reconciliation(num_records: int = 100):
    records = []
    for i in range(num_records):
        records.append({
            "id": i,
            "name": f"Person {random.randint(1, 50)}",
            "email": f"user{i % 30}@example.com",
            "value": random.uniform(100, 10000),
        })

    engine = ReconciliationEngine(MatchingEngine())

    start = time.time()
    result = engine.run_reconciliation(records)
    elapsed = time.time() - start

    print(f"\nReconciliation Benchmark: {num_records} records in {elapsed:.3f}s")
    return elapsed


if __name__ == "__main__":
    for n in [10, 50, 100, 200]:
        benchmark_reconciliation(n)