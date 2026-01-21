"""
D-Nerve Database Models
SQLAlchemy models for PostgreSQL

Tables:
- users: All users (commuters + drivers)
- drivers: Driver-specific info
- trips: GPS trip data
- routes: Discovered routes
- points_transactions: Points log
- withdrawals: Reward withdrawals
- eta_predictions: Prediction log
"""

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime,
    ForeignKey, Text, Enum, JSON, Index, create_engine
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from datetime import datetime
import enum

Base = declarative_base()


# =============================================================================
# ENUMS
# =============================================================================

class UserType(enum.Enum):
    COMMUTER = "commuter"
    DRIVER = "driver"
    ADMIN = "admin"


class DriverTier(enum.Enum):
    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"
    PLATINUM = "platinum"
    DIAMOND = "diamond"


class TripStatus(enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    PROCESSING = "processing"


class WithdrawalStatus(enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    COMPLETED = "completed"
    REJECTED = "rejected"


# =============================================================================
# USER MODELS
# =============================================================================

class User(Base):
    """Base user table for all user types"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    user_type = Column(Enum(UserType), nullable=False)
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


class Driver(Base):
    """Driver-specific information"""
    __tablename__ = "drivers"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)

    # Vehicle info
    vehicle_type = Column(String(50), nullable=False)
    license_plate = Column(String(20), unique=True, nullable=False)
    vehicle_capacity = Column(Integer, default=14)

    # Gamification
    total_points = Column(Integer, default=0, index=True)
    current_tier = Column(Enum(DriverTier), default=DriverTier.BRONZE)
    trips_completed = Column(Integer, default=0)
    quality_avg = Column(Float, default=0.0)
    current_streak = Column(Integer, default=0)
    longest_streak = Column(Integer, default=0)

    # Rewards
    rewards_earned = Column(Float, default=0.0)
    rewards_withdrawn = Column(Float, default=0.0)

    # Status
    is_approved = Column(Boolean, default=False)
    approved_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="driver")
    trips = relationship("Trip", back_populates="driver")
    withdrawals = relationship("Withdrawal", back_populates="driver")

    __table_args__ = (
        Index('idx_driver_points', 'total_points'),
        Index('idx_driver_tier', 'current_tier'),
    )

    @property
    def rewards_available(self):
        return self.rewards_earned - self.rewards_withdrawn


# =============================================================================
# ROUTE & TRIP MODELS
# =============================================================================

class Route(Base):
    """Discovered microbus routes"""
    __tablename__ = "routes"

    id = Column(Integer, primary_key=True, index=True)
    route_id = Column(String(50), unique=True, index=True, nullable=False)

    # Route info
    name = Column(String(200), nullable=False)
    origin = Column(String(100), nullable=False)
    destination = Column(String(100), nullable=False)

    # Coordinates
    origin_lat = Column(Float, nullable=False)
    origin_lon = Column(Float, nullable=False)
    dest_lat = Column(Float, nullable=False)
    dest_lon = Column(Float, nullable=False)

    # Stats
    distance_km = Column(Float, nullable=False)
    avg_duration_minutes = Column(Float, nullable=False)
    fare_egp = Column(Float, default=0.0)

    # Route details
    stops = Column(JSON, default=list)
    waypoints = Column(JSON, default=list)

    # Metadata
    trip_count = Column(Integer, default=0)
    cluster_id = Column(Integer, nullable=True)
    confidence = Column(Float, default=0.0)

    is_active = Column(Boolean, default=True)
    discovered_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    trips = relationship("Trip", back_populates="route")

    __table_args__ = (
        Index('idx_route_origin', 'origin_lat', 'origin_lon'),
        Index('idx_route_dest', 'dest_lat', 'dest_lon'),
    )


class Trip(Base):
    """GPS trip data from drivers"""
    __tablename__ = "trips"

    id = Column(Integer, primary_key=True, index=True)
    trip_id = Column(String(50), unique=True, index=True, nullable=False)

    # References
    driver_id = Column(Integer, ForeignKey("drivers.id"), nullable=False)
    route_id = Column(Integer, ForeignKey("routes.id"), nullable=True)

    # Time
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    duration_minutes = Column(Float, nullable=False)

    # GPS data
    num_points = Column(Integer, nullable=False)
    gps_data = Column(JSON, nullable=True)

    # Quality
    quality_score = Column(Float, default=0.0)
    completeness = Column(Float, default=0.0)
    accuracy = Column(Float, default=0.0)
    consistency = Column(Float, default=0.0)
    coverage = Column(Float, default=0.0)

    # Points
    points_earned = Column(Integer, default=0)
    quality_multiplier = Column(Float, default=1.0)
    streak_bonus = Column(Integer, default=0)
    coverage_bonus = Column(Integer, default=0)

    # Status
    status = Column(Enum(TripStatus), default=TripStatus.PENDING)
    rejection_reason = Column(Text, nullable=True)

    # Metadata
    is_new_route = Column(Boolean, default=False)
    distance_km = Column(Float, nullable=True)
    avg_speed_kph = Column(Float, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)

    # Relationships
    driver = relationship("Driver", back_populates="trips")
    route = relationship("Route", back_populates="trips")

    __table_args__ = (
        Index('idx_trip_driver', 'driver_id'),
        Index('idx_trip_route', 'route_id'),
        Index('idx_trip_date', 'start_time'),
    )


# =============================================================================
# GAMIFICATION MODELS
# =============================================================================

class PointsTransaction(Base):
    """Log of all point transactions"""
    __tablename__ = "points_transactions"

    id = Column(Integer, primary_key=True, index=True)
    driver_id = Column(Integer, ForeignKey("drivers.id"), nullable=False)

    points = Column(Integer, nullable=False)
    transaction_type = Column(String(50), nullable=False)
    description = Column(String(255), nullable=True)

    reference_type = Column(String(50), nullable=True)
    reference_id = Column(Integer, nullable=True)

    balance_after = Column(Integer, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_points_driver', 'driver_id'),
        Index('idx_points_date', 'created_at'),
    )


class Withdrawal(Base):
    """Reward withdrawal requests"""
    __tablename__ = "withdrawals"

    id = Column(Integer, primary_key=True, index=True)
    driver_id = Column(Integer, ForeignKey("drivers.id"), nullable=False)

    points = Column(Integer, nullable=False)
    amount_egp = Column(Float, nullable=False)

    payment_method = Column(String(50), nullable=False)
    payment_number = Column(String(20), nullable=False)

    status = Column(Enum(WithdrawalStatus), default=WithdrawalStatus.PENDING)
    rejection_reason = Column(Text, nullable=True)

    requested_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    driver = relationship("Driver", back_populates="withdrawals")


class ETAPrediction(Base):
    """Log of ETA predictions"""
    __tablename__ = "eta_predictions"

    id = Column(Integer, primary_key=True, index=True)

    route_id = Column(Integer, ForeignKey("routes.id"), nullable=True)
    distance_km = Column(Float, nullable=False)
    hour = Column(Integer, nullable=False)
    is_peak = Column(Boolean, nullable=False)

    predicted_minutes = Column(Float, nullable=False)
    confidence_lower = Column(Float, nullable=False)
    confidence_upper = Column(Float, nullable=False)
    model_version = Column(String(20), nullable=False)

    actual_minutes = Column(Float, nullable=True)
    error_minutes = Column(Float, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_eta_route', 'route_id'),
        Index('idx_eta_date', 'created_at'),
    )


# =============================================================================
# DATABASE CONNECTION
# =============================================================================

def get_engine(database_url: str):
    """Create database engine"""
    return create_engine(database_url)


def get_session(engine):
    """Create database session"""
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


def create_tables(engine):
    """Create all tables"""
    Base.metadata.create_all(engine)
    print("✓ Database tables created")


def drop_tables(engine):
    """Drop all tables (use with caution!)"""
    Base.metadata.drop_all(engine)
    print("✗ Database tables dropped")
