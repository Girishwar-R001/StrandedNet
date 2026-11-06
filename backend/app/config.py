"""Runtime configuration. Every value has a working default so the demo runs with no setup."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./stranded.db"
    jwt_secret: str = "dev-only-secret-change-me-before-any-real-deployment"
    jwt_ttl_minutes: int = 720
    # Demo mode exposes reset, simulated passenger responses and the quick-login list.
    demo_mode: bool = True
    # "auto" uses OR-Tools CP-SAT when importable, otherwise the deterministic greedy solver.
    allocation_solver: str = "auto"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    # API requests allowed in flight at once. The rest wait, cheaply, outside the worker threads.
    max_concurrent_requests: int = 32


settings = Settings()
