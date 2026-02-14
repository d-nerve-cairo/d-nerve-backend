"""
Route Discovery Service
Uses DBSCAN to discover new routes from driver GPS trajectories
"""

import json
import logging
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session
from sklearn.cluster import DBSCAN
from collections import defaultdict

from app.models.database import Route, Trip, SessionLocal

logger = logging.getLogger(__name__)


class RouteDiscoveryService:
    """
    Service to discover new routes from GPS trajectory data using DBSCAN clustering
    """
    
    # DBSCAN Parameters (tuned for Cairo microbus routes)
    EPSILON_METERS = 200  # Maximum distance between points in same cluster
    MIN_SAMPLES = 3       # Minimum trips to form a route
    MIN_GPS_POINTS = 10   # Minimum GPS points per trip
    
    # Cairo hub coordinates for snapping route endpoints
    CAIRO_HUBS = {
        "Ramses Square": (30.0619, 31.2466),
        "Tahrir Square": (30.0444, 31.2357),
        "Giza Square": (30.0131, 31.2089),
        "Ataba Square": (30.0531, 31.2469),
        "Maadi": (29.9602, 31.2569),
        "Heliopolis": (30.0866, 31.3225),
        "Nasr City": (30.0511, 31.3656),
        "Shubra": (30.0986, 31.2422),
        "Mohandessin": (30.0609, 31.2003),
        "Dokki": (30.0392, 31.2125),
        "Ain Shams": (30.1311, 31.3194),
        "Zeitoun": (30.1167, 31.3000),
        "Abbassia": (30.0722, 31.2833),
        "Imbaba": (30.0758, 31.2078),
        "Dar El Salam": (29.9833, 31.2417),
        "6th October City": (29.9389, 30.9167),
        "New Cairo": (30.0300, 31.4700),
        "Helwan": (29.8500, 31.3340),
        "Zamalek": (30.0609, 31.2194),
        "Downtown": (30.0459, 31.2394),
    }
    
    @classmethod
    def haversine_distance(cls, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance in meters between two coordinates"""
        import math
        R = 6371000  # Earth's radius in meters
        
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        
        return R * c
    
    @classmethod
    def find_nearest_hub(cls, lat: float, lon: float, max_distance_m: float = 2000) -> Optional[str]:
        """Find nearest Cairo hub to coordinates"""
        nearest_hub = None
        min_distance = float('inf')
        
        for hub_name, (hub_lat, hub_lon) in cls.CAIRO_HUBS.items():
            distance = cls.haversine_distance(lat, lon, hub_lat, hub_lon)
            if distance < min_distance and distance <= max_distance_m:
                min_distance = distance
                nearest_hub = hub_name
        
        return nearest_hub
    
    @classmethod
    def extract_trajectory_features(cls, gps_points: List[Dict]) -> Optional[Dict]:
        """
        Extract features from GPS trajectory for clustering
        
        Returns:
            {
                "start": (lat, lon),
                "end": (lat, lon),
                "distance_km": float,
                "duration_minutes": float,
                "point_count": int
            }
        """
        if not gps_points or len(gps_points) < cls.MIN_GPS_POINTS:
            return None
        
        # Sort by timestamp
        sorted_points = sorted(gps_points, key=lambda p: p.get('timestamp', ''))
        
        start_point = sorted_points[0]
        end_point = sorted_points[-1]
        
        # Calculate total distance
        total_distance = 0
        for i in range(1, len(sorted_points)):
            p1 = sorted_points[i-1]
            p2 = sorted_points[i]
            total_distance += cls.haversine_distance(
                p1['latitude'], p1['longitude'],
                p2['latitude'], p2['longitude']
            )
        
        return {
            "start": (start_point['latitude'], start_point['longitude']),
            "end": (end_point['latitude'], end_point['longitude']),
            "distance_km": total_distance / 1000,
            "point_count": len(sorted_points)
        }
    
    @classmethod
    def compute_trajectory_similarity(cls, traj1: Dict, traj2: Dict) -> float:
        """
        Compute similarity between two trajectories
        Uses start/end point distances
        
        Returns: Distance score (lower = more similar)
        """
        start_dist = cls.haversine_distance(
            traj1['start'][0], traj1['start'][1],
            traj2['start'][0], traj2['start'][1]
        )
        
        end_dist = cls.haversine_distance(
            traj1['end'][0], traj1['end'][1],
            traj2['end'][0], traj2['end'][1]
        )
        
        return start_dist + end_dist
    
    @classmethod
    def cluster_trajectories(cls, trajectories: List[Dict]) -> Dict[int, List[int]]:
        """
        Cluster trajectories using DBSCAN
        
        Returns: {cluster_id: [trajectory_indices]}
        """
        if len(trajectories) < cls.MIN_SAMPLES:
            logger.warning(f"Not enough trajectories for clustering: {len(trajectories)}")
            return {}
        
        # Build feature matrix (start_lat, start_lon, end_lat, end_lon)
        features = np.array([
            [t['start'][0], t['start'][1], t['end'][0], t['end'][1]]
            for t in trajectories
        ])
        
        # Normalize coordinates for distance calculation
        # Approximate: 1 degree lat ≈ 111 km, 1 degree lon ≈ 85 km (at Cairo latitude)
        features_scaled = features.copy()
        features_scaled[:, [0, 2]] *= 111000  # lat to meters
        features_scaled[:, [1, 3]] *= 85000   # lon to meters
        
        # Run DBSCAN
        clustering = DBSCAN(
            eps=cls.EPSILON_METERS * 2,  # *2 because we sum start+end distances
            min_samples=cls.MIN_SAMPLES,
            metric='euclidean'
        ).fit(features_scaled)
        
        # Group by cluster
        clusters = defaultdict(list)
        for idx, label in enumerate(clustering.labels_):
            if label >= 0:  # Ignore noise (-1)
                clusters[label].append(idx)
        
        logger.info(f"DBSCAN found {len(clusters)} clusters from {len(trajectories)} trajectories")
        return dict(clusters)
    
    @classmethod
    def extract_route_from_cluster(
        cls, 
        trajectories: List[Dict],
        trips: List[Trip]
    ) -> Optional[Dict]:
        """
        Extract route information from a cluster of similar trajectories
        """
        if not trajectories:
            return None
        
        # Average start/end points
        avg_start_lat = np.mean([t['start'][0] for t in trajectories])
        avg_start_lon = np.mean([t['start'][1] for t in trajectories])
        avg_end_lat = np.mean([t['end'][0] for t in trajectories])
        avg_end_lon = np.mean([t['end'][1] for t in trajectories])
        
        # Snap to nearest hubs
        origin_hub = cls.find_nearest_hub(avg_start_lat, avg_start_lon)
        dest_hub = cls.find_nearest_hub(avg_end_lat, avg_end_lon)
        
        if not origin_hub or not dest_hub or origin_hub == dest_hub:
            return None
        
        # Calculate average metrics
        avg_distance = np.mean([t['distance_km'] for t in trajectories])
        avg_duration = np.mean([t.duration_minutes for t in trips if t.duration_minutes])
        
        # Get hub coordinates
        origin_coords = cls.CAIRO_HUBS[origin_hub]
        dest_coords = cls.CAIRO_HUBS[dest_hub]
        
        return {
            "origin": origin_hub,
            "destination": dest_hub,
            "origin_lat": origin_coords[0],
            "origin_lon": origin_coords[1],
            "dest_lat": dest_coords[0],
            "dest_lon": dest_coords[1],
            "distance_km": round(avg_distance, 1),
            "avg_duration_minutes": round(avg_duration, 0) if avg_duration else round(avg_distance * 3, 0),
            "trip_count": len(trajectories)
        }
    
    @classmethod
    def discover_routes(
        cls,
        db: Session,
        days_back: int = 30,
        min_trips: int = 50
    ) -> Dict:
        """
        Main route discovery function
        
        Args:
            db: Database session
            days_back: Look at trips from last N days
            min_trips: Minimum trips required to run discovery
            
        Returns:
            {
                "success": bool,
                "routes_discovered": int,
                "routes_updated": int,
                "trips_processed": int,
                "message": str
            }
        """
        logger.info(f"Starting route discovery (last {days_back} days)")
        
        # Get recent trips with GPS data
        cutoff_date = datetime.utcnow() - timedelta(days=days_back)
        
        trips = db.query(Trip).filter(
            Trip.created_at >= cutoff_date,
            Trip.gps_points_count >= cls.MIN_GPS_POINTS,
            Trip.gps_points_json.isnot(None)
        ).all()
        
        logger.info(f"Found {len(trips)} trips with GPS data")
        
        if len(trips) < min_trips:
            return {
                "success": False,
                "routes_discovered": 0,
                "routes_updated": 0,
                "trips_processed": len(trips),
                "message": f"Not enough trips ({len(trips)}/{min_trips}). Need more data."
            }
        
        # Extract trajectory features
        trajectories = []
        valid_trips = []
        
        for trip in trips:
            try:
                gps_points = json.loads(trip.gps_points_json)
                features = cls.extract_trajectory_features(gps_points)
                if features:
                    trajectories.append(features)
                    valid_trips.append(trip)
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Failed to parse GPS data for trip {trip.trip_id}: {e}")
                continue
        
        logger.info(f"Extracted features from {len(trajectories)} valid trajectories")
        
        if len(trajectories) < cls.MIN_SAMPLES:
            return {
                "success": False,
                "routes_discovered": 0,
                "routes_updated": 0,
                "trips_processed": len(trips),
                "message": f"Not enough valid trajectories ({len(trajectories)})"
            }
        
        # Cluster trajectories
        clusters = cls.cluster_trajectories(trajectories)
        
        if not clusters:
            return {
                "success": False,
                "routes_discovered": 0,
                "routes_updated": 0,
                "trips_processed": len(trips),
                "message": "No clusters found. Trips may be too diverse."
            }
        
        # Extract routes from clusters
        routes_discovered = 0
        routes_updated = 0
        
        for cluster_id, indices in clusters.items():
            cluster_trajectories = [trajectories[i] for i in indices]
            cluster_trips = [valid_trips[i] for i in indices]
            
            route_info = cls.extract_route_from_cluster(cluster_trajectories, cluster_trips)
            
            if route_info:
                # Check if route already exists
                existing = db.query(Route).filter(
                    Route.origin == route_info['origin'],
                    Route.destination == route_info['destination']
                ).first()
                
                if existing:
                    # Update existing route
                    existing.trip_count += route_info['trip_count']
                    existing.avg_duration_minutes = (
                        existing.avg_duration_minutes + route_info['avg_duration_minutes']
                    ) / 2
                    routes_updated += 1
                    logger.info(f"Updated route: {route_info['origin']} → {route_info['destination']}")
                else:
                    # Create new route
                    new_route = Route(
                        route_id=f"route_discovered_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{routes_discovered}",
                        name=f"{route_info['origin']} - {route_info['destination']}",
                        origin=route_info['origin'],
                        destination=route_info['destination'],
                        origin_lat=route_info['origin_lat'],
                        origin_lon=route_info['origin_lon'],
                        dest_lat=route_info['dest_lat'],
                        dest_lon=route_info['dest_lon'],
                        distance_km=route_info['distance_km'],
                        avg_duration_minutes=route_info['avg_duration_minutes'],
                        fare_egp=round(route_info['distance_km'] * 0.5, 0),  # Estimate fare
                        trip_count=route_info['trip_count'],
                        is_active=True
                    )
                    db.add(new_route)
                    routes_discovered += 1
                    logger.info(f"Discovered new route: {route_info['origin']} → {route_info['destination']}")
        
        db.commit()
        
        return {
            "success": True,
            "routes_discovered": routes_discovered,
            "routes_updated": routes_updated,
            "trips_processed": len(trips),
            "clusters_found": len(clusters),
            "message": f"Discovery complete. Found {routes_discovered} new routes, updated {routes_updated} existing."
        }
    
    @classmethod
    def get_discovery_stats(cls, db: Session) -> Dict:
        """Get statistics about route discovery readiness"""
        
        # Count trips with GPS data
        total_trips = db.query(Trip).count()
        trips_with_gps = db.query(Trip).filter(
            Trip.gps_points_count >= cls.MIN_GPS_POINTS
        ).count()
        
        # Count routes
        total_routes = db.query(Route).count()
        active_routes = db.query(Route).filter(Route.is_active == True).count()
        
        # Recent trips (last 7 days)
        week_ago = datetime.utcnow() - timedelta(days=7)
        recent_trips = db.query(Trip).filter(Trip.created_at >= week_ago).count()
        
        return {
            "total_trips": total_trips,
            "trips_with_gps": trips_with_gps,
            "gps_coverage_percent": round(trips_with_gps / total_trips * 100, 1) if total_trips > 0 else 0,
            "recent_trips_7d": recent_trips,
            "total_routes": total_routes,
            "active_routes": active_routes,
            "ready_for_discovery": trips_with_gps >= 50,
            "min_trips_required": 50,
            "dbscan_params": {
                "epsilon_meters": cls.EPSILON_METERS,
                "min_samples": cls.MIN_SAMPLES,
                "min_gps_points": cls.MIN_GPS_POINTS
            }
        }
