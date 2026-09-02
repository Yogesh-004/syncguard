"""Synthetic demo data for SyncGuard."""
import json
import random
import string


def generate_name():
    first_names = ["John", "Jane", "Bob", "Alice", "Charlie", "Diana", "Eve", "Frank", "Grace", "Henry"]
    last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez"]
    return f"{random.choice(first_names)} {random.choice(last_names)}"


def generate_email(name: str) -> str:
    clean = name.lower().replace(" ", ".")
    domains = ["example.com", "test.org", "demo.net", "sample.io"]
    return f"{clean}@{random.choice(domains)}"


def generate_phone() -> str:
    return f"555{random.randint(100000, 999999)}"


def generate_record(record_id: int) -> dict:
    name = generate_name()
    return {
        "id": record_id,
        "source_id": f"source-{random.randint(1, 5)}",
        "source_record_id": f"rec-{record_id:04d}",
        "data": {
            "name": name,
            "email": generate_email(name),
            "phone": generate_phone(),
            "age": random.randint(18, 80),
            "amount": round(random.uniform(10, 10000), 2),
            "date": f"2024-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
        },
        "raw_data": None,
    }


def generate_dataset(num_records: int = 100) -> list:
    return [generate_record(i) for i in range(num_records)]


if __name__ == "__main__":
    data = generate_dataset(100)
    with open("D:/01_Projects/Syncguard/data/demo/records.json", "w") as f:
        json.dump(data, f, indent=2)
    print(f"Generated {len(data)} demo records")

    # Also generate CSV
    import csv
    with open("D:/01_Projects/Syncguard/data/demo/records.csv", "w", newline="") as f:
        if data:
            writer = csv.DictWriter(f, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
    print("Generated CSV demo data")