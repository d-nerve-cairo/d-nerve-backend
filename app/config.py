"""
D-Nerve Backend Configuration
"""

from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    """Application settings"""
    
    # App
    APP_NAME: str = "D-Nerve Cairo Transit API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    
    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/dnerve"
    
    # For SQLite (development):
    # DATABASE_URL: str = "sqlite:///./dnerve.db"
    
    # Security (for future auth)
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    
    # ML Models
    MODEL_DIR: str = os.path.join(os.path.dirname(__file__), "ml", "models")
    
    # Cairo bounds
    CAIRO_LAT_MIN: float = 29.7
    CAIRO_LAT_MAX: float = 30.3
    CAIRO_LON_MIN: float = 31.0
    CAIRO_LON_MAX: float = 31.6
    
    # Gamification
    POINTS_PER_TRIP: int = 10
    REWARD_RATE: float = 0.1  # EGP per point
    MIN_WITHDRAWAL_POINTS: int = 100
    
    class Config:
        env_file = ".env"
        case_sensitive = True


# Global settings instance
settings = Settings()
