"""ReceiptBox AI evaluation harness (P15, spec 19).

Importing this package puts `backend/` on `sys.path`, so the experiments use the app's own code
(validation, matching features, tools, masker vectors) instead of copies.

Rules (CLAUDE.md, D-016): only the free tier of Gemini, real calls only from here and manual
runs, every real request passes the daily cap, answers are cached per (system, input) so reruns
are free, and requests are paced under the per-minute limits.
"""

import sys
from pathlib import Path

EXPERIMENTS_DIR = Path(__file__).resolve().parents[1]
REPO = EXPERIMENTS_DIR.parents[1]
BACKEND = REPO / "backend"
MOBILE = REPO / "mobile"
DATASETS = REPO / "ai" / "datasets"
REPORT_ASSETS = REPO / "docs" / "report_assets"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def settings(**overrides: object):  # noqa: ANN201
    """The backend settings with the repository's .env (wherever the script is started from).
    The API key and the database URL come from there; nothing is printed."""
    from app.core.config import Settings

    return Settings(_env_file=(REPO / ".env",), **overrides)  # type: ignore[call-arg]
