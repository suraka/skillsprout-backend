from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: str = "development"
    database_url: str = "postgresql+asyncpg://skillsprout:skillsprout@localhost:5432/skillsprout"
    frontend_url: str = "http://localhost:3000"
    firebase_project_id: str = ""
    firebase_client_email: str = ""
    firebase_private_key: str = ""
    max_students_per_parent: int = 10
    openai_model: str = "gpt-6-astra"  # Reserved for a later, separately enabled AI milestone.

    @model_validator(mode="after")
    def validate_config(self):
        if self.database_url.startswith("postgres://"):
            self.database_url = self.database_url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif self.database_url.startswith("postgresql://"):
            self.database_url = self.database_url.replace(
                "postgresql://", "postgresql+asyncpg://", 1
            )
        if self.app_env == "production":
            if not self.firebase_project_id:
                raise ValueError("FIREBASE_PROJECT_ID is required in production")
            if not self.frontend_url.startswith("https://"):
                raise ValueError("FRONTEND_URL must use HTTPS in production")
        return self


settings = Settings()
