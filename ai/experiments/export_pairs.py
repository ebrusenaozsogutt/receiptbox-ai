"""Export YOUR matching decisions as E2 pairs: ai/datasets/e2_pairs/real.jsonl (git-ignored).

    cd ai/experiments && uv run python export_pairs.py --email you@example.com

Each match_decisions row becomes a pair with the features the app stored and a PRE-FILLED label
(accepted -> same / installment, rejected -> unrelated, pending -> none). A pre-filled label does
not count until you confirm it with label_pairs.py: "rejected" also covers candidates the system
itself ruled out. Labels you already verified are kept when you export again.
"""

import argparse
import asyncio
import json

from rbx_eval import DATASETS, e2, settings

import asyncpg

from app.ai.usage import asyncpg_dsn

_DECISIONS = """
SELECT d.id, d.match_type, d.decision, d.features_json,
       o.merchant_raw AS bank_merchant, o.amount_minor AS bank_amount, o.obs_date AS bank_date,
       o.installment_seq, o.installment_count,
       t.merchant_display AS merchant, t.total_minor AS amount, t.purchase_date AS day
  FROM match_decisions d
  JOIN observations o ON o.id = d.observation_id
  LEFT JOIN transactions t ON t.id = d.transaction_id
 WHERE o.user_id = $1 AND d.features_json <> '{}'::jsonb
"""


async def export(email: str) -> int:
    conn = await asyncpg.connect(asyncpg_dsn(settings().database_url))
    try:
        user = await conn.fetchval("SELECT id FROM users WHERE email = $1", email.lower())
        if user is None:
            raise SystemExit("No such account.")
        rows = await conn.fetch(_DECISIONS, user)
    finally:
        await conn.close()
    path = DATASETS / "e2_pairs" / "real.jsonl"
    old = {p["id"]: p for p in e2.read_pairs(path)}
    pairs = []
    for row in rows:
        kind = "1:N" if row["match_type"] == "INSTALLMENT" else "1:1"
        prefill = {"ACCEPTED": e2.POSITIVE[kind], "REJECTED": "unrelated"}.get(row["decision"])
        pid = str(row["id"])
        features = row["features_json"]
        marker = (
            f"{row['installment_seq']}/{row['installment_count']}"
            if row["installment_seq"]
            else None
        )
        pair = {
            "id": pid,
            "kind": kind,
            "source": "db",
            "features": json.loads(features) if isinstance(features, str) else features,
            "label": prefill,
            "verified": False,
            "show": {
                "bank": [row["bank_merchant"], row["bank_amount"], str(row["bank_date"]), marker],
                "purchase": [row["merchant"], row["amount"], str(row["day"])],
            },
        }
        if pid in old and old[pid].get("verified"):
            pair.update(label=old[pid]["label"], verified=True)
        pairs.append(pair)
    e2.write_pairs(path, pairs)
    return len(pairs)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    print(f"{asyncio.run(export(args.email))} pairs exported")


if __name__ == "__main__":
    main()
