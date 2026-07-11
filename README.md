# Community Shorts Factory

Auto-generates YouTube Shorts and uploads them daily via GitHub Actions.

## Setup

### 1. Clone & install

```bash
git clone https://github.com/BudongJW/community-shorts-factory.git
cd community-shorts-factory
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Environment variables

```bash
cp .env.example .env
```

Fill in the keys you need in `.env`.

### 3. YouTube upload auth (optional)

```bash
# 1) Create an OAuth 2.0 Client (Desktop) in Google Cloud Console,
#    enable YouTube Data API v3, and download the JSON.
mv ~/Downloads/client_secret_*.json config/client_secret.json

# 2) Generate the token (opens a browser login).
python scripts/setup_youtube_token.py
```

### 4. Run locally

```bash
PYTHONIOENCODING=utf-8 python -m src.orchestrator.main --help
```

Use `--skip-upload` to generate without uploading.

## GitHub Actions

Register these repository secrets (Settings > Secrets and variables > Actions):

| Secret | Purpose |
|---|---|
| `YOUTUBE_TOKEN_JSON` | Output of `setup_youtube_token.py` (full JSON) — required for upload |
| `GROQ_API_KEY` | LLM script generation (optional, mode-dependent) |
| `PEXELS_API_KEY` | Stock footage (optional, mode-dependent) |

The workflows then run and upload on schedule automatically. To trigger manually:
Actions tab > select the workflow > **Run workflow**.
