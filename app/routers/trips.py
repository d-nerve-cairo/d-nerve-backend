"""
Trips Router
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime

from app.services.gamification import gamification_service, TripData

router = APIRouter()

# In-memory storage (replace with database in production)
trips_db: Dict[str, Dict] = {}


# =============================================================================
# SCHEMAS
# =============================================================================

class GPSPoint(BaseModel):
    """Single GPS point"""
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    timestamp: datetime
    accuracy_meters: Optional[float] = None
    speed_kph: Optional[float] = None


class TripSubmission(BaseModel):
    """Trip submission from driver app"""
    driver_id: str
    route_id: Optional[str] = None
    start_time: datetime
    end_time: datetime
    gps_points: List[GPSPoint]
    vehicle_id: Optional[str] = None


class TripResponse(BaseModel):
    """Response after trip submission"""
    trip_id: str
    status: str
    quality_score: float
    points_earned: int
    driver_total_points: int
    driver_tier: str
    message: str


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.post("/trips", response_model=TripResponse)
async def submit_trip(submission: TripSubmission):
    """
    Submit a completed trip from driver app
    
    This endpoint:
    1. Validates GPS data
    2. Calculates quality score
    3. Awards points to driver
    4. Updates leaderboard
    """
    try:
        # Validate minimum points
        if len(submission.gps_points) < 5:
            raise HTTPException(
                status_code=400, 
                detail="Trip must have at least 5 GPS points"
            )
        
        # Generate trip ID
        trip_id = f"trip_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{submission.driver_id[-4:]}"
        
        # Convert to internal format
        gps_points = [
            (p.latitude, p.longitude, p.timestamp)
            for p in submission.gps_points
        ]
        
        trip_data = TripData(
            trip_id=trip_id,
            driver_id=submission.driver_id,
            start_time=submission.start_time,
            end_time=submission.end_time,
            gps_points=gps_points,
            route_id=submission.route_id
        )
        
        # Process through gamification
        result = gamification_service.process_trip(
            trip=trip_data,
            driver_streak=0,  # TODO: Get from database
            is_new_route=False  # TODO: Check if new route
        )
        
        # Store trip
        trips_db[trip_id] = {
            "trip_id": trip_id,
            "driver_id": submission.driver_id,
            "route_id": submission.route_id,
            "start_time": submission.start_time.isoformat(),
            "end_time": submission.end_time.isoformat(),
            "duration_minutes": (submission.end_time - submission.start_time).total_seconds() / 60,
            "num_points": len(submission.gps_points),
            "quality_score": result['quality']['overall_score'],
            "points_earned": result['points_earned']['total_points'],
            "status": "accepted",
            "created_at": datetime.utcnow().isoformat()
        }
        
        return TripResponse(
            trip_id=trip_id,
            status="accepted",
            quality_score=result['quality']['overall_score'],
            points_earned=result['points_earned']['total_points'],
            driver_total_points=result['driver']['total_points'],
            driver_tier=result['driver']['current_tier'],
            message=f"Trip recorded! You earned {result['points_earned']['total_points']} points."
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trips/{trip_id}")
async def get_trip(trip_id: str):
    """
    Get details of a specific trip
    """
    if trip_id not in trips_db:
        raise HTTPException(status_code=404, detail="Trip not found")
    
    return trips_db[trip_id]


@router.get("/drivers/{driver_id}/trips")
async def get_driver_trips(
    driver_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """
    Get trip history for a driver
    """
    driver_trips = [
        trip for trip in trips_db.values()
        if trip['driver_id'] == driver_id
    ]
    
    # Sort by date descending
    driver_trips.sort(key=lambda x: x['created_at'], reverse=True)
    
    return {
        "trips": driver_trips[offset:offset+limit],
        "total": len(driver_trips),
        "limit": limit,
        "offset": offset
    }


@router.get("/trips")
async def list_trips(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    driver_id: Optional[str] = None
):
    """
    List all trips (with optional driver filter)
    """
    trips = list(trips_db.values())
    
    if driver_id:
        trips = [t for t in trips if t['driver_id'] == driver_id]
    
    # Sort by date descending
    trips.sort(key=lambda x: x['created_at'], reverse=True)
    
    return {
        "trips": trips[offset:offset+limit],
        "total": len(trips),
        "limit": limit,
        "offset": offset
    }
