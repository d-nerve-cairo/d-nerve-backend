"""
Routes Router - Reads ML-trained routes from database
Includes route matching for custom routes
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime
from sqlalchemy.orm import Session
import math

from app.models.database import get_db, Route
from app.services.route_matching import RouteMatchingService

router = APIRouter()


# =============================================================================
# SCHEMAS
# =============================================================================

class RouteResponse(BaseModel):
    """Route response matching Android app expectations"""
    route_id: str
    start_name: str          # Android expects 'start_name'
    end_name: str            # Android expects 'end_name'
    estimated_duration: int  # Android expects 'estimated_duration'
    popularity: int          # Based on trip_count
    distance_km: float
    fare_egp: Optional[float] = None

    # NEW: Route coordinates for map display
    origin_lat: Optional[float] = None
    origin_lon: Optional[float] = None
    dest_lat: Optional[float] = None
    dest_lon: Optional[float] = None

    class Config:
        from_attributes = True


class RouteDetailResponse(BaseModel):
    """Detailed route response"""
    route_id: str
    name: str
    origin: str
    destination: str
    origin_lat: float
    origin_lon: float
    dest_lat: float
    dest_lon: float
    distance_km: float
    avg_duration_minutes: float
    fare_egp: float
    stops: Optional[str] = None
    trip_count: int
    is_active: bool

    class Config:
        from_attributes = True


class RouteSearchRequest(BaseModel):
    """Search for routes by coordinates"""
    origin_lat: float = Field(..., ge=-90, le=90)
    origin_lon: float = Field(..., ge=-180, le=180)
    dest_lat: float = Field(..., ge=-90, le=90)
    dest_lon: float = Field(..., ge=-180, le=180)
    radius_km: float = Field(2.0, ge=0.1, le=10)


class RouteMatchRequest(BaseModel):
    """Match custom route text to existing routes"""
    origin_text: str = Field(..., min_length=1, max_length=100)
    dest_text: str = Field(..., min_length=1, max_length=100)


class DistanceEstimateRequest(BaseModel):
    """Estimate distance between coordinates"""
    origin_lat: float = Field(..., ge=-90, le=90)
    origin_lon: float = Field(..., ge=-180, le=180)
    dest_lat: float = Field(..., ge=-90, le=90)
    dest_lon: float = Field(..., ge=-180, le=180)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in km between two coordinates"""
    R = 6371
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))


def route_to_response(route: Route) -> dict:
    """Convert database Route to Android-compatible response"""
    return {
        "route_id": route.route_id,
        "start_name": route.origin,           # Map origin -> start_name
        "end_name": route.destination,        # Map destination -> end_name
        "estimated_duration": int(route.avg_duration_minutes),  # Map avg_duration_minutes -> estimated_duration
        "popularity": route.trip_count,       # Map trip_count -> popularity
        "distance_km": route.distance_km,
        "fare_egp": route.fare_egp,
        # NEW: Route coordinates for map display
        "origin_lat": route.origin_lat,
        "origin_lon": route.origin_lon,
        "dest_lat": route.dest_lat,
        "dest_lon": route.dest_lon
    }


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.get("/routes", response_model=List[RouteResponse])
async def get_routes(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    active_only: bool = Query(True),
    db: Session = Depends(get_db)
):
    """
    Get list of discovered microbus routes from database

    Returns routes in format expected by Android app:
    - start_name (origin)
    - end_name (destination)
    - estimated_duration (avg_duration_minutes)
    - popularity (trip_count)
    - distance_km
    """
    query = db.query(Route)

    if active_only:
        query = query.filter(Route.is_active == True)

    # Sort by trip count (popularity)
    query = query.order_by(Route.trip_count.desc())

    routes = query.offset(offset).limit(limit).all()

    # Convert to Android-compatible format
    return [route_to_response(route) for route in routes]


@router.get("/routes/{route_id}")
async def get_route(route_id: str, db: Session = Depends(get_db)):
    """
    Get details of a specific route
    """
    route = db.query(Route).filter(Route.route_id == route_id).first()

    if not route:
        raise HTTPException(status_code=404, detail="Route not found")

    return {
        "route_id": route.route_id,
        "name": route.name,
        "origin": route.origin,
        "destination": route.destination,
        "origin_lat": route.origin_lat,
        "origin_lon": route.origin_lon,
        "dest_lat": route.dest_lat,
        "dest_lon": route.dest_lon,
        "distance_km": route.distance_km,
        "avg_duration_minutes": route.avg_duration_minutes,
        "fare_egp": route.fare_egp,
        "stops": route.stops,
        "trip_count": route.trip_count,
        "is_active": route.is_active,
        "last_updated": datetime.utcnow().isoformat()
    }


@router.post("/routes/search")
async def search_routes(request: RouteSearchRequest, db: Session = Depends(get_db)):
    """
    Search for routes near origin and destination
    """
    routes = db.query(Route).filter(Route.is_active == True).all()
    matching_routes = []

    for route in routes:
        # Check origin distance
        origin_dist = haversine_distance(
            request.origin_lat, request.origin_lon,
            route.origin_lat, route.origin_lon
        )

        # Check destination distance
        dest_dist = haversine_distance(
            request.dest_lat, request.dest_lon,
            route.dest_lat, route.dest_lon
        )

        if origin_dist <= request.radius_km and dest_dist <= request.radius_km:
            response = route_to_response(route)
            response['origin_distance_km'] = round(origin_dist, 2)
            response['dest_distance_km'] = round(dest_dist, 2)
            matching_routes.append(response)

    # Sort by combined distance
    matching_routes.sort(
        key=lambda x: x['origin_distance_km'] + x['dest_distance_km']
    )

    return {
        "routes": matching_routes,
        "total": len(matching_routes),
        "search_params": {
            "origin": {"lat": request.origin_lat, "lon": request.origin_lon},
            "destination": {"lat": request.dest_lat, "lon": request.dest_lon},
            "radius_km": request.radius_km
        }
    }


@router.get("/routes/nearby")
async def get_nearby_routes(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(2.0, ge=0.1, le=10),
    db: Session = Depends(get_db)
):
    """
    Get routes with origins near a location
    """
    routes = db.query(Route).filter(Route.is_active == True).all()
    nearby_routes = []

    for route in routes:
        distance = haversine_distance(lat, lon, route.origin_lat, route.origin_lon)

        if distance <= radius_km:
            response = route_to_response(route)
            response['distance_from_user_km'] = round(distance, 2)
            nearby_routes.append(response)

    # Sort by distance
    nearby_routes.sort(key=lambda x: x['distance_from_user_km'])

    return {
        "routes": nearby_routes,
        "total": len(nearby_routes),
        "location": {"lat": lat, "lon": lon},
        "radius_km": radius_km
    }


@router.get("/commuter/nearby-routes")
async def commuter_nearby_routes(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(1.0, ge=0.1, le=10),
    db: Session = Depends(get_db)
):
    """
    Get microbus routes near a location (for commuter app)
    """
    return await get_nearby_routes(lat, lon, radius_km, db)


@router.get("/commuter/route-eta")
async def commuter_route_eta(
    route_id: str = Query(...),
    origin_lat: float = Query(...),
    origin_lon: float = Query(...),
    db: Session = Depends(get_db)
):
    """
    Get ETA for a specific route from current location
    """
    route = db.query(Route).filter(Route.route_id == route_id).first()

    if not route:
        raise HTTPException(status_code=404, detail="Route not found")

    # Calculate walking distance to route origin
    walk_distance = haversine_distance(
        origin_lat, origin_lon,
        route.origin_lat, route.origin_lon
    )

    # Estimate walking time (5 km/h average)
    walk_time_minutes = (walk_distance / 5) * 60

    # Add route duration
    total_eta = walk_time_minutes + route.avg_duration_minutes

    return {
        "route_id": route_id,
        "route_name": route.name,
        "walk_distance_km": round(walk_distance, 2),
        "walk_time_minutes": round(walk_time_minutes, 1),
        "route_duration_minutes": route.avg_duration_minutes,
        "total_eta_minutes": round(total_eta, 1),
        "fare_egp": route.fare_egp,
        "confidence": "medium"
    }


# =============================================================================
# ROUTE MATCHING ENDPOINTS (NEW)
# =============================================================================

@router.post("/routes/match")
async def match_route(request: RouteMatchRequest, db: Session = Depends(get_db)):
    """
    Match user-typed route to existing routes
    
    Use this when driver types custom start/end instead of selecting from list.
    Returns matched route with distance for ETA prediction.
    """
    result = RouteMatchingService.match_route(
        origin_text=request.origin_text,
        dest_text=request.dest_text,
        db=db
    )
    
    return result


@router.post("/routes/estimate-distance")
async def estimate_distance(request: DistanceEstimateRequest):
    """
    Estimate road distance between two coordinates
    
    Uses Haversine formula with road factor (1.35x straight line).
    Use this when no matching route found but coordinates are available.
    """
    distance = RouteMatchingService.estimate_distance(
        origin_lat=request.origin_lat,
        origin_lon=request.origin_lon,
        dest_lat=request.dest_lat,
        dest_lon=request.dest_lon
    )
    
    return {
        "distance_km": distance,
        "method": "haversine_with_road_factor",
        "accuracy": "estimated"
    }


@router.get("/routes/nearest-hub")
async def find_nearest_hub(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    max_distance_km: float = Query(5.0, ge=0.1, le=20),
    db: Session = Depends(get_db)
):
    """
    Find nearest transit hub to given coordinates
    
    Useful for suggesting starting points to drivers.
    """
    hub = RouteMatchingService.find_nearest_hub(
        lat=lat,
        lon=lon,
        db=db,
        max_distance_km=max_distance_km
    )
    
    if hub:
        return {
            "found": True,
            "hub": hub
        }
    
    return {
        "found": False,
        "message": f"No hub found within {max_distance_km} km"
    }