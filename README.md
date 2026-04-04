# Genie Backend (FastAPI)

Backend API for the Genie document generation platform, built with FastAPI, SQLAlchemy, and Alembic.

## Features

- **Authentication**: Validates NextAuth JWT tokens from the frontend
- **Source Management**: Upload and process PDFs, images, Excel, CSV, and text files
- **Dataset Organization**: Group sources into datasets
- **Prompt Management**: Create, organize, and chain prompts
- **LLM Integration**: Generate content using OpenRouter API (Claude 3.5 Sonnet, etc.)
- **Document Export**: Generate DOCX and TXT exports
- **Infographics**: SSE streaming for infographic generation

## Tech Stack

- **FastAPI** - Async web framework
- **SQLAlchemy 2.0** - Async ORM with asyncpg driver
- **Alembic** - Database migrations
- **Pydantic v2** - Data validation
- **UV** - Fast Python package manager

## Project Structure

```
genie_sv/
├── main.py              # FastAPI application entry point
├── pyproject.toml       # UV/Python project config
├── alembic/             # Database migrations
│   ├── alembic.ini
│   └── versions/
├── app/
│   ├── config.py        # Environment settings
│   ├── database.py      # Async SQLAlchemy engine
│   ├── dependencies.py  # FastAPI dependencies (auth, db)
│   ├── models/          # SQLAlchemy ORM models
│   ├── schemas/         # Pydantic request/response models
│   ├── routers/         # API endpoint handlers
│   ├── services/        # Business logic (LLM, file parsing, etc.)
│   └── utils/           # Utility functions
```

## Setup

### Prerequisites

- Python 3.11+
- PostgreSQL (Supabase)
- UV package manager

### Install Dependencies

```bash
cd genie_sv
uv sync
```

### Environment Variables

Create a `.env` file:

```env
# Database (Supabase PostgreSQL)
DATABASE_URL=postgresql+asyncpg://postgres.xxx:password@aws-0-region.pooler.supabase.com:6543/postgres

# Supabase Storage
SUPABASE_URL=https://yourproject.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key

# OpenRouter LLM API
OPENROUTER_API_KEY=sk-or-v1-xxx

# NextAuth JWT secret (must match frontend)
NEXTAUTH_SECRET=your-nextauth-secret

# CORS (frontend URL)
CORS_ORIGINS=["http://localhost:3000"]
```

### Run Migrations

```bash
# Create database schema
uv run alembic upgrade head
```

### Run Development Server

```bash
# Using UV
uv run uvicorn main:app --reload --port 8000

# Or directly
python main.py
```

## API Endpoints

### Authentication

All endpoints (except `/health`) require a valid NextAuth JWT token in the `Authorization: Bearer <token>` header.

### Main Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/api/users/me` | Current user info |
| GET | `/api/sources` | List user's sources |
| POST | `/api/sources` | Upload a file |
| GET | `/api/datasets` | List datasets |
| GET | `/api/prompts` | List prompts |
| GET | `/api/prompt-folders` | List prompt folders |
| GET | `/api/formats` | List response formats |
| GET | `/api/prompt-chains` | List prompt chains |
| POST | `/api/generate` | Generate content with LLM |
| GET | `/api/generations` | List generation history |
| POST | `/api/exports/docx` | Export to DOCX |
| POST | `/api/exports/txt` | Export to TXT |
| POST | `/api/genie/infographics` | Generate infographic (SSE) |

### Admin Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/admin/users` | List all users |
| PATCH | `/api/admin/users/{id}` | Update user role |

## Swagger Docs

Visit `http://localhost:8000/docs` for interactive API documentation.

## Development

### Code Style

```bash
# Format code
uv run ruff format .

# Lint
uv run ruff check .
```

### Add New Migration

```bash
# Auto-generate from model changes
uv run alembic revision --autogenerate -m "description"

# Apply migrations
uv run alembic upgrade head
```

## Frontend Integration

The frontend (`genie_ui`) connects to this backend using the API client at `src/lib/api.ts`. Set the `NEXT_PUBLIC_BACKEND_URL` environment variable in the frontend to point to this server.

```env
# In genie_ui/.env.local
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
```

## License

MIT
