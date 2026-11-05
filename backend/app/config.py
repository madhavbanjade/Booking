from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # Required
    database_url: str
    secret_key: str

    # Frontend (used for CORS and for links inside emails)
    frontend_url: str = "http://localhost:3000"

    # Login cookie
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days
    cookie_secure: bool = False  # set to true in production (HTTPS only)
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"

    # Gmail SMTP (leave credentials empty in development to print messages locally).
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    smtp_from_name: str = "BuildCo"
    admin_notify_email: str | None = None

    # Cloudflare Turnstile. If the key is empty, the captcha check is skipped.
    turnstile_secret_key: str | None = None

    # Cloudinary (image uploads)
    cloudinary_cloud_name: str | None = None
    cloudinary_api_key: str | None = None
    cloudinary_api_secret: str | None = None

    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore")


settings = Settings()
