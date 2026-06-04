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

    # Mono — bank account linking and transaction sync
    mono_secret_key: str

    # Paystack — bank list sync
    paystack_secret_key: str

    # OpenAI — receipt OCR
    openai_api_key: str
    ocr_provider: str = "openai"

    # Digital Ocean Spaces — file storage
    storage_provider: str = "spaces"
    spaces_key: str
    spaces_secret: str
    spaces_region: str
    spaces_bucket: str
    spaces_endpoint_url: str
    spaces_cdn_url: str

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()  # raises ValidationError at startup if any required field is missing
