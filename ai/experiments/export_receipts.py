"""Export YOUR captured receipts for E1 into ai/datasets/receipts_real/ (git-ignored).

    cd ai/experiments && uv run python export_receipts.py --email you@example.com [--images]

For every receipt / e-invoice the app read (observations RECEIPT and EINVOICE_QR with a masked
text): masked.txt (the masked text that went to the server; the app never had the unmasked one),
meta.json with the QR fields and the values you saved in the app as a pre-fill (unverified until
you confirm them in label_receipts.py). --images also copies the kept receipt photo (when
"Fiş görsellerini sakla" was on) out of the backend container, for S5. An existing gold.json is
never touched. Bank screenshots are never exported (they never leave the phone).
"""

import argparse
import asyncio
import json
import subprocess
from pathlib import Path

from rbx_eval import DATASETS, REPO, settings

import asyncpg

from app.ai.usage import asyncpg_dsn

MIME_SUFFIX = {"image/jpeg": ".jpg", "image/png": ".png", "application/pdf": ".pdf"}

_RECEIPTS = """
SELECT o.id, o.source, o.masked_text, o.merchant_raw, o.obs_date, o.amount_minor,
       o.extraction_json -> 'qr' AS qr, o.transaction_id,
       t.merchant_display, t.purchase_date, t.total_minor, c.key AS category
  FROM observations o
  LEFT JOIN transactions t ON t.id = o.transaction_id AND t.user_id = o.user_id
  LEFT JOIN categories c ON c.id = t.category_id
 WHERE o.user_id = $1 AND o.source IN ('RECEIPT', 'EINVOICE_QR') AND o.masked_text IS NOT NULL
 ORDER BY o.created_at
"""


async def export(email: str, target: Path, images: bool) -> int:
    conn = await asyncpg.connect(asyncpg_dsn(settings().database_url))
    try:
        user = await conn.fetchval("SELECT id FROM users WHERE email = $1", email.lower())
        if user is None:
            raise SystemExit("No such account.")
        rows = await conn.fetch(_RECEIPTS, user)
        for row in rows:
            folder = target / str(row["id"])
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "masked.txt").write_text(row["masked_text"], encoding="utf-8")
            items = await conn.fetch(
                "SELECT name_raw, total_price_minor FROM receipt_items "
                "WHERE observation_id = $1 ORDER BY position",
                row["id"],
            )
            prefill = {
                "merchant": row["merchant_raw"] or row["merchant_display"],
                "date": (row["purchase_date"] or row["obs_date"]).isoformat()
                if (row["purchase_date"] or row["obs_date"])
                else None,
                "total_minor": row["total_minor"] or row["amount_minor"],
                "category": row["category"],
                "items": [
                    {"name": i["name_raw"], "total_minor": i["total_price_minor"]} for i in items
                ],
            }
            image = None
            if images and row["transaction_id"] is not None:
                doc = await conn.fetchrow(
                    "SELECT storage_key, mime_type FROM documents WHERE user_id = $1 AND "
                    "transaction_id = $2 AND type = 'RECEIPT_IMAGE' ORDER BY created_at LIMIT 1",
                    user,
                    row["transaction_id"],
                )
                if doc is not None and doc["mime_type"] in MIME_SUFFIX:
                    image = "image" + MIME_SUFFIX[doc["mime_type"]]
                    subprocess.run(
                        [
                            "docker", "compose", "-f", str(REPO / "infra" / "docker-compose.yml"),
                            "cp", f"backend:/app/storage/{doc['storage_key']}", str(folder / image),
                        ],
                        check=True,
                    )  # fmt: skip
            qr = row["qr"]
            meta = {
                "source": row["source"],
                "qr": json.loads(qr) if isinstance(qr, str) else qr,
                "prefill": prefill,
                "image": image,
            }
            (folder / "meta.json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        return len(rows)
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--email", required=True)
    parser.add_argument("--images", action="store_true")
    parser.add_argument("--dataset", default="receipts_real")
    args = parser.parse_args()
    count = asyncio.run(export(args.email, DATASETS / args.dataset, args.images))
    print(f"{count} receipts exported to {DATASETS / args.dataset}")


if __name__ == "__main__":
    main()
