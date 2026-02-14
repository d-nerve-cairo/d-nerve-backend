"""
Admin Router - Route Discovery and System Management
"""

from fastapi import APIRouter, HTTPException, Query, Depends, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from sqlalchemy.orm import Session

from app.models.database import get_db, Route
from app.services.route_discovery import RouteDiscoveryService

router = APIRouter()


# =============================================================================
# SCHEMAS
# =============================================================================

class DiscoveryTriggerRequest(BaseModel):
    """Request to trigger route discovery"""
    days_back: int = Field(30, ge=1, le=365, description="Look at trips from last N days")
    min_trips: int = Field(50, ge=10, le=1000, description="Minimum trips required")
    force: bool = Field(False, description="Force discovery even if minimum not met")


class RouteCreateRequest(BaseModel):
    """Manually create a route"""
    name: str = Field(..., min_length=3, max_length=200)
    origin: str = Field(..., min_length=2, max_length=100)
    destination: str = Field(..., min_length=2, max_length=100)
    origin_lat: float = Field(..., ge=-90, le=90)
    origin_lon: float = Field(..., ge=-180, le=180)
    dest_lat: float = Field(..., ge=-90, le=90)
    dest_lon: float = Field(..., ge=-180, le=180)
    distance_km: float = Field(..., ge=0.1, le=500)
    avg_duration_minutes: float = Field(..., ge=1, le=600)
    fare_egp: float = Field(..., ge=0, le=1000)


# =============================================================================
# ROUTE DISCOVERY ENDPOINTS
# =============================================================================

@router.get("/admin/discovery/stats")
async def get_discovery_stats(db: Session = Depends(get_db)):
    """
    Get statistics about route discovery readiness
    
    Shows:
    - Total trips and GPS coverage
    - Current route count
    - Whether system is ready for discovery
    """
    stats = RouteDiscoveryService.get_discovery_stats(db)
    return stats


@router.post("/admin/discovery/trigger")
async def trigger_route_discovery(
    request: DiscoveryTriggerRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Trigger DBSCAN route discovery
    
    This analyzes recent GPS trajectories and discovers new popular routes.
    Can be run manually or scheduled.
    """
    # Check readiness
    stats = RouteDiscoveryService.get_discovery_stats(db)
    
    if not stats['ready_for_discovery'] and not request.force:
        return {
            "success": False,
            "message": f"Not enough trips. Have {stats['trips_with_gps']}, need {request.min_trips}.",
            "stats": stats,
            "tip": "Set force=true to run anyway, or wait for more trips."
        }
    
    # Run discovery
    result = RouteDiscoveryService.discover_routes(
        db=db,
        days_back=request.days_back,
        min_trips=request.min_trips if not request.force else 1
    )
    
    return result


@router.get("/admin/discovery/preview")
async def preview_discovery(
    days_back: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db)
):
    """
    Preview what routes would be discovered (dry run)
    
    Shows potential clusters without actually creating routes.
    """
    from app.models.database import Trip
    from datetime import timedelta
    import json
    
    cutoff_date = datetime.utcnow() - timedelta(days=days_back)
    
    trips = db.query(Trip).filter(
        Trip.created_at >= cutoff_date,
        Trip.gps_points_count >= RouteDiscoveryService.MIN_GPS_POINTS,
        Trip.gps_points_json.isnot(None)
    ).all()
    
    # Extract start/end locations
    route_pairs = {}
    
    for trip in trips:
        try:
            gps_points = json.loads(trip.gps_points_json)
            if len(gps_points) >= 2:
                start = gps_points[0]
                end = gps_points[-1]
                
                # Find nearest hubs
                start_hub = RouteDiscoveryService.find_nearest_hub(
                    start['latitude'], start['longitude']
                )
                end_hub = RouteDiscoveryService.find_nearest_hub(
                    end['latitude'], end['longitude']
                )
                
                if start_hub and end_hub and start_hub != end_hub:
                    key = f"{start_hub} → {end_hub}"
                    route_pairs[key] = route_pairs.get(key, 0) + 1
        except:
            continue
    
    # Filter by minimum trips
    potential_routes = [
        {"route": k, "trip_count": v, "meets_threshold": v >= RouteDiscoveryService.MIN_SAMPLES}
        for k, v in sorted(route_pairs.items(), key=lambda x: -x[1])
    ]
    
    return {
        "trips_analyzed": len(trips),
        "days_back": days_back,
        "potential_routes": potential_routes,
        "routes_meeting_threshold": sum(1 for r in potential_routes if r['meets_threshold']),
        "min_samples_required": RouteDiscoveryService.MIN_SAMPLES
    }


# =============================================================================
# ROUTE MANAGEMENT ENDPOINTS
# =============================================================================

@router.post("/admin/routes/create")
async def create_route(request: RouteCreateRequest, db: Session = Depends(get_db)):
    """Manually create a new route"""
    
    # Check for duplicates
    existing = db.query(Route).filter(
        Route.origin == request.origin,
        Route.destination == request.destination
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Route already exists: {existing.route_id}"
        )
    
    new_route = Route(
        route_id=f"route_manual_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        name=request.name,
        origin=request.origin,
        destination=request.destination,
        origin_lat=request.origin_lat,
        origin_lon=request.origin_lon,
        dest_lat=request.dest_lat,
        dest_lon=request.dest_lon,
        distance_km=request.distance_km,
        avg_duration_minutes=request.avg_duration_minutes,
        fare_egp=request.fare_egp,
        trip_count=0,
        is_active=True
    )
    
    db.add(new_route)
    db.commit()
    db.refresh(new_route)
    
    return {
        "success": True,
        "route_id": new_route.route_id,
        "message": f"Route created: {request.name}"
    }


@router.put("/admin/routes/{route_id}/toggle")
async def toggle_route(route_id: str, db: Session = Depends(get_db)):
    """Enable or disable a route"""
    
    route = db.query(Route).filter(Route.route_id == route_id).first()
    
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")
    
    route.is_active = not route.is_active
    db.commit()
    
    return {
        "route_id": route_id,
        "is_active": route.is_active,
        "message": f"Route {'enabled' if route.is_active else 'disabled'}"
    }


@router.delete("/admin/routes/{route_id}")
async def delete_route(route_id: str, db: Session = Depends(get_db)):
    """Delete a route"""
    
    route = db.query(Route).filter(Route.route_id == route_id).first()
    
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")
    
    db.delete(route)
    db.commit()
    
    return {
        "success": True,
        "message": f"Route {route_id} deleted"
    }


@router.get("/admin/routes/all")
async def get_all_routes(
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db)
):
    """Get all routes with admin details"""
    
    query = db.query(Route)
    
    if not include_inactive:
        query = query.filter(Route.is_active == True)
    
    routes = query.order_by(Route.trip_count.desc()).all()
    
    return {
        "total": len(routes),
        "routes": [
            {
                "route_id": r.route_id,
                "name": r.name,
                "origin": r.origin,
                "destination": r.destination,
                "distance_km": r.distance_km,
                "avg_duration_minutes": r.avg_duration_minutes,
                "fare_egp": r.fare_egp,
                "trip_count": r.trip_count,
                "is_active": r.is_active,
                "created_at": r.created_at.isoformat() if r.created_at else None
            }
            for r in routes
        ]
    }
