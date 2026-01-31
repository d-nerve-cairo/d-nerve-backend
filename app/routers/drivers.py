"""
Drivers Router - PostgreSQL with User model
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from sqlalchemy.orm import Session

from app.models.database import get_db, User, Driver, UserType

router = APIRouter()


# =============================================================================
# SCHEMAS
# =============================================================================

class DriverRegistration(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    phone: str = Field(..., min_length=10, max_length=20)
    vehicle_type: str = Field(default="Microbus")
    license_plate: Optional[str] = None


class DriverUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    vehicle_type: Optional[str] = None
    license_plate: Optional[str] = None


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def calculate_tier(points: int) -> str:
    if points >= 10000:
        return "Diamond"
    elif points >= 5000:
        return "Platinum"
    elif points >= 2000:
        return "Gold"
    elif points >= 500:
        return "Silver"
    return "Bronze"


def driver_to_dict(driver: Driver) -> dict:
    return {
        "driver_id": driver.driver_id,
        "name": driver.user.name,
        "phone": driver.user.phone,
        "vehicle_type": driver.vehicle_type,
        "license_plate": driver.license_plate or "",
        "total_points": driver.total_points,
        "tier": driver.tier,
        "current_tier": driver.tier,
        "trips_completed": driver.trips_completed,
        "quality_avg": round(driver.quality_avg, 2),
        "current_streak": driver.current_streak,
        "rewards_available_egp": round((driver.rewards_earned or 0) - (driver.rewards_withdrawn or 0), 2),
        "member_since": driver.created_at.isoformat() + "Z" if driver.created_at else ""
    }


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.post("/drivers/register")
async def register_driver(registration: DriverRegistration, db: Session = Depends(get_db)):
    """Register a new driver"""
    
    # Check if phone exists
    existing_user = db.query(User).filter(User.phone == registration.phone).first()
    
    if existing_user:
        # Check if already a driver
        existing_driver = db.query(Driver).filter(Driver.user_id == existing_user.id).first()
        if existing_driver:
            return driver_to_dict(existing_driver)
        
        # User exists but not a driver - create driver profile
        user = existing_user
    else:
        # Create new user
        user = User(
            user_type=UserType.DRIVER,
            phone=registration.phone,
            name=registration.name,
            is_active=True
        )
        db.add(user)
        db.flush()  # Get user.id
    
    # Create driver profile
    driver_id = f"driver_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    
    driver = Driver(
        user_id=user.id,
        driver_id=driver_id,
        vehicle_type=registration.vehicle_type,
        license_plate=registration.license_plate,
        total_points=0,
        tier="Bronze",
        trips_completed=0,
        quality_avg=0.0,
        current_streak=0,
        rewards_earned=0.0,
        rewards_withdrawn=0.0
    )
    
    db.add(driver)
    db.commit()
    db.refresh(driver)
    
    return driver_to_dict(driver)


@router.get("/drivers/{driver_id}")
async def get_driver(driver_id: str, db: Session = Depends(get_db)):
    """Get driver profile"""
    
    driver = db.query(Driver).filter(Driver.driver_id == driver_id).first()
    
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    
    return driver_to_dict(driver)


@router.put("/drivers/{driver_id}")
async def update_driver(driver_id: str, updates: DriverUpdate, db: Session = Depends(get_db)):
    """Update driver profile"""
    
    driver = db.query(Driver).filter(Driver.driver_id == driver_id).first()
    
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    
    # Update user fields
    if updates.name:
        driver.user.name = updates.name
    if updates.phone:
        driver.user.phone = updates.phone
    
    # Update driver fields
    if updates.vehicle_type:
        driver.vehicle_type = updates.vehicle_type
    if updates.license_plate is not None:
        driver.license_plate = updates.license_plate
    
    driver.updated_at = datetime.utcnow()
    driver.user.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(driver)
    
    return {"message": "Profile updated", "driver": driver_to_dict(driver)}


@router.get("/drivers")
async def list_drivers(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """List all drivers"""
    
    total = db.query(Driver).count()
    drivers = db.query(Driver).offset(offset).limit(limit).all()
    
    return {
        "drivers": [driver_to_dict(d) for d in drivers],
        "total": total,
        "limit": limit,
        "offset": offset
    }