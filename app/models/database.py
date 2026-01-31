"""
D-Nerve Database Models - PostgreSQL with User model
"""

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime,
    Text, Index, Enum, ForeignKey, create_engine
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import enum
import logging

from app.config import settings

logger = logging.getLogger(__name__)

# Database engine
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    echo=False
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class
Base = declarative_base()


# =============================================================================
# ENUMS
# =============================================================================

class UserType(enum.Enum):
    COMMUTER = "commuter"
    DRIVER = "driver"
    ADMIN = "admin"


# =============================================================================
# MODELS
# =============================================================================

class User(Base):
    """Base user table for all user types"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_type = Column(Enum(UserType), nullable=False, default=UserType.DRIVER)
    phone = Column(String(20), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=True)
    password_hash = Column(String(255), nullable=True)
    
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    
    # Relationships
    driver = relationship("Driver", back_populates="user", uselist=False)
    
    __table_args__ = (
        Index('idx_user_phone', 'phone'),
        Index('idx_user_email', 'email'),
    )


class Driver(Base):
    """Driver table - linked to User"""
    __tablename__ = "drivers"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    driver_id = Column(String(50), unique=True, index=True, nullable=False)  # External ID for Android
    
    # Vehicle info
    vehicle_type = Column(String(50), default="Microbus")
    license_plate = Column(String(20), nullable=True)
    
    # Gamification
    total_points = Column(Integer, default=0, index=True)
    tier = Column(String(20), default="Bronze")
    trips_completed = Column(Integer, default=0)
    quality_avg = Column(Float, default=0.0)
    current_streak = Column(Integer, default=0)
    longest_streak = Column(Integer, default=0)
    
    # Rewards
    rewards_earned = Column(Float, default=0.0)
    rewards_withdrawn = Column(Float, default=0.0)
    
    # Status
    is_approved = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="driver")
    
    __table_args__ = (
        Index('idx_driver_points', 'total_points'),
        Index('idx_driver_id', 'driver_id'),
    )


class Trip(Base):
    """Trip table"""
    __tablename__ = "trips"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    trip_id = Column(String(50), unique=True, index=True, nullable=False)
    driver_id = Column(String(50), index=True, nullable=False)  # References Driver.driver_id
    route_id = Column(String(50), nullable=True)
    
    # Time
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    duration_minutes = Column(Float, default=0)
    
    # GPS data
    gps_points_count = Column(Integer, default=0)
    gps_points_json = Column(Text, nullable=True)
    distance_km = Column(Float, default=0)
    
    # Quality & Points
    quality_score = Column(Float, default=0)
    points_earned = Column(Integer, default=0)
    
    # Status
    status = Column(String(20), default="completed")
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_trip_driver', 'driver_id'),
        Index('idx_trip_date', 'start_time'),
    )


class Withdrawal(Base):
    """Withdrawal requests table"""
    __tablename__ = "withdrawals"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    withdrawal_id = Column(String(50), unique=True, index=True, nullable=False)
    driver_id = Column(String(50), index=True, nullable=False)
    
    # Amount
    amount = Column(Float, nullable=False)
    points_deducted = Column(Integer, nullable=False)
    
    # Payment
    payment_method = Column(String(50), nullable=False)
    account_number = Column(String(50), nullable=False)
    
    # Status
    status = Column(String(20), default="pending")
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)
    
    __table_args__ = (
        Index('idx_withdrawal_driver', 'driver_id'),
    )


class Route(Base):
    """Routes table"""
    __tablename__ = "routes"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    route_id = Column(String(50), unique=True, index=True, nullable=False)
    
    name = Column(String(200), nullable=False)
    origin = Column(String(100), nullable=False)
    destination = Column(String(100), nullable=False)
    
    origin_lat = Column(Float, nullable=False)
    origin_lon = Column(Float, nullable=False)
    dest_lat = Column(Float, nullable=False)
    dest_lon = Column(Float, nullable=False)
    
    distance_km = Column(Float, default=0)
    avg_duration_minutes = Column(Float, default=0)
    fare_egp = Column(Float, default=0)
    
    stops = Column(Text, nullable=True)
    trip_count = Column(Integer, default=0)
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PointsTransaction(Base):
    """Points transaction history"""
    __tablename__ = "points_transactions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    driver_id = Column(String(50), index=True, nullable=False)
    
    points = Column(Integer, nullable=False)
    transaction_type = Column(String(50), nullable=False)
    description = Column(String(255), nullable=True)
    
    reference_type = Column(String(50), nullable=True)
    reference_id = Column(String(50), nullable=True)
    
    balance_after = Column(Integer, nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_points_driver', 'driver_id'),
        Index('idx_points_date', 'created_at'),
    )


class Commuter(Base):
    """Commuter table - for future commuter app"""
    __tablename__ = "commuters"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    commuter_id = Column(String(50), unique=True, index=True, nullable=False)
    
    # Preferences
    home_lat = Column(Float, nullable=True)
    home_lon = Column(Float, nullable=True)
    work_lat = Column(Float, nullable=True)
    work_lon = Column(Float, nullable=True)
    
    favorite_routes = Column(Text, nullable=True)  # JSON
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    user = relationship("User", backref="commuter")


# =============================================================================
# DATABASE UTILITIES
# =============================================================================

def get_db():
    """Dependency to get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    """Create all tables"""
    Base.metadata.create_all(bind=engine)
    logger.info("✓ Database tables created")


def init_sample_routes(db):
    """Initialize sample routes if empty"""
    if db.query(Route).count() == 0:
        sample_routes = [
            Route(
                route_id="route_001",
                name="Ramses - Tahrir",
                origin="Ramses Square",
                destination="Tahrir Square",
                origin_lat=30.0626,
                origin_lon=31.2466,
                dest_lat=30.0444,
                dest_lon=31.2357,
                distance_km=3.5,
                avg_duration_minutes=15,
                fare_egp=5.0,
                stops='["Ramses", "26th July", "Tahrir"]',
                trip_count=150
            ),
            Route(
                route_id="route_002",
                name="Giza - Maadi",
                origin="Giza Square",
                destination="Maadi",
                origin_lat=30.0131,
                origin_lon=31.2089,
                dest_lat=29.9602,
                dest_lon=31.2569,
                distance_km=12.0,
                avg_duration_minutes=35,
                fare_egp=10.0,
                stops='["Giza", "Dokki", "Garden City", "Maadi"]',
                trip_count=89
            ),
            Route(
                route_id="route_003",
                name="Heliopolis - Downtown",
                origin="Heliopolis",
                destination="Ataba Square",
                origin_lat=30.0866,
                origin_lon=31.3225,
                dest_lat=30.0519,
                dest_lon=31.2466,
                distance_km=8.5,
                avg_duration_minutes=28,
                fare_egp=8.0,
                stops='["Heliopolis", "Nasr City", "Abbasia", "Ataba"]',
                trip_count=112
            ),
        ]
        
        for route in sample_routes:
            db.add(route)
        
        db.commit()
        logger.info("✓ Sample routes initialized")