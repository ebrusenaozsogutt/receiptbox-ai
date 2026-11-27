"""E3 gold answers, computed by SQL written for this experiment (spec 19: "gold answers computed
by SQL"). It does not call the app's services or tools, so the app is not graded by its own code.

Semantics (spec 6.3, the same rules the app documents): spending = purchases by purchase date,
net of their refunds (a refund reduces its purchase), deleted rows never count, installment
payments are not spending; remaining installments = EXPECTED payments of ACTIVE plans from the
current month on.

A gold answer is a dict: `numbers` (Turkish-formatted amounts or counts that must all appear in
the answer), `names` (texts that must appear), `dates` (dates that must appear), `no_data` (the
records hold nothing for this question), `out_of_scope`.
"""

import uuid
from datetime import date, timedelta
from typing import Any

import asyncpg

from app.ai.tools.base import MONTHS_TR
from app.core.money import format_minor

_NET_PURCHASES = """
SELECT t.id, t.merchant_display AS merchant, c.key AS category, t.purchase_date AS day,
       (t.total_minor - COALESCE((
           SELECT SUM(r.total_minor) FROM transactions r
            WHERE r.refund_of_id = t.id AND r.kind = 'REFUND' AND r.deleted_at IS NULL
       ), 0))::bigint AS net
  FROM transactions t
  LEFT JOIN categories c ON c.id = t.category_id
 WHERE t.user_id = $1 AND t.kind = 'PURCHASE' AND t.deleted_at IS NULL
"""


def tl(minor: int) -> str:
    return format_minor(minor)


def month_tr(day: date) -> str:
    return f"{MONTHS_TR[day.month - 1]} {day.year}"


def as_date(value: Any) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def _filters(spec: dict[str, Any], start: int = 2) -> tuple[str, list[Any]]:
    sql, args = [], []
    if spec.get("from"):
        args.append(as_date(spec["from"]))
        sql.append(f"day >= ${start + len(args) - 1}")
    if spec.get("to"):
        args.append(as_date(spec["to"]))
        sql.append(f"day <= ${start + len(args) - 1}")
    if spec.get("category"):
        args.append(spec["category"])
        sql.append(f"category = ${start + len(args) - 1}")
    if spec.get("merchant"):
        args.append(spec["merchant"])  # the exact shop name (Turkish case rules differ in SQL)
        sql.append(f"merchant = ${start + len(args) - 1}")
    return (" AND ".join(sql) or "TRUE"), args


async def _spend(conn: asyncpg.Connection, user: uuid.UUID, spec: dict[str, Any]) -> int:
    where, args = _filters(spec)
    sql = f"SELECT COALESCE(SUM(net), 0) FROM ({_NET_PURCHASES}) p WHERE {where}"
    return int(await conn.fetchval(sql, user, *args))


async def gold(
    conn: asyncpg.Connection, user: uuid.UUID, today: date, spec: dict[str, Any]
) -> dict:
    kind = spec["kind"]
    out: dict[str, Any] = {"numbers": [], "names": [], "dates": [], "no_data": False}

    if kind == "out_of_scope":
        return {**out, "out_of_scope": True}
    if kind == "no_data":
        return {**out, "no_data": True}

    if kind == "spend":
        total = await _spend(conn, user, spec)
        return {**out, "numbers": [tl(total)]} if total else {**out, "no_data": True}

    if kind == "compare":
        a = await _spend(conn, user, {**spec["a"], "category": spec.get("category")})
        b = await _spend(conn, user, {**spec["b"], "category": spec.get("category")})
        return {**out, "numbers": [tl(a), tl(b)], "optional": [tl(abs(a - b))]}

    if kind in ("top", "biggest", "count"):
        where, args = _filters(spec)
        if kind == "count":
            sql = f"SELECT COUNT(*) FROM ({_NET_PURCHASES}) p WHERE {where}"
            count = int(await conn.fetchval(sql, user, *args))
            return {**out, "numbers": [str(count)]} if count else {**out, "no_data": True}
        limit = spec.get("n", 1)
        sql = (
            f"SELECT merchant, net FROM ({_NET_PURCHASES}) p WHERE {where} AND net > 0 "
            f"ORDER BY net DESC, day DESC LIMIT {int(limit)}"
        )
        rows = await conn.fetch(sql, user, *args)
        if not rows:
            return {**out, "no_data": True}
        names = [rows[0]["merchant"]] if kind == "biggest" else []
        return {**out, "numbers": [tl(r["net"]) for r in rows], "names": names}

    if kind in ("warranty_ending", "return_ending"):
        until = today + timedelta(days=spec["days"])
        if kind == "warranty_ending":
            sql = """SELECT p.name, w.end_date FROM products p
                     JOIN warranties w ON w.product_id = p.id
                     WHERE p.user_id = $1 AND p.status = 'ACTIVE' AND w.end_date BETWEEN $2 AND $3
                     ORDER BY w.end_date"""
        else:
            sql = """SELECT p.name, r.end_date FROM products p
                     JOIN return_windows r ON r.product_id = p.id
                     WHERE p.user_id = $1 AND p.status = 'ACTIVE' AND r.status = 'OPEN'
                       AND r.end_date BETWEEN $2 AND $3 ORDER BY r.end_date"""
        rows = await conn.fetch(sql, user, today, until)
        if not rows:
            return {**out, "no_data": True}
        return {**out, "names": [r["name"] for r in rows], "dates": [r["end_date"] for r in rows]}

    if kind in ("remaining_installments", "month_due"):
        if kind == "remaining_installments":
            sql = """SELECT COALESCE(SUM(ip.amount_minor), 0) FROM installment_payments ip
                     JOIN installment_plans pl ON pl.id = ip.plan_id
                     JOIN transactions t ON t.id = pl.transaction_id
                     WHERE t.user_id = $1 AND t.deleted_at IS NULL AND pl.status = 'ACTIVE'
                       AND ip.status = 'EXPECTED' AND ip.due_month >= $2"""
            value = int(await conn.fetchval(sql, user, today.replace(day=1)))
        else:
            sql = """SELECT COALESCE(SUM(ip.amount_minor), 0) FROM installment_payments ip
                     JOIN installment_plans pl ON pl.id = ip.plan_id
                     JOIN transactions t ON t.id = pl.transaction_id
                     WHERE t.user_id = $1 AND t.deleted_at IS NULL AND pl.status <> 'CANCELLED'
                       AND ip.due_month = $2"""
            value = int(await conn.fetchval(sql, user, as_date(f"{spec['month']}-01")))
        return {**out, "numbers": [tl(value)]} if value else {**out, "no_data": True}

    if kind == "last_installment":
        sql = """SELECT MAX(ip.due_month) FROM installment_payments ip
                 JOIN installment_plans pl ON pl.id = ip.plan_id
                 JOIN transactions t ON t.id = pl.transaction_id
                 WHERE t.user_id = $1 AND t.merchant_display = $2"""
        last = await conn.fetchval(sql, user, spec["merchant"])
        return {**out, "names": [month_tr(last)]} if last else {**out, "no_data": True}

    if kind == "products":
        rows = await conn.fetch(
            "SELECT name FROM products WHERE user_id = $1 AND status = 'ACTIVE' ORDER BY name", user
        )
        return {**out, "names": [r["name"] for r in rows]} if rows else {**out, "no_data": True}

    if kind in ("product_price", "warranty_end", "documents"):
        product = await conn.fetchrow(
            "SELECT id, purchase_price_minor FROM products WHERE user_id = $1 AND name = $2",
            user,
            spec["product"],
        )
        if product is None:
            return {**out, "no_data": True}
        if kind == "product_price":
            return {**out, "numbers": [tl(product["purchase_price_minor"])]}
        if kind == "warranty_end":
            end = await conn.fetchval(
                "SELECT end_date FROM warranties WHERE product_id = $1", product["id"]
            )
            return {**out, "dates": [end]}
        types = await conn.fetch(
            "SELECT type FROM documents WHERE user_id = $1 AND product_id = $2", user, product["id"]
        )
        words = {
            "INVOICE": "fatura",
            "WARRANTY": "garanti",
            "RECEIPT_IMAGE": "fiş",
            "OTHER": "belge",
        }
        return (
            {**out, "names": sorted({words[t["type"]] for t in types})}
            if types
            else {**out, "no_data": True}
        )

    raise ValueError(f"unknown gold kind: {kind}")
