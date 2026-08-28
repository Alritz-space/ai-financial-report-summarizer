import csv
import io
import json
import os
import statistics
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import google.generativeai as genai

BASE_DIR = Path(__file__).resolve().parent
PROMPT_PATH = BASE_DIR / "prompts" / "summarizer_prompt.txt"

app = FastAPI(title="AI Financial Report Summarizer", version="1.0.0")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


class DataValidationError(ValueError):
    pass


def parse_csv(content: bytes) -> list[dict[str, Any]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DataValidationError("CSV must be UTF-8 encoded.") from exc

    reader = csv.DictReader(io.StringIO(text))
    required = {"date", "account", "category", "amount", "period"}

    if not reader.fieldnames:
        raise DataValidationError("CSV is missing a header row.")

    missing = required - set(reader.fieldnames)
    if missing:
        raise DataValidationError(
            "Missing required columns: " + ", ".join(sorted(missing))
        )

    transactions = []
    for line_no, row in enumerate(reader, start=2):
        try:
            tx_date = row["date"].strip()
            account = row["account"].strip()
            category = row["category"].strip()
            period = row["period"].strip()
            amount = float(row["amount"])
        except (AttributeError, TypeError, ValueError) as exc:
            raise DataValidationError(
                f"Invalid value on CSV line {line_no}."
            ) from exc

        if not all([tx_date, account, category, period]):
            raise DataValidationError(f"Blank required value on CSV line {line_no}.")
        transactions.append(
            {
                "date": tx_date,
                "account": account,
                "category": category,
                "amount": round(amount, 2),
                "period": period,
            }
        )

    if not transactions:
        raise DataValidationError("CSV contains no transaction rows.")
    if len(transactions) > 10000:
        raise DataValidationError("CSV is too large for this portfolio prototype (max 10,000 rows).")

    return transactions


def rule_based_anomalies(transactions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_account: dict[str, list[float]] = {}
    for tx in transactions:
        by_account.setdefault(tx["account"], []).append(tx["amount"])

    anomalies = []
    for tx in transactions:
        values = by_account[tx["account"]]
        if len(values) < 3:
            continue

        mean = statistics.mean(values)
        stdev = statistics.stdev(values)
        if stdev == 0:
            continue

        z_score = abs(tx["amount"] - mean) / stdev
        if z_score > 2:
            anomalies.append(
                {
                    "account": tx["account"],
                    "category": tx["category"],
                    "date": tx["date"],
                    "period": tx["period"],
                    "amount": tx["amount"],
                    "z_score": round(z_score, 2),
                    "source": "rule",
                    "detail": (
                        f"{tx['period']} transaction of {tx['amount']:,.2f} "
                        f"(z-score {z_score:.2f} against {tx['account']} history)."
                    ),
                }
            )

    return anomalies


def compact_dataset(transactions: list[dict[str, Any]]) -> dict[str, Any]:
    periods = sorted({tx["period"] for tx in transactions})
    quarter_totals = []
    for period in periods:
        total = sum(tx["amount"] for tx in transactions if tx["period"] == period)
        quarter_totals.append({"period": period, "total": round(total, 2)})

    category_totals = {}
    for tx in transactions:
        category_totals.setdefault(tx["category"], 0.0)
        category_totals[tx["category"]] += tx["amount"]

    return {
        "transactions": transactions,
        "period_totals": quarter_totals,
        "category_totals": [
            {"category": k, "total": round(v, 2)}
            for k, v in sorted(category_totals.items(), key=lambda x: abs(x[1]), reverse=True)
        ],
    }


def call_gemini(dataset: dict[str, Any], rule_flags: list[dict[str, Any]]) -> dict[str, Any]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="GEMINI_API_KEY is not configured. Add it to your environment before analyzing."
        )

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name=MODEL_NAME,
        system_instruction=PROMPT_PATH.read_text(encoding="utf-8"),
        generation_config=genai.GenerationConfig(
            response_mime_type="application/json",
            response_schema={
                "type": "OBJECT",
                "properties": {
                    "summary": {"type": "STRING"},
                    "anomalies": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "account": {"type": "STRING"},
                                "detail": {"type": "STRING"},
                                "reason": {"type": "STRING"},
                            },
                            "required": ["account", "detail", "reason"],
                        },
                    },
                },
                "required": ["summary", "anomalies"],
            },
            temperature=0.2,
        ),
    )

    payload = {
        "financial_data": dataset,
        "rule_based_anomalies": rule_flags,
    }
    response = model.generate_content(json.dumps(payload, separators=(",", ":")))
    text = response.text.strip()

    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="Gemini returned invalid JSON.") from exc

    return result


def merge_anomalies(
    llm_anomalies: list[dict[str, Any]],
    rule_flags: list[dict[str, Any]],
) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []

    def key(item: dict[str, Any]) -> str:
        detail = str(item.get("detail", "")).lower()
        account = str(item.get("account", "")).lower()
        return f"{account}|{detail[:100]}"

    seen = set()

    # Prefer LLM wording for rule flags when it confirms them.
    for item in llm_anomalies:
        normalized = {
            "account": str(item.get("account", "Unknown")),
            "detail": str(item.get("detail", "")),
            "reason": str(item.get("reason", "")),
        }
        k = key(normalized)
        if k not in seen:
            merged.append(normalized)
            seen.add(k)

    for flag in rule_flags:
        normalized = {
            "account": flag["account"],
            "detail": flag["detail"],
            "reason": (
                "Rule-based statistical flag: this transaction is more than "
                "2 standard deviations from the account's historical pattern."
            ),
        }
        # Account + period + amount is a stronger duplicate signal than prose.
        duplicate = any(
            x["account"] == normalized["account"]
            and str(flag["period"]) in x["detail"]
            and f"{flag['amount']:,.2f}" in x["detail"]
            for x in merged
        )
        if not duplicate:
            merged.append(normalized)

    return merged[:8]


@app.get("/")
def index():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file.")

    try:
        content = await file.read()
        transactions = parse_csv(content)
    except DataValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    rule_flags = rule_based_anomalies(transactions)
    dataset = compact_dataset(transactions)
    result = call_gemini(dataset, rule_flags)

    summary = str(result.get("summary", "")).strip()
    anomalies = result.get("anomalies", [])
    if not isinstance(anomalies, list):
        anomalies = []

    return {
        "summary": summary,
        "anomalies": merge_anomalies(anomalies, rule_flags),
        "metadata": {
            "transactions_analyzed": len(transactions),
            "rule_flags": len(rule_flags),
            "model": MODEL_NAME,
        },
    }
