import csv
from pathlib import Path

from app import parse_csv, rule_based_anomalies

SAMPLE = Path(__file__).parents[1] / "sample_data.csv"


def test_sample_dataset_has_required_columns_and_rows():
    content = SAMPLE.read_bytes()
    transactions = parse_csv(content)
    assert len(transactions) >= 50
    assert {"date", "account", "category", "amount", "period"} <= transactions[0].keys()


def test_rule_layer_finds_material_outliers():
    transactions = parse_csv(SAMPLE.read_bytes())
    flags = rule_based_anomalies(transactions)
    accounts = {flag["account"] for flag in flags}
    assert "Travel Expense" in accounts
    assert "Cloud Infrastructure" in accounts
    assert "Professional Services" in accounts
