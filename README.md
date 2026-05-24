# Finclair AI

FastAPI + PostgreSQL + SQLAlchemy (async) backend using domain-oriented modular structure.

---

## Stack

| Concern | Choice |
|---|---|
| Framework | FastAPI |
| Database | PostgreSQL |
| ORM | SQLAlchemy 2 (async) |
| Validation | Pydantic v2 |
| Migrations | Alembic |
| Auth | python-jose + passlib/bcrypt |
| DevOps | Docker + Docker Compose |

---

## Project Structure

```
finclair-ai/
├── app/
│   ├── core/
│   │   └── config.py           # Pydantic settings (env vars)
│   ├── database/
│   │   └── session.py          # SQLAlchemy engine + session + Base
│   ├── common/
│   │   ├── middleware/
│   │   │   └── error_handler.py  # Global error handler + validation handler
│   │   └── response/
│   │       ├── result.py         # Result[T] pattern (no thrown errors)
│   │       └── api_response.py   # Standard ApiResponse[T] envelope
│   └── module/                 # Domain modules (singular naming)
│       ├── auth/
│       │   ├── dto/auth.py       # LoginDto, RegisterDto, TokenResponseDto
│       │   ├── service/auth_service.py
│       │   └── router.py
│       └── user/
│           ├── dto/user.py       # CreateUserDto, UserResponseDto, …
│           ├── schema/user.py    # SQLAlchemy User model
│           ├── service/user_service.py
│           └── router.py
├── migrations/                 # Alembic async migrations
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── alembic.ini
└── pyproject.toml              # mypy strict + ruff config
```

---

## Key Design Decisions

### Result Pattern (no thrown errors)
Services never raise exceptions. Every operation returns `Result[T]`:

```python
result = await user_service.get_by_id(1)

if result.is_err:
    # handle gracefully
    return JSONResponse(status_code=result.status_code, ...)

user = result.data  # typed, safe
```

### DTOs + Full Typing
- All inputs validated via Pydantic DTOs (`CreateUserDto`, `LoginDto`, etc.)
- All service methods fully type-annotated
- `mypy --strict` configured in `pyproject.toml`
- No use of `Any`

### Domain-Oriented Modules (singular)
Each domain (`user`, `auth`) owns its own `dto/`, `schema/`, `service/`, and `router.py`.
No repository pattern — SQLAlchemy sessions are injected directly into services.

---

## Getting Started

```bash
# 1. Copy env
cp .env.example .env

# 2. Start services
docker compose up --build

# 3. Run migrations
docker compose exec app alembic upgrade head

# 4. API docs
open http://localhost:8000/docs
```
