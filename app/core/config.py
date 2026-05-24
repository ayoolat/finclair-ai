from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Finclair AI"
    debug: bool = False
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/finclair"
    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 30

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
