from pydantic_settings import BaseSettings
import os

class Settings(BaseSettings):
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "sqlite:///./gridgame.db"
    )
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key")
    DEBUG: bool = os.getenv("DEBUG", "True") == "True"

    class Config:
        env_file = ".env"

settings = Settings()