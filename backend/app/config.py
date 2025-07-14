from pydantic import BaseSettings, Field
import os

class Settings(BaseSettings):
    REDIS_URL: str = Field("redis://redis:6379/0", env="REDIS_URL")
    # Local path inside the container for storing results
    RESULTS_DIR: str = "/app/results"

    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'

settings = Settings()

# Ensure the results directory exists
os.makedirs(settings.RESULTS_DIR, exist_ok=True)
