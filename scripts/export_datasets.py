"""Run python -m scripts.export_datasets from the repository root."""
from yieldcrest.datasets import export_datasets

if __name__ == "__main__":
    result = export_datasets()
    for path, details in result["datasets"].items():
        print(f"{path}: {details['rows']} rows")
