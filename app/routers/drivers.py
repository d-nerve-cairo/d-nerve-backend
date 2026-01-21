"""
Drivers Router
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from datetime import datetime

router = APIRouter()

# In-memory storage (replace with database in production)
drivers_db: Dict[str, Dict] = {}


# =============================================================================
# SCHEMAS
# =============================================================================

class DriverRegistration(BaseModel):
    """Driver registration request"""
    name: str = Field(..., min_length=2, max_length=100)
    phone: str = Field(..., min_length=10, max_length=20)
    vehicle_type: str = Field(..., min_length=2, max_length=50)
    license_plate: str = Field(..., min_length=2, max_length=20)


class DriverUpdate(BaseModel):
    """Driver update request"""
    name: Optional[str] = None
    phone: Optional[str] = None
    vehicle_type: Optional[str] = None
    license_plate: Optional[str] = None


class DriverResponse(BaseModel):
    """Driver profile response"""
    driver_id: str
    name: str
    phone: str
    vehicle_type: str
    license_plate: str
    total_points: int
    current_tier: str
    trips_completed: int
    quality_avg: float
    current_streak: int
    rewards_available_egp: float
    member_since: str


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.post("/drivers/register")
async def register_driver(registration: DriverRegistration):
    """
    Register a new driver
    """
    # Check if phone already exists
    for driver in drivers_db.values():
        if driver['phone'] == registration.phone:
            raise HTTPException(status_code=400, detail="Phone number already registered")
    
    # Generate driver ID
    driver_id = f"driver_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    
    drivers_db[driver_id] = {
        "driver_id": driver_id,
        "name": registration.name,
        "phone": registration.phone,
        "vehicle_type": registration.vehicle_type,
        "license_plate": registration.license_plate,
        "total_points": 0,
        "current_tier": "Bronze",
        "trips_completed": 0,
        "quality_avg": 0.0,
        "current_streak": 0,
        "rewards_earned": 0.0,
        "rewards_withdrawn": 0.0,
        "member_since": datetime.utcnow().isoformat(),
        "created_at": datetime.utcnow().isoformat()
    }
    
    return {
        "driver_id": driver_id,
        "message": "Registration successful! Start driving to earn points.",
        "status": "active"
    }


@router.get("/drivers/{driver_id}")
async def get_driver_profile(driver_id: str):
    """
    Get driver profile and stats
    """
    # Check gamification service first
    from app.services.gamification import gamification_service
    stats = gamification_service.get_driver_stats(driver_id)
    
    if stats:
        return stats
    
    # Fall back to database
    if driver_id in drivers_db:
        driver = drivers_db[driver_id]
        return {
            "driver_id": driver["driver_id"],
            "name": driver["name"],
            "phone": driver["phone"],
            "vehicle_type": driver["vehicle_type"],
            "total_points": driver["total_points"],
            "current_tier": driver["current_tier"],
            "trips_completed": driver["trips_completed"],
            "quality_avg": driver["quality_avg"],
            "current_streak": driver["current_streak"],
            "rewards_available_egp": driver["rewards_earned"] - driver["rewards_withdrawn"],
            "member_since": driver["member_since"]
        }
    
    raise HTTPException(status_code=404, detail="Driver not found")


@router.put("/drivers/{driver_id}")
async def update_driver(driver_id: str, updates: DriverUpdate):
    """
    Update driver profile
    """
    if driver_id not in drivers_db:
        raise HTTPException(status_code=404, detail="Driver not found")
    
    driver = drivers_db[driver_id]
    
    if updates.name:
        driver['name'] = updates.name
    if updates.phone:
        driver['phone'] = updates.phone
    if updates.vehicle_type:
        driver['vehicle_type'] = updates.vehicle_type
    if updates.license_plate:
        driver['license_plate'] = updates.license_plate
    
    driver['updated_at'] = datetime.utcnow().isoformat()
    
    return {"message": "Profile updated", "driver": driver}


@router.get("/drivers")
async def list_drivers(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """
    List all drivers (admin endpoint)
    """
    drivers = list(drivers_db.values())
    
    return {
        "drivers": drivers[offset:offset+limit],
        "total": len(drivers),
        "limit": limit,
        "offset": offset
    }
