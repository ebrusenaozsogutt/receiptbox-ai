"""Label E1 receipts in the terminal: confirm or correct the pre-filled fields.

    cd ai/experiments && uv run python label_receipts.py                 # your exported receipts
    uv run python label_receipts.py --dataset receipts_synthetic --all   # a dry run

Only fields you confirm (Enter) or correct count as gold; "?" leaves a field unverified. Your
answers are saved after every receipt (gold.json next to the text); "q" saves and stops, and the
next run continues where you left off.
"""

import argparse

from rbx_eval import e1, labelling


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dataset", default="receipts_real")
    parser.add_argument("--all", action="store_true", help="also receipts already fully labelled")
    args = parser.parse_args()
    receipts = e1.load_dataset(args.dataset)
    todo = [r for r in receipts if args.all or labelling.needs_work(r)]
    print(f"{len(receipts)} fiş, {len(todo)} tanesi etiketlenecek.")
    for index, receipt in enumerate(todo, start=1):
        print(f"\n[{index}/{len(todo)}]")
        try:
            gold = labelling.label(receipt, input, print)
        except labelling.Quit:
            print("Kaydedildi, çıkılıyor.")
            return
        labelling.save(receipt, gold)
    print("Bitti.")


if __name__ == "__main__":
    main()
