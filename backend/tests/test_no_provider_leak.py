"""CLAUDE.md: no provider SDK import outside `backend/app/ai/providers/`.

Walks every Python file of the repository (backend, tests, the experiments scripts) and checks
the import statements with `ast`, so a comment or a string that merely mentions a package does
not count.
"""

import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND.parent
PROVIDERS_DIR = BACKEND / "app" / "ai" / "providers"

# Top-level packages of LLM provider SDKs. `google.genai` is checked on its full dotted name
# because other `google.*` packages (protobuf, auth) are not providers.
SDK_ROOTS = {"openai", "anthropic", "ollama", "cohere", "mistralai", "groq", "vertexai"}
SDK_DOTTED = ("google.genai", "google.generativeai", "google.ai", "google.cloud.aiplatform")

# The one test file that may import the SDK: it tests the Gemini wrapper itself and needs the SDK's
# error type to simulate a 429. Nothing else is exempt.
EXEMPT = {BACKEND / "tests" / "test_gemini_provider.py"}

SKIP_DIRS = {".venv", "__pycache__", ".git", "node_modules", "build", ".dart_tool", "mobile"}


def python_files() -> list[Path]:
    files = []
    for path in REPO_ROOT.rglob("*.py"):
        if any(part in SKIP_DIRS for part in path.relative_to(REPO_ROOT).parts):
            continue
        files.append(path)
    return files


def imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.append(node.module)
            modules.extend(f"{node.module}.{alias.name}" for alias in node.names)
    return modules


def is_sdk(module: str) -> bool:
    return module.split(".")[0] in SDK_ROOTS or module.startswith(SDK_DOTTED)


def test_no_file_outside_the_providers_folder_imports_a_provider_sdk() -> None:
    offenders = []
    for path in python_files():
        if PROVIDERS_DIR in path.parents or path in EXEMPT:
            continue
        for module in imported_modules(path):
            if is_sdk(module):
                offenders.append(f"{path.relative_to(REPO_ROOT)} imports {module}")

    assert offenders == []


def test_the_check_is_not_vacuous_the_gemini_provider_does_import_the_sdk() -> None:
    gemini = PROVIDERS_DIR / "gemini.py"

    assert any(is_sdk(module) for module in imported_modules(gemini))
    assert gemini in python_files()


def test_the_detector_recognises_the_sdks(tmp_path_factory: object) -> None:
    for module in (
        "google.genai",
        "google.genai.types",
        "google.generativeai",
        "openai",
        "anthropic.types",
    ):
        assert is_sdk(module), module
    for module in ("google.protobuf", "app.ai.provider", "httpx", "app.ai.providers.gemini"):
        assert not is_sdk(module), module


def test_model_names_are_not_hard_coded_in_the_provider_code() -> None:
    for path in PROVIDERS_DIR.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "gemini-" not in source.replace("gemini-fixtures", ""), path.name
        assert "gemini-3" not in source and "gemini-2" not in source, path.name


def test_the_api_key_is_never_printed_or_logged_by_the_provider_code() -> None:
    for path in list((BACKEND / "app").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "print":
                raise AssertionError(f"print() in {path.relative_to(REPO_ROOT)}")
        assert "get_secret_value" not in path.read_text(encoding="utf-8") or path.name in {
            "provider.py",
            "deps.py",
            "auth.py",
            "tokens.py",
            "config.py",
            "database.py",
        }, path.name
