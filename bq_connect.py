"""Reusable BigQuery connection helper + smoke test.

Auth: uses Application Default Credentials (ADC). Set them up once with:
    gcloud auth application-default login

Usage:
    # set your default project (one-off)
    export BQ_PROJECT="your-gcp-project-id"

    # run the built-in smoke test
    .dbenv/bin/python bq_connect.py

    # run an ad-hoc query
    .dbenv/bin/python bq_connect.py "SELECT 1 AS ok"

    # import in other scripts
    from bq_connect import get_client, run_query
"""

import os
import sys

from google.cloud import bigquery

# Project that runs/bills query jobs. Override per-run with BQ_PROJECT.
DEFAULT_PROJECT = "ocean-ml-sandbox"
PROJECT = os.environ.get("BQ_PROJECT") or DEFAULT_PROJECT
# Editorial warehouse tables live here; query them cross-project from BQ_PROJECT.
OCEAN_PROJECT = os.environ.get("BQ_OCEAN_PROJECT") or "frontiers-ocean"
LOCATION = os.environ.get("BQ_LOCATION") or None  # e.g. "EU", "US", "europe-west1"


def get_client() -> bigquery.Client:
    """Return an authenticated BigQuery client using ADC."""
    return bigquery.Client(project=PROJECT, location=LOCATION)


def run_query(sql: str, client: bigquery.Client | None = None):
    """Run a query and return the list of result rows."""
    client = client or get_client()
    job = client.query(sql)
    return list(job.result())


def _smoke_test() -> None:
    client = get_client()
    print(f"Connected. project={client.project!r} location={client.location!r}")

    rows = run_query(
        "SELECT CURRENT_TIMESTAMP() AS now, SESSION_USER() AS who", client
    )
    for row in rows:
        print(f"Server time: {row['now']}  |  Authenticated as: {row['who']}")

    print("\nDatasets visible in this project:")
    datasets = list(client.list_datasets())
    if not datasets:
        print("  (none, or insufficient permissions)")
    for ds in datasets[:25]:
        print(f"  - {ds.dataset_id}")


def main() -> int:
    try:
        if len(sys.argv) > 1:
            for row in run_query(sys.argv[1]):
                print(dict(row))
        else:
            _smoke_test()
    except Exception as exc:  # noqa: BLE001 - surface the real auth/query error
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
