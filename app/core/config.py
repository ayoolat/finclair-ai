from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Application
    app_name: str = "Finclair AI"
    debug: bool = False

    # Database — required, no default
    database_url: str

    # Auth — required, no default
    secret_key: str
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    # Redis / RQ — required, no default
    redis_url: str

    # SMTP — all required, no defaults
    smtp_host: str
    smtp_port: int = 587
    smtp_user: str
    smtp_password: str
    smtp_from: str
    smtp_from_name: str = "Finclair"

    # OTP
    otp_expire_minutes: int = 10

    # Cross-server email queue access — required, no default
    email_api_key: str

    # Frontend URL used in email links
    frontend_url: str = "http://localhost:3000"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()  # raises ValidationError at startup if any required field is missing
