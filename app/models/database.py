"""
D-Nerve Database Models - PostgreSQL with User model
"""

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime,
    Text, Index, Enum, ForeignKey, create_engine, UniqueConstraint
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


class DocumentType(enum.Enum):
    """Document types for driver verification"""
    PROFILE_PHOTO = "profile_photo"
    NATIONAL_ID = "national_id"
    DRIVERS_LICENSE = "drivers_license"
    VEHICLE_REGISTRATION = "vehicle_registration"
    VEHICLE_PHOTO = "vehicle_photo"


class DocumentStatus(enum.Enum):
    """Document verification status"""
    NOT_UPLOADED = "not_uploaded"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


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
    driver_id = Column(String(50), unique=True, index=True, nullable=False)
    
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
    driver_id = Column(String(50), index=True, nullable=False)
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
    
    # Passengers
    passenger_count = Column(Integer, default=0)
    
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
    
    favorite_routes = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    user = relationship("User", backref="commuter")


class Badge(Base):
    """Badge definitions"""
    __tablename__ = "badges"
    
    id = Column(Integer, primary_key=True, index=True)
    badge_id = Column(String(50), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    name_ar = Column(String(100), nullable=True)
    description = Column(String(255), nullable=False)
    description_ar = Column(String(255), nullable=True)
    icon = Column(String(50), nullable=False)
    category = Column(String(50), nullable=False)
    requirement_type = Column(String(50), nullable=False)
    requirement_value = Column(Integer, nullable=False)
    points_reward = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class DriverBadge(Base):
    """Driver earned badges"""
    __tablename__ = "driver_badges"
    
    id = Column(Integer, primary_key=True, index=True)
    driver_id = Column(String(50), ForeignKey("drivers.driver_id"), nullable=False)
    badge_id = Column(String(50), ForeignKey("badges.badge_id"), nullable=False)
    earned_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    driver = relationship("Driver", backref="badges")
    badge = relationship("Badge", backref="driver_badges")
    
    __table_args__ = (
        UniqueConstraint('driver_id', 'badge_id', name='unique_driver_badge'),
    )


class Document(Base):
    """Driver documents for verification"""
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(String(50), unique=True, index=True, nullable=False)
    driver_id = Column(String(50), ForeignKey("drivers.driver_id"), nullable=False)
    
    # Document info
    document_type = Column(Enum(DocumentType), nullable=False)
    file_path = Column(String(500), nullable=True)
    file_name = Column(String(255), nullable=True)
    file_size = Column(Integer, default=0)
    
    # Verification
    status = Column(Enum(DocumentStatus), default=DocumentStatus.PENDING)
    rejection_reason = Column(String(255), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    reviewed_by = Column(String(50), nullable=True)
    
    # Timestamps
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    driver = relationship("Driver", backref="documents")
    
    __table_args__ = (
        Index('idx_document_driver', 'driver_id'),
        UniqueConstraint('driver_id', 'document_type', name='unique_driver_document'),
    )


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
    """
    Initialize Cairo microbus routes - EXACT routes used for ML training
    
    These 27 routes were generated using OpenRouteService with real Cairo
    coordinates and used to train the DBSCAN clustering and ETA prediction models.
    
    Source: d-nerve-ml-models/data/cairo/raw/route_summary.csv
    Hub coords: d-nerve-ml-models/data/cairo/cairo_hubs.csv
    """
    if db.query(Route).count() == 0:
        
        # Cairo Hub Coordinates (from cairo_hubs.csv)
        HUBS = {
            "ramses": {"name": "Ramses Square", "lat": 30.0619, "lon": 31.2466},
            "tahrir": {"name": "Tahrir Square", "lat": 30.0444, "lon": 31.2357},
            "giza": {"name": "Giza Square", "lat": 30.0131, "lon": 31.2089},
            "ataba": {"name": "Ataba Square", "lat": 30.0531, "lon": 31.2469},
            "maadi": {"name": "Maadi", "lat": 29.9602, "lon": 31.2569},
            "heliopolis": {"name": "Heliopolis", "lat": 30.0866, "lon": 31.3225},
            "nasr_city": {"name": "Nasr City", "lat": 30.0511, "lon": 31.3656},
            "shubra": {"name": "Shubra", "lat": 30.0986, "lon": 31.2422},
            "mohandessin": {"name": "Mohandessin", "lat": 30.0609, "lon": 31.2003},
            "dokki": {"name": "Dokki", "lat": 30.0392, "lon": 31.2125},
            "ain_shams": {"name": "Ain Shams", "lat": 30.1311, "lon": 31.3194},
            "zeitoun": {"name": "Zeitoun", "lat": 30.1167, "lon": 31.3000},
            "abbassia": {"name": "Abbassia", "lat": 30.0722, "lon": 31.2833},
            "imbaba": {"name": "Imbaba", "lat": 30.0758, "lon": 31.2078},
            "dar_el_salam": {"name": "Dar El Salam", "lat": 29.9833, "lon": 31.2417},
            "6october": {"name": "6th October City", "lat": 29.9389, "lon": 30.9167},
            "new_cairo": {"name": "New Cairo", "lat": 30.0300, "lon": 31.4700},
            "helwan": {"name": "Helwan", "lat": 29.8500, "lon": 31.3340},
        }
        
        # Routes from route_summary.csv (ML training data)
        # Format: (route_id, origin_key, dest_key, total_points, estimated_duration_min, distance_km, fare)
        ML_ROUTES = [
            (1, "dokki", "mohandessin", 721, 6, 2.5, 4.0),
            (2, "tahrir", "mohandessin", 631, 5, 3.0, 5.0),
            (3, "giza", "6october", 4379, 37, 32.0, 15.0),
            (4, "ramses", "giza", 917, 8, 5.5, 6.0),
            (5, "tahrir", "6october", 4582, 38, 35.0, 18.0),
            (6, "tahrir", "giza", 917, 8, 6.0, 6.0),
            (7, "shubra", "imbaba", 1214, 10, 4.0, 5.0),
            (8, "ramses", "ataba", 393, 3, 1.5, 3.0),
            (9, "maadi", "helwan", 2835, 24, 15.0, 10.0),
            (10, "heliopolis", "new_cairo", 2842, 24, 18.0, 12.0),
            (11, "tahrir", "dokki", 521, 4, 3.0, 4.0),
            (12, "tahrir", "maadi", 1988, 17, 10.0, 8.0),
            (13, "heliopolis", "nasr_city", 1436, 12, 5.0, 5.0),
            (14, "ramses", "nasr_city", 2415, 20, 12.0, 10.0),
            (15, "ramses", "tahrir", 321, 3, 2.5, 4.0),
            (16, "ramses", "heliopolis", 1817, 15, 9.0, 8.0),
            (17, "ataba", "zeitoun", 1788, 15, 8.0, 7.0),
            (18, "nasr_city", "new_cairo", 2299, 19, 14.0, 10.0),
            (19, "ataba", "tahrir", 306, 3, 1.5, 3.0),
            (20, "giza", "mohandessin", 1280, 11, 5.0, 5.0),
            (21, "maadi", "dar_el_salam", 958, 8, 4.0, 4.0),
            (22, "nasr_city", "ain_shams", 2174, 18, 10.0, 8.0),
            (23, "abbassia", "heliopolis", 926, 8, 4.0, 5.0),
            (24, "ramses", "shubra", 859, 7, 4.5, 5.0),
            (25, "ataba", "abbassia", 730, 6, 3.5, 4.0),
            (26, "giza", "dokki", 758, 6, 3.0, 4.0),
            (27, "tahrir", "helwan", 3871, 32, 22.0, 12.0),
        ]
        
        cairo_routes = []
        
        for route_id, origin_key, dest_key, total_points, duration, distance, fare in ML_ROUTES:
            origin = HUBS[origin_key]
            dest = HUBS[dest_key]
            
            cairo_routes.append(Route(
                route_id=f"route_{route_id:03d}",
                name=f"{origin['name']} - {dest['name']}",
                origin=origin['name'],
                destination=dest['name'],
                origin_lat=origin['lat'],
                origin_lon=origin['lon'],
                dest_lat=dest['lat'],
                dest_lon=dest['lon'],
                distance_km=distance,
                avg_duration_minutes=duration,
                fare_egp=fare,
                stops=f'["{origin["name"]}", "{dest["name"]}"]',
                trip_count=10  # Each route has 10 trips in training data
            ))
        
        for route in cairo_routes:
            db.add(route)
        
        db.commit()
        logger.info(f"✓ {len(cairo_routes)} ML-trained Cairo routes initialized")