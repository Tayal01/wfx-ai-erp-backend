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

The backend is scaffolded with route modules, settings, health checks, Supabase
schema, and CSV import tooling. Runtime service integrations will be expanded in
later milestones.

## Supabase Database Setup

Create a Supabase project, then open the SQL Editor and run:

```sql
-- paste the contents of database/schema.sql
```

Set local credentials in `.env`:

```env
SUPABASE_URL="your-project-url"
SUPABASE_SERVICE_ROLE_KEY="your-service-role-key"
SUPABASE_ANON_KEY="your-anon-key"
```

Validate CSV files without writing to Supabase:

```bash
python scripts/import_erp_data.py --dry-run
```

Import CSV data into Supabase:

```bash
python scripts/import_erp_data.py
```

Expected row counts:

- buyers: 12
- suppliers: 12
- finished_goods: 1000
- sales_orders: 1500
- sales_invoices: 1206
- tech_packs: 1000
