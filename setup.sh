#!/usr/bin/env bash
set -e

# ─────────────────────────────────────────────
# Finclair AI — Project Setup Script
# GitHub: github.com/ayoolat/finclair-ai
# ─────────────────────────────────────────────

REPO_NAME="finclair-ai"
GITHUB_USER="ayoolat"
PROJECT_DIR="$HOME/Documents/projects/$REPO_NAME"

echo ""
echo "🚀 Setting up Finclair AI..."
echo ""

# ── Prerequisites check ──────────────────────
if ! command -v git &>/dev/null; then
  echo "❌ git is not installed. Please install it and re-run."
  exit 1
fi

if ! command -v gh &>/dev/null; then
  echo "❌ GitHub CLI (gh) is not installed."
  echo "   Install it from: https://cli.github.com"
  exit 1
fi

if ! gh auth status &>/dev/null; then
  echo "❌ You are not logged into GitHub CLI."
  echo "   Run: gh auth login"
  exit 1
fi

# ── Create project directory ─────────────────
mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"

echo "📁 Created project at $PROJECT_DIR"

# ── Write all project files ──────────────────

# .env.example
cat > .env.example << 'EOF'
APP_NAME=Finclair AI
DEBUG=true
DATABASE_URL=postgresql+asyncpg://finclair:finclair@db:5432/finclair
SECRET_KEY=change-me-in-production
ACCESS_TOKEN_EXPIRE_MINUTES=30
EOF

# .gitignore
cat > .gitignore << 'EOF'
__pycache__/
*.py[cod]
*.pyo
.env
.venv/
venv/
*.egg-info/
dist/
build/
.mypy_cache/
.ruff_cache/
.pytest_cache/
*.sqlite3
EOF

# requirements.txt
cat > requirements.txt << 'EOF'
fastapi==0.115.0
uvicorn[standard]==0.30.6
sqlalchemy[asyncio]==2.0.35
asyncpg==0.29.0
alembic==1.13.3
pydantic==2.9.2
pydantic-settings==2.5.2
pydantic[email]==2.9.2
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
EOF

# pyproject.toml
cat > pyproject.toml << 'EOF'
[tool.mypy]
python_version = "3.12"
strict = true
ignore_missing_imports = true
plugins = ["pydantic.mypy"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP"]
EOF

# alembic.ini
cat > alembic.ini << 'EOF'
[alembic]
script_location = migrations
prepend_sys_path = .
sqlalchemy.url = driver://user:pass@localhost/dbname

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
EOF

# Dockerfile
cat > Dockerfile << 'EOF'
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
EOF

# docker-compose.yml
cat > docker-compose.yml << 'EOF'
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: finclair
      POSTGRES_PASSWORD: finclair
      POSTGRES_DB: finclair
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U finclair"]
      interval: 5s
      timeout: 5s
      retries: 5

  app:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
    depends_on:
      db:
        condition: service_healthy
    volumes:
      - .:/app
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

volumes:
  postgres_data:
EOF

# README.md
cat > README.md << 'EOF'
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
│   │   └── config.py
│   ├── database/
│   │   └── session.py
│   ├── common/
│   │   ├── middleware/
│   │   │   └── error_handler.py
│   │   └── response/
│   │       ├── result.py
│   │       └── api_response.py
│   └── module/
│       ├── auth/
│       │   ├── dto/auth.py
│       │   ├── service/auth_service.py
│       │   └── router.py
│       └── user/
│           ├── dto/user.py
│           ├── schema/user.py
│           ├── service/user_service.py
│           └── router.py
├── migrations/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── alembic.ini
└── pyproject.toml
```

---

## Key Design Decisions

### Result Pattern
Services never raise exceptions. Every operation returns `Result[T]`:

```python
result = await user_service.get_by_id(1)
if result.is_err:
    return JSONResponse(status_code=result.status_code, ...)
user = result.data
```

### DTOs + Full Typing
- All inputs validated via Pydantic DTOs
- `mypy --strict` enforced
- No use of `Any`

### Domain-Oriented Modules (singular naming)
Each domain owns `dto/`, `schema/`, `service/`, `router.py`.
No repository pattern — SQLAlchemy sessions injected directly into services.

---

## Getting Started

```bash
cp .env.example .env
docker compose up --build
docker compose exec app alembic upgrade head
# Docs: http://localhost:8000/docs
```
EOF

# ── App package structure ────────────────────
mkdir -p app/core
mkdir -p app/database
mkdir -p app/common/middleware
mkdir -p app/common/response
mkdir -p app/module/auth/dto
mkdir -p app/module/auth/schema
mkdir -p app/module/auth/service
mkdir -p app/module/user/dto
mkdir -p app/module/user/schema
mkdir -p app/module/user/service
mkdir -p migrations/versions

# Touch all __init__.py files
touch app/__init__.py
touch app/core/__init__.py
touch app/database/__init__.py
touch app/common/__init__.py
touch app/common/middleware/__init__.py
touch app/common/response/__init__.py
touch app/module/__init__.py
touch app/module/auth/__init__.py
touch app/module/auth/dto/__init__.py
touch app/module/auth/schema/__init__.py
touch app/module/auth/service/__init__.py
touch app/module/user/__init__.py
touch app/module/user/dto/__init__.py
touch app/module/user/schema/__init__.py
touch app/module/user/service/__init__.py

# ── app/core/config.py ───────────────────────
cat > app/core/config.py << 'EOF'
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Finclair AI"
    debug: bool = False
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/finclair"
    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 30

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
EOF

# ── app/database/session.py ──────────────────
cat > app/database/session.py << 'EOF'
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

engine = create_async_engine(settings.database_url, echo=settings.debug)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:  # type: ignore[return]
    async with AsyncSessionLocal() as session:
        yield session  # type: ignore[misc]
EOF

# ── app/common/response/result.py ───────────
cat > app/common/response/result.py << 'EOF'
from typing import Generic, Optional, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class Result(BaseModel, Generic[T]):
    success: bool
    data: Optional[T] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    status_code: int = 200

    @classmethod
    def ok(cls, data: T, status_code: int = 200) -> "Result[T]":
        return cls(success=True, data=data, status_code=status_code)

    @classmethod
    def fail(
        cls,
        error: str,
        error_code: Optional[str] = None,
        status_code: int = 400,
    ) -> "Result[T]":
        return cls(
            success=False,
            error=error,
            error_code=error_code,
            status_code=status_code,
        )

    @property
    def is_ok(self) -> bool:
        return self.success

    @property
    def is_err(self) -> bool:
        return not self.success
EOF

# ── app/common/response/api_response.py ─────
cat > app/common/response/api_response.py << 'EOF'
from typing import Generic, Optional, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    success: bool
    message: Optional[str] = None
    data: Optional[T] = None

    @classmethod
    def ok(cls, data: Optional[T] = None, message: Optional[str] = None) -> "ApiResponse[T]":
        return cls(success=True, data=data, message=message)

    @classmethod
    def error(cls, message: str) -> "ApiResponse[None]":
        return cls(success=False, message=message)
EOF

# ── app/common/response/__init__.py ─────────
cat > app/common/response/__init__.py << 'EOF'
from .result import Result
from .api_response import ApiResponse

__all__ = ["Result", "ApiResponse"]
EOF

# ── app/common/middleware/error_handler.py ──
cat > app/common/middleware/error_handler.py << 'EOF'
import logging
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = logging.getLogger(__name__)


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: object) -> Response:
        try:
            response: Response = await call_next(request)  # type: ignore[operator]
            return response
        except Exception as exc:
            logger.exception("Unhandled exception: %s", exc)
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "message": "An unexpected error occurred.",
                    "error_code": "INTERNAL_SERVER_ERROR",
                },
            )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = [
        {
            "field": ".".join(str(loc) for loc in error["loc"]),
            "message": error["msg"],
            "type": error["type"],
        }
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "message": "Validation failed.",
            "errors": errors,
        },
    )
EOF

# ── app/common/middleware/__init__.py ────────
cat > app/common/middleware/__init__.py << 'EOF'
from .error_handler import ErrorHandlerMiddleware, validation_exception_handler

__all__ = ["ErrorHandlerMiddleware", "validation_exception_handler"]
EOF

# ── app/module/user/schema/user.py ──────────
cat > app/module/user/schema/user.py << 'EOF'
from datetime import datetime
from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database.session import Base


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
EOF

# ── app/module/user/dto/user.py ──────────────
cat > app/module/user/dto/user.py << 'EOF'
from datetime import datetime
from pydantic import BaseModel, EmailStr


class CreateUserDto(BaseModel):
    email: EmailStr
    full_name: str
    password: str


class UpdateUserDto(BaseModel):
    full_name: str | None = None
    is_active: bool | None = None


class UserResponseDto(BaseModel):
    id: int
    email: str
    full_name: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
EOF

# ── app/module/user/service/user_service.py ─
cat > app/module/user/service/user_service.py << 'EOF'
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response import Result
from app.module.user.dto.user import CreateUserDto, UserResponseDto
from app.module.user.schema.user import User


class UserService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_id(self, user_id: int) -> Result[UserResponseDto]:
        result = await self._db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if user is None:
            return Result.fail("User not found.", error_code="USER_NOT_FOUND", status_code=404)

        return Result.ok(UserResponseDto.model_validate(user))

    async def get_by_email(self, email: str) -> Result[UserResponseDto]:
        result = await self._db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if user is None:
            return Result.fail("User not found.", error_code="USER_NOT_FOUND", status_code=404)

        return Result.ok(UserResponseDto.model_validate(user))

    async def create(self, dto: CreateUserDto, hashed_password: str) -> Result[UserResponseDto]:
        existing = await self._db.execute(select(User).where(User.email == dto.email))
        if existing.scalar_one_or_none() is not None:
            return Result.fail(
                "A user with this email already exists.",
                error_code="USER_ALREADY_EXISTS",
                status_code=409,
            )

        user = User(
            email=dto.email,
            full_name=dto.full_name,
            hashed_password=hashed_password,
        )
        self._db.add(user)
        await self._db.commit()
        await self._db.refresh(user)

        return Result.ok(UserResponseDto.model_validate(user), status_code=201)
EOF

# ── app/module/user/router.py ────────────────
cat > app/module/user/router.py << 'EOF'
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response import ApiResponse
from app.database.session import get_db
from app.module.user.dto.user import UserResponseDto
from app.module.user.service.user_service import UserService

router = APIRouter(prefix="/user", tags=["user"])


@router.get("/{user_id}", response_model=ApiResponse[UserResponseDto])
async def get_user(user_id: int, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    result = await UserService(db).get_by_id(user_id)

    if result.is_err:
        return JSONResponse(
            status_code=result.status_code,
            content=ApiResponse.error(result.error or "User not found.").model_dump(),
        )

    return JSONResponse(
        status_code=200,
        content=ApiResponse.ok(data=result.data).model_dump(),
    )
EOF

# ── app/module/auth/dto/auth.py ──────────────
cat > app/module/auth/dto/auth.py << 'EOF'
from pydantic import BaseModel, EmailStr


class LoginDto(BaseModel):
    email: EmailStr
    password: str


class TokenResponseDto(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RegisterDto(BaseModel):
    email: EmailStr
    full_name: str
    password: str
EOF

# ── app/module/auth/service/auth_service.py ─
cat > app/module/auth/service/auth_service.py << 'EOF'
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response import Result
from app.core.config import settings
from app.module.auth.dto.auth import LoginDto, RegisterDto, TokenResponseDto
from app.module.user.dto.user import CreateUserDto
from app.module.user.service.user_service import UserService

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"


def _hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def _verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


def _create_access_token(subject: str, expires_delta: Optional[timedelta] = None) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._user_service = UserService(db)

    async def register(self, dto: RegisterDto) -> Result[TokenResponseDto]:
        create_dto = CreateUserDto(
            email=dto.email, full_name=dto.full_name, password=dto.password
        )
        user_result = await self._user_service.create(
            create_dto, _hash_password(dto.password)
        )

        if user_result.is_err:
            return Result.fail(
                user_result.error or "Registration failed.",
                error_code=user_result.error_code,
                status_code=user_result.status_code,
            )

        token = _create_access_token(str(user_result.data.id))  # type: ignore[union-attr]
        return Result.ok(TokenResponseDto(access_token=token), status_code=201)

    async def login(self, dto: LoginDto) -> Result[TokenResponseDto]:
        from sqlalchemy import select
        from app.module.user.schema.user import User

        result = await self._db.execute(select(User).where(User.email == dto.email))
        user = result.scalar_one_or_none()

        if user is None or not _verify_password(dto.password, user.hashed_password):
            return Result.fail(
                "Invalid email or password.",
                error_code="INVALID_CREDENTIALS",
                status_code=401,
            )

        if not user.is_active:
            return Result.fail(
                "Account is inactive.", error_code="ACCOUNT_INACTIVE", status_code=403
            )

        token = _create_access_token(str(user.id))
        return Result.ok(TokenResponseDto(access_token=token))
EOF

# ── app/module/auth/router.py ────────────────
cat > app/module/auth/router.py << 'EOF'
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response import ApiResponse
from app.database.session import get_db
from app.module.auth.dto.auth import LoginDto, RegisterDto, TokenResponseDto
from app.module.auth.service.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=ApiResponse[TokenResponseDto])
async def register(dto: RegisterDto, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    result = await AuthService(db).register(dto)

    if result.is_err:
        return JSONResponse(
            status_code=result.status_code,
            content=ApiResponse.error(result.error or "Registration failed.").model_dump(),
        )

    return JSONResponse(
        status_code=result.status_code,
        content=ApiResponse.ok(data=result.data, message="Registration successful.").model_dump(),
    )


@router.post("/login", response_model=ApiResponse[TokenResponseDto])
async def login(dto: LoginDto, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    result = await AuthService(db).login(dto)

    if result.is_err:
        return JSONResponse(
            status_code=result.status_code,
            content=ApiResponse.error(result.error or "Login failed.").model_dump(),
        )

    return JSONResponse(
        status_code=result.status_code,
        content=ApiResponse.ok(data=result.data, message="Login successful.").model_dump(),
    )
EOF

# ── app/main.py ──────────────────────────────
cat > app/main.py << 'EOF'
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from app.common.middleware import ErrorHandlerMiddleware, validation_exception_handler
from app.core.config import settings
from app.module.auth.router import router as auth_router
from app.module.user.router import router as user_router

app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(ErrorHandlerMiddleware)
app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]

app.include_router(auth_router, prefix="/api/v1")
app.include_router(user_router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
EOF

# ── migrations/env.py ────────────────────────
cat > migrations/env.py << 'EOF'
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.database.session import Base
from app.module.user.schema.user import User  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: object) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)  # type: ignore[arg-type]
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_async_engine(settings.database_url)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
EOF

echo ""
echo "✅ All files written."
echo ""

# ── Git init + first commit ───────────────────
git init
git add .
git commit -m "feat: initial project scaffold

- FastAPI + PostgreSQL + SQLAlchemy (async)
- Domain-oriented modular structure (singular naming)
- Result pattern — no thrown exceptions
- Pydantic v2 DTOs + strict typing (mypy --strict)
- Global error handler + validation middleware
- Auth module (register/login + JWT)
- User module
- Docker + Docker Compose
- Alembic async migrations"

echo ""
echo "📦 Creating private GitHub repo: $GITHUB_USER/$REPO_NAME..."
echo ""

gh repo create "$GITHUB_USER/$REPO_NAME" \
  --private \
  --source=. \
  --remote=origin \
  --push

echo ""
echo "✅ Done! Your repo is live at: https://github.com/$GITHUB_USER/$REPO_NAME"
echo ""
echo "Next steps:"
echo "  cd $PROJECT_DIR"
echo "  cp .env.example .env"
echo "  docker compose up --build"
echo "  docker compose exec app alembic upgrade head"
echo "  open http://localhost:8000/docs"
echo ""
