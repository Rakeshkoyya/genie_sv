"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # Database
    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/genie"
    
    @computed_field
    @property
    def async_database_url(self) -> str:
        """Convert database URL to async format if needed."""
        url = self.database_url
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url
    
    # Supabase
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    
    # OpenRouter LLM
    openrouter_api_key: str = ""
    openrouter_model: str = "anthropic/claude-3.5-sonnet"
    openrouter_image_model: str = "google/gemini-3.1-flash-image-preview"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    
    # NextAuth JWT validation
    nextauth_secret: str = ""
    
    # Server
    debug: bool = False
    cors_origins: list[str] = ["http://localhost:3000"]
    
    # Storage bucket names
    input_files_bucket: str = "input-files"
    exports_bucket: str = "exports"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
