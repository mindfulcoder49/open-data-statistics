from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional

class Settings(BaseSettings):
    REDIS_PASSWORD: Optional[str] = Field(None, env="REDIS_PASSWORD")
    REDIS_URL: str = Field("redis://redis:6379/0", env="REDIS_URL")
    
    # The broker URL for Celery. If not set, defaults to REDIS_URL.
    # This allows the worker to be on a different network from the backend/redis.
    CELERY_BROKER_URL: Optional[str] = Field(None, env="CELERY_BROKER_URL")
    
    # Local path inside the container for storing results.
    # This path should be within a mounted volume for persistence in development.
    RESULTS_DIR: str = "/app/storage/results"
    
    # The hostname that internal services (like Celery workers) should use
    # to communicate with the API. In a standard docker-compose setup, this is the service name.
    # For a distributed setup, this should be the public domain of the backend.
    INTERNAL_API_HOSTNAME: str = Field("http://backend:8080", env="INTERNAL_API_HOSTNAME")

    # Ollama URL for the completions worker
    OLLAMA_URL: str = Field("http://localhost:11434", env="OLLAMA_URL")

    # Storage Configuration
    STORAGE_TYPE: str = Field("local", env="STORAGE_TYPE") # 'local' or 's3'
    S3_BUCKET_NAME: Optional[str] = Field(None, env="S3_BUCKET_NAME")
    AWS_ACCESS_KEY_ID: Optional[str] = Field(None, env="AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY: Optional[str] = Field(None, env="AWS_SECRET_ACCESS_KEY")
    AWS_DEFAULT_REGION: Optional[str] = Field("us-east-1", env="AWS_DEFAULT_REGION")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding='utf-8', extra='ignore')

settings = Settings()
