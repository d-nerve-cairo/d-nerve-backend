"""
Routes Router
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime

router = APIRouter()

# Sample routes data (in production, load from database)
SAMPLE_ROUTES = [
    {
        "route_id": "route_001",
        "name": "Ramses - Tahrir",
        "origin": "Ramses Square",
        "destination": "Tahrir Square",
        "origin_lat": 30.0626,
        "origin_lon": 31.2466,
        "dest_lat": 30.0444,
        "dest_lon": 31.2357,
        "distance_km": 3.5,
        "avg_duration_minutes": 15,
        "fare_egp": 5.0,
        "stops": ["Ramses", "26th July", "Tahrir"],
        "trip_count": 150,
        "is_active": True
    },
    {
        "route_id": "route_002",
        "name": "Giza - Maadi",
        "origin": "Giza Square",
        "destination": "Maadi",
        "origin_lat": 30.0131,
        "origin_lon": 31.2089,
        "dest_lat": 29.9602,
        "dest_lon": 31.2569,
        "distance_km": 12.0,
        "avg_duration_minutes": 35,
        "fare_egp": 10.0,
        "stops": ["Giza", "Dokki", "Garden City", "Maadi"],
        "trip_count": 89,
        "is_active": True
    },
    {
        "route_id": "route_003",
        "name": "Heliopolis - Downtown",
        "origin": "Heliopolis",
        "destination": "Ataba Square",
        "origin_lat": 30.0866,
        "origin_lon": 31.3225,
        "dest_lat": 30.0519,
        "dest_lon": 31.2466,
        "distance_km": 8.5,
        "avg_duration_minutes": 28,
        "fare_egp": 8.0,
        "stops": ["Heliopolis", "Nasr City", "Abbasia", "Ataba"],
        "trip_count": 112,
        "is_active": True
    },
    {
        "route_id": "route_004",
        "name": "6th October - Tahrir",
        "origin": "6th October City",
        "destination": "Tahrir Square",
        "origin_lat": 29.9285,
        "origin_lon": 30.9188,
        "dest_lat": 30.0444,
        "dest_lon": 31.2357,
        "distance_km": 35.0,
        "avg_duration_minutes": 60,
        "fare_egp": 15.0,
        "stops": ["6th October", "Giza", "Dokki", "Tahrir"],
        "trip_count": 67,
        "is_active": True
    },
    {
        "route_id": "route_005",
        "name": "Nasr City - Maadi",
        "origin": "Nasr City",
        "destination": "Maadi",
        "origin_lat": 30.0511,
        "origin_lon": 31.3656,
        "dest_lat": 29.9602,
        "dest_lon": 31.2569,
        "distance_km": 15.0,
        "avg_duration_minutes": 40,
        "fare_egp": 12.0,
        "stops": ["Nasr City", "Abbasia", "Downtown", "Maadi"],
        "trip_count": 95,
        "is_active": True
    }
]

# In-memory routes storage
routes_db: Dict[str, Dict] = {r['route_id']: r for r in SAMPLE_ROUTES}


# =============================================================================
# SCHEMAS
# =============================================================================

class RouteSearchRequest(BaseModel):
    """Search for routes by coordinates"""
    origin_lat: float = Field(..., ge=-90, le=90)
    origin_lon: float = Field(..., ge=-180, le=180)
    dest_lat: float = Field(..., ge=-90, le=90)
    dest_lon: float = Field(..., ge=-180, le=180)
    radius_km: float = Field(2.0, ge=0.1, le=10)


class NearbyRequest(BaseModel):
    """Find routes near a location"""
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    radius_km: float = Field(2.0, ge=0.1, le=10)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in km between two coordinates"""
    import math
    R = 6371
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.get("/routes")
async def get_routes(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    active_only: bool = Query(True)
):
    """
    Get list of discovered microbus routes
    """
    routes = list(routes_db.values())
    
    if active_only:
        routes = [r for r in routes if r.get('is_active', True)]
    
    # Sort by trip count
    routes.sort(key=lambda x: x.get('trip_count', 0), reverse=True)
    
    return {
        "routes": routes[offset:offset+limit],
        "total": len(routes),
        "limit": limit,
        "offset": offset
    }


@router.get("/routes/{route_id}")
async def get_route(route_id: str):
    """
    Get details of a specific route
    """
    if route_id not in routes_db:
        raise HTTPException(status_code=404, detail="Route not found")
    
    route = routes_db[route_id]
    route['last_updated'] = datetime.utcnow().isoformat()
    
    return route


@router.post("/routes/search")
async def search_routes(request: RouteSearchRequest):
    """
    Search for routes near origin and destination
    """
    matching_routes = []
    
    for route in routes_db.values():
        if not route.get('is_active', True):
            continue
        
        # Check origin distance
        origin_dist = haversine_distance(
            request.origin_lat, request.origin_lon,
            route['origin_lat'], route['origin_lon']
        )
        
        # Check destination distance
        dest_dist = haversine_distance(
            request.dest_lat, request.dest_lon,
            route['dest_lat'], route['dest_lon']
        )
        
        if origin_dist <= request.radius_km and dest_dist <= request.radius_km:
            matching_routes.append({
                **route,
                'origin_distance_km': round(origin_dist, 2),
                'dest_distance_km': round(dest_dist, 2)
            })
    
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
    radius_km: float = Query(2.0, ge=0.1, le=10)
):
    """
    Get routes with origins near a location
    """
    nearby_routes = []
    
    for route in routes_db.values():
        if not route.get('is_active', True):
            continue
        
        distance = haversine_distance(lat, lon, route['origin_lat'], route['origin_lon'])
        
        if distance <= radius_km:
            nearby_routes.append({
                **route,
                'distance_km': round(distance, 2)
            })
    
    # Sort by distance
    nearby_routes.sort(key=lambda x: x['distance_km'])
    
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
    radius_km: float = Query(1.0, ge=0.1, le=10)
):
    """
    Get microbus routes near a location (for commuter app)
    """
    return await get_nearby_routes(lat, lon, radius_km)


@router.get("/commuter/route-eta")
async def commuter_route_eta(
    route_id: str = Query(...),
    origin_lat: float = Query(...),
    origin_lon: float = Query(...)
):
    """
    Get ETA for a specific route from current location
    """
    if route_id not in routes_db:
        raise HTTPException(status_code=404, detail="Route not found")
    
    route = routes_db[route_id]
    
    # Calculate walking distance to route origin
    walk_distance = haversine_distance(
        origin_lat, origin_lon,
        route['origin_lat'], route['origin_lon']
    )
    
    # Estimate walking time (5 km/h average)
    walk_time_minutes = (walk_distance / 5) * 60
    
    # Add route duration
    total_eta = walk_time_minutes + route['avg_duration_minutes']
    
    return {
        "route_id": route_id,
        "route_name": route['name'],
        "walk_distance_km": round(walk_distance, 2),
        "walk_time_minutes": round(walk_time_minutes, 1),
        "route_duration_minutes": route['avg_duration_minutes'],
        "total_eta_minutes": round(total_eta, 1),
        "fare_egp": route['fare_egp'],
        "confidence": "medium"
    }
