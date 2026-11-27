"""Confirm or correct the E2 pair labels (ai/datasets/e2_pairs/real.jsonl).

    cd ai/experiments && uv run python label_pairs.py

For each pair the bank row and the purchase are shown side by side. Enter = the pre-filled label
is right, a = same purchase, t = installment, i = unrelated, ? = skip, q = save and stop.
"""

from rbx_eval import DATASETS, e2

ANSWERS = {"a": "same", "t": "installment", "i": "unrelated"}


def main() -> None:
    path = DATASETS / "e2_pairs" / "real.jsonl"
    pairs = e2.read_pairs(path)
    todo = [p for p in pairs if not p.get("verified")]
    print(f"{len(pairs)} çift, {len(todo)} tanesi doğrulanacak.")
    print("Enter = doğru, a = aynı alışveriş, t = taksit, i = ilgisiz, ? = geç, q = kaydet ve çık")
    try:
        for index, pair in enumerate(todo, start=1):
            print(f"\n[{index}/{len(todo)}] {pair['kind']}")
            print(f"  Banka:     {pair['show']['bank']}")
            print(f"  Alışveriş: {pair['show']['purchase']}")
            answer = input(f"  Etiket: {pair['label'] or '(yok)'} > ").strip().lower()
            if answer == "q":
                break
            if answer == "?":
                continue
            if answer == "" and pair["label"]:
                pair["verified"] = True
            elif answer in ANSWERS:
                pair.update(label=ANSWERS[answer], verified=True)
    finally:
        e2.write_pairs(path, pairs)
        print("Kaydedildi.")


if __name__ == "__main__":
    main()
