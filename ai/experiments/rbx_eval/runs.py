"""Experiment configs (YAML) and result folders: results/<exp>/<timestamp>/ (CSV, JSON, PNG)."""

import csv
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from rbx_eval import EXPERIMENTS_DIR

import yaml

RESULTS = EXPERIMENTS_DIR / "results"
CONFIGS = EXPERIMENTS_DIR / "configs"


def load_config(name: str) -> dict[str, Any]:
    """configs/<name>.yaml as a dict."""
    with (CONFIGS / f"{name}.yaml").open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


@dataclass(frozen=True)
class Run:
    experiment: str
    folder: Path

    @classmethod
    def new(cls, experiment: str, *, root: Path = RESULTS, now: datetime | None = None) -> "Run":
        stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
        folder = root / experiment / stamp
        folder.mkdir(parents=True, exist_ok=False)
        return cls(experiment, folder)

    def write_json(self, name: str, data: Any) -> Path:
        path = self.folder / name
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), "utf-8")
        return path

    def write_csv(self, name: str, rows: list[dict[str, Any]]) -> Path:
        path = self.folder / name
        fields: list[str] = []
        for row in rows:
            fields.extend(key for key in row if key not in fields)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        return path


def latest_run(experiment: str, *, root: Path = RESULTS) -> Path | None:
    folder = root / experiment
    if not folder.is_dir():
        return None
    runs = sorted(p for p in folder.iterdir() if p.is_dir())
    return runs[-1] if runs else None
