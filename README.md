# WFX AI ERP Backend

FastAPI backend for the WFX AI ERP Assistant.

This service will provide:

- ERP dashboard APIs
- Product APIs
- Natural-language ERP assistant APIs
- Typesense text and image search APIs
- Supabase PostgreSQL data access

## Local Setup

Create an environment file:

```bash
cp .env.example .env
```

Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run the API:

```bash
uvicorn app.main:app --reload
```

Default local URL:

```txt
http://localhost:8000
```

Health check:

```txt
http://localhost:8000/health
```

## Current Status

The backend is currently scaffolded with route modules and service placeholders.
External integrations will be added in later milestones.
