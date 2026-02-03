"""
Trips Router - PostgreSQL
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
import json
import random
from sqlalchemy.orm import Session

from app.models.database import get_db, Driver, Trip, PointsTransaction

router = APIRouter()


# =============================================================================
# SCHEMAS
# =============================================================================

class GPSPoint(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    timestamp: str
    accuracy_meters: Optional[float] = None
    speed_kph: Optional[float] = None


class TripSubmission(BaseModel):
    driver_id: str
    route_id: Optional[str] = None
    start_time: str
    end_time: str
    gps_points: List[GPSPoint]


class TripResponse(BaseModel):
    trip_id: str
    status: str
    quality_score: float
    points_earned: int
    driver_total_points: int
    driver_tier: str
    message: str


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


def calculate_quality_score(gps_points: List[GPSPoint]) -> float:
    if len(gps_points) < 5:
        return 0.5
    
    score = 0.7
    
    if len(gps_points) >= 20:
        score += 0.15
    elif len(gps_points) >= 10:
        score += 0.1
    
    accurate = sum(1 for p in gps_points if p.accuracy_meters and p.accuracy_meters < 20)
    if accurate > len(gps_points) * 0.8:
        score += 0.1
    
    score += random.uniform(-0.05, 0.05)
    
    return min(max(score, 0.0), 1.0)


def calculate_points(quality_score: float, gps_count: int) -> int:
    base_points = gps_count
    quality_multiplier = 0.5 + quality_score
    return int(base_points * quality_multiplier)


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.post("/trips", response_model=TripResponse)
async def submit_trip(submission: TripSubmission, db: Session = Depends(get_db)):
    """Submit a completed trip"""
    
    # Validate driver
    driver = db.query(Driver).filter(Driver.driver_id == submission.driver_id).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    
    # Validate GPS points
    if len(submission.gps_points) < 5:
        raise HTTPException(status_code=400, detail="Trip must have at least 5 GPS points")
    
    # Calculate scores
    quality_score = calculate_quality_score(submission.gps_points)
    points_earned = calculate_points(quality_score, len(submission.gps_points))
    
    # Parse times
    try:
        start_dt = datetime.fromisoformat(submission.start_time.replace('Z', '+00:00').replace('+00:00', ''))
        end_dt = datetime.fromisoformat(submission.end_time.replace('Z', '+00:00').replace('+00:00', ''))
        duration = (end_dt - start_dt).total_seconds() / 60
    except:
        start_dt = datetime.utcnow()
        end_dt = datetime.utcnow()
        duration = 0
    
    # Create trip
    trip_id = f"trip_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{random.randint(1000, 9999)}"
    
    trip = Trip(
        trip_id=trip_id,
        driver_id=submission.driver_id,
        route_id=submission.route_id,
        start_time=start_dt,
        end_time=end_dt,
        duration_minutes=duration,
        gps_points_count=len(submission.gps_points),
        gps_points_json=json.dumps([p.dict() for p in submission.gps_points]),
        quality_score=quality_score,
        points_earned=points_earned,
        status="completed"
    )
    
    db.add(trip)
    
    # Update driver
    driver.total_points += points_earned
    driver.trips_completed += 1
    driver.rewards_earned = driver.total_points * 0.1
    
    # Update quality average
    total_quality = driver.quality_avg * (driver.trips_completed - 1) + quality_score
    driver.quality_avg = total_quality / driver.trips_completed
    
    # Update tier
    driver.tier = calculate_tier(driver.total_points)
    
    # Log points transaction
    transaction = PointsTransaction(
        driver_id=submission.driver_id,
        points=points_earned,
        transaction_type="earned",
        description=f"Trip completed - {len(submission.gps_points)} GPS points",
        reference_type="trip",
        reference_id=trip_id,
        balance_after=driver.total_points
    )
    
    db.add(transaction)
    db.commit()
    
    return TripResponse(
        trip_id=trip_id,
        status="completed",
        quality_score=round(quality_score, 2),
        points_earned=points_earned,
        driver_total_points=driver.total_points,
        driver_tier=driver.tier,
        message=f"Trip recorded! Earned {points_earned} points."
    )


@router.get("/trips")
async def list_trips(
    driver_id: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """List trips with optional driver filter"""
    
    query = db.query(Trip)
    
    if driver_id:
        query = query.filter(Trip.driver_id == driver_id)
    
    total = query.count()
    trips = query.order_by(Trip.created_at.desc()).offset(offset).limit(limit).all()
    
    return {
        "trips": [
            {
                "trip_id": t.trip_id,
                "driver_id": t.driver_id,
                "route_id": t.route_id,
                "start_time": t.start_time.isoformat() + "Z" if t.start_time else None,
                "end_time": t.end_time.isoformat() + "Z" if t.end_time else None,
                "duration_minutes": round(t.duration_minutes, 1),
                "gps_points_count": t.gps_points_count,
                "gps_points_json": t.gps_points_json,
                "quality_score": round(t.quality_score, 2),
                "points_earned": t.points_earned,
                "status": t.status,
                "created_at": t.created_at.isoformat() + "Z" if t.created_at else None
            }
            for t in trips
        ],
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.get("/trips/{trip_id}")
async def get_trip(trip_id: str, db: Session = Depends(get_db)):
    """Get trip details"""
    
    trip = db.query(Trip).filter(Trip.trip_id == trip_id).first()
    
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    
    return {
        "trip_id": trip.trip_id,
        "driver_id": trip.driver_id,
        "route_id": trip.route_id,
        "start_time": trip.start_time.isoformat() + "Z" if trip.start_time else None,
        "end_time": trip.end_time.isoformat() + "Z" if trip.end_time else None,
        "duration_minutes": round(trip.duration_minutes, 1),
        "gps_points_count": trip.gps_points_count,
        "gps_points_json": trip.gps_points_json,
        "distance_km": round(trip.distance_km, 2) if trip.distance_km else 0,
        "quality_score": round(trip.quality_score, 2),
        "points_earned": trip.points_earned,
        "status": trip.status,
        "created_at": trip.created_at.isoformat() + "Z" if trip.created_at else None
    }


@router.get("/drivers/{driver_id}/trips")
async def get_driver_trips(
    driver_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """Get trips for a specific driver"""
    return await list_trips(driver_id=driver_id, limit=limit, offset=offset, db=db)