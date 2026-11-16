# ReceiptBox AI

An Android app that remembers what you bought: receipts, bank screenshots, installments, warranties and return deadlines, with an AI assistant on top.

**Stack:** Flutter (Android only) · FastAPI · PostgreSQL 16 · Docker Compose.
This is a single-semester senior design project. The current state is tracked in [`docs/PROGRESS.md`](docs/PROGRESS.md).

## Project map

| Path | What it is |
|---|---|
| `mobile/` | The Flutter app (Android only) |
| `backend/` | The FastAPI server (`app/` code, `tests/`, `migrations/` for the database) |
| `infra/` | `docker-compose.yml`: starts PostgreSQL and the backend |
| `ai/` | AI experiments and datasets. `ai/datasets/` is git-ignored: never commit real receipts |
| `docs/` | Specification, phase plans, decisions, progress log |
| `CLAUDE.md` | Rules for Claude Code, which writes the code |
| `.claude/skills/receiptbox-scope/` | The "scope guard" skill: what is in and out of scope |

Read these before changing anything:
[`CLAUDE.md`](CLAUDE.md) · [`.claude/skills/receiptbox-scope/SKILL.md`](.claude/skills/receiptbox-scope/SKILL.md) · [`docs/PROGRESS.md`](docs/PROGRESS.md) · [`docs/spec/00_PROJECT_SPEC.md`](docs/spec/00_PROJECT_SPEC.md) · [`docs/phases/`](docs/phases/) · [`docs/DECISIONS.md`](docs/DECISIONS.md)

---

## 1. Install the tools (Windows 11, one time)

Open **PowerShell** for the commands below. After installing a tool, **close and reopen PowerShell** (and VS Code) so it finds the new program.

### 1.1 Git

```powershell
winget install --id Git.Git -e
git --version
```

### 1.2 Docker Desktop (with WSL 2)

1. Turn on virtualization in your PC's BIOS if it is off (most PCs have it on).
2. Install Docker Desktop from <https://www.docker.com/products/docker-desktop/>. Keep **"Use WSL 2 instead of Hyper-V"** ticked.
3. If Windows asks you to install or update WSL, run in an **administrator** PowerShell: `wsl --install`, then restart the PC.
4. Start **Docker Desktop** and wait until the whale icon says **Engine running**.
5. Check: `docker --version` and `docker info` (no error).

### 1.3 uv (Python package manager) and Python 3.12

```powershell
winget install --id astral-sh.uv -e
uv --version
uv python install 3.12
```

You do not need to install Python separately: `uv` downloads Python 3.12 for the backend by itself.

### 1.4 Flutter SDK

```powershell
git clone https://github.com/flutter/flutter.git -b stable C:\src\flutter
```

Then add `C:\src\flutter\bin` to your PATH: **Start menu → "Edit environment variables for your account" → Path → Edit → New**, paste `C:\src\flutter\bin`, OK. Reopen PowerShell and check:

```powershell
flutter --version
```

### 1.5 Android Studio, SDK and emulator

```powershell
winget install --id Google.AndroidStudio -e
```

1. Open **Android Studio** once. In the setup wizard choose **Standard**, accept the licenses (every license on the left), and wait for the downloads to finish.
2. Open **More Actions → SDK Manager → SDK Tools** tab. Tick **Android SDK Command-line Tools (latest)** and click **Apply**.
3. Open **More Actions → Virtual Device Manager**. A device such as *Medium Phone* or a *Pixel* should be listed. If not, click **Create Device** and pick any recent phone with a Google Play system image.
4. Accept the Android licenses (type `y` to each question):
   ```powershell
   flutter doctor --android-licenses
   ```
5. Check everything:
   ```powershell
   flutter doctor
   ```
   The **Android toolchain** line must have a green check. Warnings about *Visual Studio* or *Chrome* can be ignored: this project is Android only.

---

## 2. First-time project setup

```powershell
git clone <your-private-repo-url> receiptbox-ai
cd receiptbox-ai
copy .env.example .env
```

`.env` holds your local settings. It is git-ignored; never commit it. For P00 you do not need to change anything in it.

---

## 3. Run it (three commands)

### 3.1 Database + backend (Docker)

```powershell
docker compose -f infra/docker-compose.yml up -d
```

Check it:

```powershell
curl http://localhost:8000/api/v1/health
```

You should see `{"status":"ok","db":"ok"}`. API docs are at <http://localhost:8000/docs>.

Useful Docker commands:

```powershell
docker compose -f infra/docker-compose.yml logs backend      # see backend logs
docker compose -f infra/docker-compose.yml down              # stop everything (data is kept)
docker compose -f infra/docker-compose.yml down -v           # stop and DELETE the database data
docker compose -f infra/docker-compose.yml up -d --build     # rebuild after changing backend code
```

> **Port 5433, not 5432.** The Docker database is reachable from your PC at `localhost:5433`, so it never clashes with a PostgreSQL that is already installed on Windows.

### 3.2 Backend on your PC (for development and tests)

Use this instead of the Docker `backend` while you work on backend code. Start only the database:

```powershell
docker compose -f infra/docker-compose.yml up -d db
cd backend
uv sync
uv run uvicorn app.main:app --reload
```

Backend checks:

```powershell
uv run ruff check .
uv run ruff format --check .
uv run pytest -q          # needs the db container running
```

### 3.2.1 Database tables (migrations)

The tables are created by Alembic migrations (`backend/migrations/versions/`). With the database container running:

```powershell
cd backend
uv run alembic upgrade head      # creates all tables and loads the seed data
uv run alembic current           # shows the current version (0002 = up to date)
```

Or from inside the Docker backend container: `docker compose -f infra/docker-compose.yml exec backend alembic upgrade head`.

`uv run alembic downgrade base` removes every table again (and **all data** in them). The tests do this to the separate `receiptbox_test` database by themselves; you never need it for `receiptbox`.

**Look at the tables yourself:** install [DBeaver](https://dbeaver.io/download/) (Community), create a **PostgreSQL** connection with host `127.0.0.1`, port `5433`, database `receiptbox`, user `receiptbox`, password `receiptbox`, then open `receiptbox → Schemas → public → Tables`. Compare them with section 6 of `docs/spec/00_PROJECT_SPEC.md`. Handy queries:

```sql
SELECT key, label_tr, sort_order FROM categories ORDER BY sort_order;
SELECT count(*) FROM merchants;                      -- 223
SELECT a.alias_normalized, m.canonical_name
  FROM merchant_aliases a JOIN merchants m ON m.id = a.merchant_id
 WHERE a.alias_normalized = 'MIGROS TICARET AS';     -- Migros
```

### 3.3 The Android app

1. Start an emulator: Android Studio → **Virtual Device Manager → ▶**, or `flutter emulators --launch <emulator_id>`. Wait until you see the Android home screen.
2. Make sure the backend is running (step 3.1).
3. In another PowerShell:
   ```powershell
   cd mobile
   flutter pub get
   dart run build_runner build
   flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
   ```

The first build takes several minutes (Gradle downloads things). When it works, the emulator shows **"Sunucu: bağlı"** (server connected). If the backend is stopped, tapping **"Tekrar dene"** shows **"Sunucu: bağlantı yok"**.

`10.0.2.2` is the emulator's special address for "the PC it runs on".

Mobile checks:

```powershell
flutter analyze
flutter test
```

`dart run build_runner build` generates the `*.g.dart` files (Riverpod providers). They are git-ignored, so run it after cloning and after changing a provider.

### 3.4 Your real phone over USB (later)

1. On the phone: **Settings → About phone →** tap **Build number** 7 times, then **Settings → Developer options → USB debugging: on**.
2. Plug in the cable and accept the "Allow USB debugging" prompt. Check: `adb devices` should list your phone as `device`. (`adb` is in `%LOCALAPPDATA%\Android\Sdk\platform-tools`.)
3. Let the phone reach the backend on your PC through the cable:
   ```powershell
   adb reverse tcp:8000 tcp:8000
   ```
4. Run with a different address:
   ```powershell
   flutter run --dart-define=API_BASE_URL=http://localhost:8000
   ```

---

## 4. Troubleshooting

| Problem | Fix |
|---|---|
| `flutter`, `uv` or `docker` "is not recognized" | Close and reopen PowerShell / VS Code. Then check your PATH (see 1.4). |
| `docker ... failed to connect to the docker API` | Docker Desktop is not running. Start it and wait for **Engine running**. |
| `port is already allocated` on 8000 | Something else uses port 8000. Stop it, or change the port mapping in `infra/docker-compose.yml`. |
| `pytest` cannot connect to the database | Start it: `docker compose -f infra/docker-compose.yml up -d db`. Tests use `127.0.0.1:5433`. |
| Database connections are slow (about 2 seconds each) | Use `127.0.0.1` instead of `localhost` in the database URLs (some Windows PCs try IPv6 first). The defaults already do. |
| App shows "Sunucu: bağlantı yok" | Is the backend running? Open <http://localhost:8000/api/v1/health> in your PC browser. On a real phone use `adb reverse` (3.4). |
| Emulator is very slow or does not start | Run `emulator -accel-check` from `%LOCALAPPDATA%\Android\Sdk\emulator`. Make sure virtualization is on in BIOS and "Windows Hypervisor Platform" is enabled in Windows Features. |
| `flutter doctor` complains about Android licenses | `flutter doctor --android-licenses` |

---

## 5. Secrets and private data

- `.env` is never committed. `.env.example` lists every setting with placeholder values only.
- `ai/datasets/` and `backend/storage/` are git-ignored. **Never commit real receipts, real bank screenshots or personal data.**
- Docker Compose uses an obviously fake development JWT secret (`infra/dev-defaults.env`). Put your own in `.env` for anything beyond local development.

## 6. Continuous integration

`.github/workflows/ci.yml` runs on every push to `main` and on pull requests:

- **backend:** `uv sync`, `ruff check`, `ruff format --check`, `pytest` (with a PostgreSQL service)
- **mobile:** `flutter pub get`, `build_runner`, `flutter analyze`, `flutter test`

## 7. Commit messages

`P07: add receipt review confirm endpoint` (phase number first). See [`CLAUDE.md`](CLAUDE.md) for the full conventions.
