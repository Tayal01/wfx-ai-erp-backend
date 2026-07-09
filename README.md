# WFX AI ERP Backend

FastAPI-based, AI-native Enterprise Resource Planning (ERP) backend built to power the **WFX AI ERP Assistant**. 

This service acts as the core logical backend, providing natural language data queries, multimodal text and image search (visual similarity), dashboard KPI aggregation, and secure user sessions for apparel industry professionals.

---

## 🏗️ System Architecture & Workflow

The diagram below details the data flow of incoming client requests, from natural-language SQL conversion via OpenRouter to multimodal CLIP searches and database fallbacks:

```mermaid
graph TD
    User([User Client]) -->|HTTP Requests| APIRouter[FastAPI Router]
    
    %% Auth Check
    APIRouter -->|JWT Authentication| AuthService[Auth Service]
    
    %% AI Chat Flow
    APIRouter -->|1. NL Question| AIChatRoute[AI Chat Route]
    AIChatRoute -->|2. Get Answer| VannaService[Vanna Service]
    VannaService -->|3. Prompt + SQL Schema| OpenRouter[OpenRouter API]
    OpenRouter -->|4. Generate SQL| VannaService
    VannaService -->|5. SQL Guardrails Checklist| SQLValidator[SQL Validator]
    SQLValidator -->|6. Safe Query| SQLEngine[PostgreSQL Engine]
    SQLEngine -->|7. Query Database| SupabasePostgres[(Supabase PostgreSQL)]
    SQLEngine -->|8. Raw Rows| VannaService
    VannaService -->|9. Summarize Results| OpenRouter
    OpenRouter -->|10. NL Summary| VannaService
    VannaService -->|11. SQL + Rows + Summary| AIChatRoute
    AIChatRoute -->|12. JSON Response| User
    
    %% Search Flow
    APIRouter -->|1. Search String / Image| SearchRoute[Search Route]
    SearchRoute -->|2. Extract Visual Vector| EmbeddingService[CLIP Embedding Service]
    SearchRoute -->|3. Vector Query| TypesenseService[Typesense Service]
    TypesenseService -->|4. Index Search| TypesenseCloud[(Typesense Cloud)]
    
    %% Search Fallback Flow
    TypesenseService -.->|Typesense Offline Fallback| SupabaseService[Supabase Service]
    SupabaseService -.->|5. pgvector Cosine Search| SupabasePostgres
    
    %% Indexing Scripts
    IndexScript[index_products.py] -->|1. Fetch Products| SupabaseService
    IndexScript -->|2. Generate Embeddings| EmbeddingService
    IndexScript -->|3. Store Vectors| SupabasePostgres
    IndexScript -->|4. Seed Collection| TypesenseService
```

---

## 📂 Codebase Directory Layout

```directory
├── app/                        # Main Application Code
│   ├── config/                 # Configuration and Connections
│   │   ├── __init__.py
│   │   ├── database.py         # SQLAlchemy engine and connection setup
│   │   └── settings.py         # Pydantic Settings management (loads .env)
│   ├── models/                 # Shared Data Models & Schemas
│   │   └── __init__.py
│   ├── routes/                 # API Router Endpoints
│   │   ├── __init__.py
│   │   ├── ai.py               # Natural language chat to SQL (/api/ai/chat)
│   │   ├── auth.py             # Login and user verification (/api/auth)
│   │   ├── dashboard.py        # Dashboard summary analytics (/api/dashboard)
│   │   ├── products.py         # Catalog operations and details (/api/products)
│   │   └── search.py           # Text, Image upload, URL vector search (/api/search)
│   ├── services/               # Core Business Logic & Connectors
│   │   ├── __init__.py
│   │   ├── auth_service.py     # JWT encoding/decoding and access control
│   │   ├── embedding_service.py# SentenceTransformers CLIP vector generation
│   │   ├── supabase_service.py # PostgreSQL DB utilities and retry policies
│   │   ├── typesense_service.py# Typesense sync, indexing, and scoring
│   │   └── vanna_service.py    # Vanna integration, SQL parser, validation
│   └── main.py                 # FastAPI Application instance and middleware
├── database/                   # SQL Definitions
│   └── schema.sql              # Supabase PostgreSQL relational schema
├── scripts/                    # Maintenance & Utility Scripts
│   ├── import_erp_data.py      # Seed CSV files into PostgreSQL tables
│   └── index_products.py       # Compute product embeddings and sync Typesense
├── requirements.txt            # System dependencies
└── runtime.txt                 # Target Python engine
```

---

## ⚙️ Project File Explanations

### Core Configurations
*   **[app/main.py](file:///Users/yogeshsharma/work/wfx-ai-erp-backend/app/main.py)**: Configures the core `FastAPI` instance. It handles CORS origins loaded from settings, mounts the sub-routers, sets up the root endpoint, and provides an active `/health` endpoint displaying connection status (e.g., Supabase state, Vanna/OpenRouter access, Typesense health, and embedding model availability).
*   **[app/config/settings.py](file:///Users/yogeshsharma/work/wfx-ai-erp-backend/app/config/settings.py)**: Defines system settings using Pydantic Settings. Automatically reads environment variables from `.env` and maps configurations such as Supabase keys, OpenRouter LLM preferences, JWT settings, Typesense endpoints, and embedding specifications.
*   **[app/config/database.py](file:///Users/yogeshsharma/work/wfx-ai-erp-backend/app/config/database.py)**: Provides database connections. It loads the `DATABASE_URL` parameter to initialize a lightweight SQLAlchemy connection pool.

### API Routes (`app/routes/`)
*   **[ai.py](file:///Users/yogeshsharma/work/wfx-ai-erp-backend/app/routes/ai.py)**: Exposes the conversational interface `/chat` route. Takes a natural language query, validates length/formatting, passes it to the Vanna service, and handles response mapping.
*   **[auth.py](file:///Users/yogeshsharma/work/wfx-ai-erp-backend/app/routes/auth.py)**: Implements simulated authentication routes, including `/login` (issues a JWT token for valid credentials) and `/me` (decodes the Bearer token and returns the current user profile).
*   **[dashboard.py](file:///Users/yogeshsharma/work/wfx-ai-erp-backend/app/routes/dashboard.py)**: Delivers a summarized snapshot of ERP metrics `/summary`. Protected by authorization headers, this route returns aggregated KPIs (total order revenues, pending invoice counts, buyer percentages) used to populate frontend dashboards.
*   **[products.py](file:///Users/yogeshsharma/work/wfx-ai-erp-backend/app/routes/products.py)**: Provides paginated product listings and detailed views. Contains routes to query style details, fabric construction, and historical orders.
*   **[search.py](file:///Users/yogeshsharma/work/wfx-ai-erp-backend/app/routes/search.py)**: Handles search requests:
    *   `/products`: Standard structured and textual filtering.
    *   `/image`: Decodes uploaded binary image files and returns visually similar products.
    *   `/image-url`: Accepts image URL targets, fetches the image bytes, vectorizes them, and executes similarity search.
    *   `/reindex`: Rebuilds the search collection and updates database embeddings.

### Core Logic Services (`app/services/`)
*   **[auth_service.py](file:///Users/yogeshsharma/work/wfx-ai-erp-backend/app/services/auth_service.py)**: Implements HS256-based JSON Web Tokens (JWT). Signs tokens with a configurable expiration window and provides dependency injection helpers (`get_current_user`) to verify incoming request authorization headers.
*   **[embedding_service.py](file:///Users/yogeshsharma/work/wfx-ai-erp-backend/app/services/embedding_service.py)**: Houses the vectorization engine. It loads the `clip-ViT-B-32` SentenceTransformer (caching it using `@lru_cache`). This model translates both text queries and binary image contents into standardized 512-dimensional vector arrays.
*   **[supabase_service.py](file:///Users/yogeshsharma/work/wfx-ai-erp-backend/app/services/supabase_service.py)**: Standardizes Supabase operations. Employs connection failure logic (handling network errors with exponential backoff) and features a multi-threaded parallel compiler (`ThreadPoolExecutor` utilizing 6 workers) to aggregate dashboard statistics from different database tables.
*   **[typesense_service.py](file:///Users/yogeshsharma/work/wfx-ai-erp-backend/app/services/typesense_service.py)**: Links the search interface with the Typesense cloud cluster. Handles schema creation, document indexing, facets filtering, score normalization, and falling back to PostgreSQL cosine vector similarity (`pgvector` `<=>` operators) if Typesense is unavailable.
*   **[vanna_service.py](file:///Users/yogeshsharma/work/wfx-ai-erp-backend/app/services/vanna_service.py)**: Connects natural language queries with relational databases. Sends prompt messages loaded with the project schema SQL contents to OpenRouter models, and performs security parsing on the generated queries.

### Script Utilities (`scripts/`)
*   **[import_erp_data.py](file:///Users/yogeshsharma/work/wfx-ai-erp-backend/scripts/import_erp_data.py)**: Validates and bulk upserts tabular CSV files into the relational PostgreSQL database tables. Features batch processing (e.g. 500 records per transaction) and dry-run safety modes.
*   **[index_products.py](file:///Users/yogeshsharma/work/wfx-ai-erp-backend/scripts/index_products.py)**: Rebuilds catalog indexing. Fetches styles, computes vector embeddings for images or textual configurations, writes them to the DB, and registers the documents into Typesense.

---

## 🗄️ Relational Database Schema (`database/schema.sql`)

The database uses PostgreSQL (configured inside Supabase) and is equipped with the `vector` (pgvector) extension. The relational structure consists of six tables:

```sql
create extension if not exists vector;

-- 1. Buyers Table: Details of companies placing apparel orders
create table buyers (
    buyer_id text primary key,
    company_name text not null unique,
    country text not null,
    buyer_category text not null,
    created_at timestamptz not null default now()
);

-- 2. Suppliers Table: Details of manufacturing facilities and ratings
create table suppliers (
    supplier_id text primary key,
    company_name text not null unique,
    country text not null,
    contact text not null,
    lead_time_days integer not null check (lead_time_days >= 0),
    rating numeric(3, 2) not null check (rating >= 0 and rating <= 5),
    created_at timestamptz not null default now()
);

-- 3. Finished Goods Table: The core product catalog storing styles
create table finished_goods (
    style_number text primary key,
    style_name text not null,
    category text not null,
    fabric text not null,
    gsm integer not null check (gsm > 0),
    color text not null,
    print text not null,
    season text not null,
    brand text not null,
    supplier text not null references suppliers(company_name),
    cost numeric(12, 2) not null check (cost >= 0),
    selling_price numeric(12, 2) not null check (selling_price >= 0),
    image_url text,
    embedding vector(512),                     -- 512-dim CLIP embedding
    created_at timestamptz not null default now()
);

-- 4. Sales Orders Table: Connects buyers to finished goods style numbers
create table sales_orders (
    order_number text primary key,
    buyer text not null references buyers(company_name),
    style_number text not null references finished_goods(style_number),
    quantity integer not null check (quantity > 0),
    unit_price numeric(12, 2) not null check (unit_price >= 0),
    shipment_date date not null,
    status text not null,
    created_at timestamptz not null default now()
);

-- 5. Sales Invoices Table: Tracks invoices and billing status
create table sales_invoices (
    invoice_number text primary key,
    sales_order text not null references sales_orders(order_number),
    amount numeric(14, 2) not null check (amount >= 0),
    currency text not null,
    payment_status text not null,
    created_at timestamptz not null default now()
);

-- 6. Tech Packs Table: Fabric details and wash configurations
create table tech_packs (
    tech_pack_id text primary key,
    style_number text not null unique references finished_goods(style_number),
    fabric_details text not null,
    construction text not null,
    wash_instructions text not null,
    created_at timestamptz not null default now()
);
```

---

## 🔒 Security Guardrails & SQL Validation

To prevent execution of malicious or destructive queries via the `/chat` route, the backend implements strict query parsing in [vanna_service.py](file:///Users/yogeshsharma/work/wfx-ai-erp-backend/app/services/vanna_service.py) before running queries:

1.  **Read-Only Operations**: Restricts execution to `SELECT` and `WITH` statements only.
2.  **Strict Keyword Blocklist**: Rejects queries containing keywords such as `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE`, `CREATE`, `GRANT`, `REVOKE`, `VACUUM`, `ANALYZE`, or `COPY`.
3.  **Strict Whitelisted Tables**: Prevents system catalogs or metadata access. Only references to `buyers`, `suppliers`, `finished_goods`, `sales_orders`, `sales_invoices`, and `tech_packs` are allowed.
4.  **No Chained Commands**: The query string is verified to prevent semi-colon `;` separation, blocking multi-statement execution.
5.  **Forced Row Limits**: Wrap queries inside a sub-select to enforce a maximum return limit of 100 rows (`LIMIT 100`).

---

## ⚡ Performance Optimizations

*   **Concurrency via Thread Pools**: When fetching statistics for the dashboard, the system utilizes Python's `ThreadPoolExecutor` to trigger 6 database queries concurrently. This prevents sequential network calls from stalling the endpoint response.
*   **Caching Core Elements**:
    *   `CLIP Model Loading`: SentenceTransformer parameters are cached via `functools.lru_cache` so model weights are loaded into memory once and reused.
    *   `Schema Context Retrieval`: The relational schema file is cached after the first reading.
    *   `Query Results Caching`: A TTL (Time-To-Live) cache is applied to dashboard analytics (30 seconds) and product details (120 seconds) to reduce load on the database.
*   **Batch Operations**: ERP seed scripts utilize batch operations to import large files, ensuring memory usage remains constant.

---

## 🛠️ Local Environment Setup

### Prerequisites
*   Python 3.10+
*   Supabase project (with PostgreSQL Database)
*   Typesense Cloud instance or locally running daemon
*   OpenRouter API Key

### Step 1: Clone and Configure Environment Files
Copy the template variables file into a local `.env`:
```bash
cp .env.example .env
```

Open `.env` and fill in the required integration details:
```env
SUPABASE_URL="https://your-project-id.supabase.co"
SUPABASE_SERVICE_ROLE_KEY="your-service-role-key"
SUPABASE_ANON_KEY="your-anon-key"
DATABASE_URL="postgresql://postgres:your-db-pass@aws-0-us-east-1.pooler.supabase.com:6543/postgres"

OPENROUTER_API_KEY="sk-or-v1-..."
OPENROUTER_MODEL="openai/gpt-4o-mini"

TYPESENSE_HOST="your-cluster-id.a1.typesense.net"
TYPESENSE_PORT=443
TYPESENSE_PROTOCOL="https"
TYPESENSE_API_KEY="your-typesense-api-key"
```

### Step 2: Establish Virtual Environment & Install Dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Step 3: Run Database Schemas
Open your Supabase Project **SQL Editor**, paste the contents of `database/schema.sql`, and execute it. This initializes the tables, builds relationships, and activates the pgvector extension.

### Step 4: Load Initial Datasets
Execute the seed import script. It verifies CSV configurations under `docs/data/` and imports them into Supabase:
```bash
# Validate CSV inputs without committing records
python scripts/import_erp_data.py --dry-run

# Import records directly to Supabase
python scripts/import_erp_data.py
```

### Step 5: Index Catalog & Generate Vectors
Execute the product indexing script. This generates visual embeddings using the CLIP model and creates the index inside Typesense:
```bash
python scripts/index_products.py
```

### Step 6: Launch API Service
Run the development server using Uvicorn:
```bash
uvicorn app.main:app --reload
```
The API is now running locally at: **`http://localhost:8000`**

---

## 🚀 API Endpoint Reference

### 1. Authentication

#### Authenticate & Receive JWT Token
*   **Endpoint**: `POST /api/auth/login`
*   **Body**:
    ```json
    {
      "email": "merchandiser@wfx.com",
      "password": "demo1234"
    }
    ```
*   **Example Call**:
    ```bash
    curl -X POST http://127.0.0.1:8000/api/auth/login \
      -H "Content-Type: application/json" \
      -d '{"email":"merchandiser@wfx.com","password":"demo1234"}'
    ```

---

### 2. Dashboard Analytics

#### Retrieve ERP Dashboard Summaries
*   **Endpoint**: `GET /api/dashboard/summary`
*   **Headers**: `Authorization: Bearer <access_token>`
*   **Example Call**:
    ```bash
    curl http://127.0.0.1:8000/api/dashboard/summary \
      -H "Authorization: Bearer <access_token>"
    ```

---

### 3. Product Catalog

#### Fetch Paginated Products
*   **Endpoint**: `GET /api/products`
*   **Headers**: `Authorization: Bearer <access_token>`
*   **Params**: `page` (default 1), `page_size` (default 24), optional filters (`category`, `color`, `fabric`, `season`, `supplier`)
*   **Example Call**:
    ```bash
    curl "http://127.0.0.1:8000/api/products?page=1&page_size=10&category=Shirts" \
      -H "Authorization: Bearer <access_token>"
    ```

#### Fetch Product Detail
*   **Endpoint**: `GET /api/products/{style_number}`
*   **Headers**: `Authorization: Bearer <access_token>`
*   **Example Call**:
    ```bash
    curl http://127.0.0.1:8000/api/products/STYLE101 \
      -H "Authorization: Bearer <access_token>"
    ```

---

### 4. Search Operations

#### Standard & Filter Search
*   **Endpoint**: `POST /api/search/products`
*   **Headers**: `Authorization: Bearer <access_token>`
*   **Body**:
    ```json
    {
      "query": "Cotton printed shirts",
      "category": "Shirts",
      "limit": 12
    }
    ```
*   **Example Call**:
    ```bash
    curl -X POST http://127.0.0.1:8000/api/search/products \
      -H "Authorization: Bearer <access_token>" \
      -H "Content-Type: application/json" \
      -d '{"query": "Cotton printed shirts", "limit": 5}'
    ```

#### Visual Similarity Search (File Upload)
*   **Endpoint**: `POST /api/search/image`
*   **Headers**: `Authorization: Bearer <access_token>`
*   **Body**: Form-data with file payload under `image`
*   **Example Call**:
    ```bash
    curl -X POST http://127.0.0.1:8000/api/search/image \
      -H "Authorization: Bearer <access_token>" \
      -F "image=@/path/to/local_sample.jpg" \
      -F "limit=5"
    ```

#### Visual Similarity Search (Image URL)
*   **Endpoint**: `POST /api/search/image-url`
*   **Headers**: `Authorization: Bearer <access_token>`
*   **Body**:
    ```json
    {
      "image_url": "https://example.com/sample_shirt.jpg",
      "limit": 5
    }
    ```
*   **Example Call**:
    ```bash
    curl -X POST http://127.0.0.1:8000/api/search/image-url \
      -H "Authorization: Bearer <access_token>" \
      -H "Content-Type: application/json" \
      -d '{"image_url": "https://example.com/sample_shirt.jpg", "limit": 5}'
    ```

#### Reindex Catalog Documents
*   **Endpoint**: `POST /api/search/reindex`
*   **Headers**: `Authorization: Bearer <access_token>`
*   **Body**:
    ```json
    {
      "limit": 1000,
      "include_embeddings": true
    }
    ```
*   **Example Call**:
    ```bash
    curl -X POST http://127.0.0.1:8000/api/search/reindex \
      -H "Authorization: Bearer <access_token>" \
      -H "Content-Type: application/json" \
      -d '{"limit": 1000, "include_embeddings": true}'
    ```

---

### 5. Conversational AI Chat

#### Ask AI Natural Language Questions
*   **Endpoint**: `POST /api/ai/chat`
*   **Headers**: `Authorization: Bearer <access_token>`
*   **Body**:
    ```json
    {
      "question": "What is the total revenue generated from buyers in the USA?"
    }
    ```
*   **Response Payload**:
    ```json
    {
      "question": "What is the total revenue generated from buyers in the USA?",
      "sql": "SELECT SUM(so.quantity * so.unit_price) FROM sales_orders so JOIN buyers b ON so.buyer = b.company_name WHERE b.country = 'USA'",
      "row_count": 1,
      "rows": [
        {
          "sum": 245000.00
        }
      ],
      "summary": "The total revenue generated from buyers in the USA is $245,000.00, based on active sales orders."
    }
    ```
*   **Example Call**:
    ```bash
    curl -X POST http://127.0.0.1:8000/api/ai/chat \
      -H "Authorization: Bearer <access_token>" \
      -H "Content-Type: application/json" \
      -d '{"question": "What is the total revenue generated from buyers in the USA?"}'
    ```
