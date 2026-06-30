# app/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str
    SECRET_KEY: str
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    RESEND_API_KEY: str = ""
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    CLERK_WEBHOOK_SECRET: str = ""
    JWKS_CLERK_KEY: str = ""
    META_PAGE_TOKEN: str = ""
    GMAIL_EMAIL: str = ""
    GMAIL_APP_PASSWORD: str = ""

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()