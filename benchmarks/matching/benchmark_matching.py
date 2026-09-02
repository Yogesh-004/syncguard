"""Benchmark: matching performance."""
import time
import random
from backend.app.services.matching import MatchingEngine


def benchmark_matching(num_records: int = 100):
    records = []
    for i in range(num_records):
        records.append({
            "id": i,
            "name": f"Person {random.randint(1, 50)}",
            "email": f"user{i % 30}@example.com",
            "phone": f"555{random.randint(100000, 999999)}",
        })

    engine = MatchingEngine()

    start = time.time()
    results = engine.find_matches(records, threshold=0.7)
    elapsed = time.time() - start

    print(f"\nMatching Benchmark: {num_records} records, {len(results)} matches found in {elapsed:.3f}s")
    return elapsed


if __name__ == "__main__":
    for n in [10, 50, 100, 200]:
        benchmark_matching(n)