"""
Route Matching Service
Matches user-typed text to existing routes for ETA prediction
"""

from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Tuple
import math
import re

from app.models.database import Route


class RouteMatchingService:
    """Service to match custom route inputs to known routes"""
    
    # Common Cairo area aliases
    AREA_ALIASES = {
        # Ramses
        "ramses": ["ramses", "رمسيس", "ramsis", "mahatet masr", "train station"],
        "tahrir": ["tahrir", "التحرير", "tahrer", "midan tahrir"],
        "giza": ["giza", "الجيزة", "gizah", "pyramids area"],
        "maadi": ["maadi", "المعادي", "maady", "maadi degla"],
        "heliopolis": ["heliopolis", "مصر الجديدة", "masr el gedida", "misr el gedida"],
        "nasr city": ["nasr city", "مدينة نصر", "nasr", "madinet nasr"],
        "mohandessin": ["mohandessin", "المهندسين", "mohandiseen", "mohandseen"],
        "dokki": ["dokki", "الدقي", "doki", "doqqi"],
        "shubra": ["shubra", "شبرا", "shoubra", "shobra"],
        "zamalek": ["zamalek", "الزمالك", "zamalak"],
        "downtown": ["downtown", "وسط البلد", "wust el balad", "ataba", "opera"],
        "6th october": ["6th october", "6 october", "السادس من أكتوبر", "october", "6 اكتوبر"],
        "new cairo": ["new cairo", "القاهرة الجديدة", "tagamoa", "التجمع", "rehab", "fifth settlement"],
        "helwan": ["helwan", "حلوان", "heloan"],
        "ain shams": ["ain shams", "عين شمس", "ein shams"],
        "abbassia": ["abbassia", "العباسية", "abbasia", "abasseya"],
        "imbaba": ["imbaba", "إمبابة", "embaba"],
        "dar el salam": ["dar el salam", "دار السلام", "dar alsalam"],
        "zeitoun": ["zeitoun", "الزيتون", "zaytoun", "zaitoun"],
        "ataba": ["ataba", "العتبة", "attaba"],
    }
    
    @classmethod
    def normalize_text(cls, text: str) -> str:
        """Normalize text for matching"""
        if not text:
            return ""
        # Lowercase, remove extra spaces
        text = text.lower().strip()
        text = re.sub(r'\s+', ' ', text)
        return text
    
    @classmethod
    def get_canonical_name(cls, text: str) -> Optional[str]:
        """Get canonical area name from text"""
        normalized = cls.normalize_text(text)
        
        for canonical, aliases in cls.AREA_ALIASES.items():
            for alias in aliases:
                if alias in normalized or normalized in alias:
                    return canonical
        
        return None
    
    @classmethod
    def match_route(
        cls, 
        origin_text: str, 
        dest_text: str, 
        db: Session
    ) -> Dict:
        """
        Match user input to existing route
        
        Returns:
            {
                "matched": bool,
                "route": {...} or None,
                "match_type": "exact" | "partial" | "none",
                "confidence": float 0-1
            }
        """
        origin_normalized = cls.normalize_text(origin_text)
        dest_normalized = cls.normalize_text(dest_text)
        
        # Get canonical names
        origin_canonical = cls.get_canonical_name(origin_text)
        dest_canonical = cls.get_canonical_name(dest_text)
        
        routes = db.query(Route).filter(Route.is_active == True).all()
        
        best_match = None
        best_score = 0
        match_type = "none"
        
        for route in routes:
            route_origin = cls.normalize_text(route.origin)
            route_dest = cls.normalize_text(route.destination)
            route_origin_canonical = cls.get_canonical_name(route.origin)
            route_dest_canonical = cls.get_canonical_name(route.destination)
            
            score = 0
            
            # Exact canonical match (highest priority)
            if origin_canonical and dest_canonical:
                if (origin_canonical == route_origin_canonical and 
                    dest_canonical == route_dest_canonical):
                    score = 1.0
                    match_type = "exact"
            
            # Partial text match
            if score == 0:
                origin_match = (
                    origin_normalized in route_origin or 
                    route_origin in origin_normalized or
                    (origin_canonical and origin_canonical in route_origin)
                )
                dest_match = (
                    dest_normalized in route_dest or 
                    route_dest in dest_normalized or
                    (dest_canonical and dest_canonical in route_dest)
                )
                
                if origin_match and dest_match:
                    score = 0.8
                    match_type = "partial"
                elif origin_match or dest_match:
                    score = 0.4
                    match_type = "partial"
            
            if score > best_score:
                best_score = score
                best_match = route
        
        if best_match and best_score >= 0.4:
            return {
                "matched": True,
                "route": {
                    "route_id": best_match.route_id,
                    "name": best_match.name,
                    "origin": best_match.origin,
                    "destination": best_match.destination,
                    "distance_km": best_match.distance_km,
                    "avg_duration_minutes": best_match.avg_duration_minutes,
                    "fare_egp": best_match.fare_egp,
                },
                "match_type": match_type,
                "confidence": best_score
            }
        
        return {
            "matched": False,
            "route": None,
            "match_type": "none",
            "confidence": 0,
            "suggestion": "No matching route found. Try selecting from popular routes."
        }
    
    @classmethod
    def estimate_distance(
        cls,
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float
    ) -> float:
        """
        Estimate road distance using Haversine formula with road factor
        
        Args:
            origin_lat, origin_lon: Start coordinates
            dest_lat, dest_lon: End coordinates
            
        Returns:
            Estimated road distance in km
        """
        R = 6371  # Earth's radius in km
        
        lat1, lon1 = math.radians(origin_lat), math.radians(origin_lon)
        lat2, lon2 = math.radians(dest_lat), math.radians(dest_lon)
        
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        
        straight_distance = R * c
        
        # Road factor: roads are typically 1.3-1.4x longer than straight line
        road_factor = 1.35
        
        return round(straight_distance * road_factor, 2)
    
    @classmethod
    def find_nearest_hub(
        cls,
        lat: float,
        lon: float,
        db: Session,
        max_distance_km: float = 5.0
    ) -> Optional[Dict]:
        """Find nearest route origin to given coordinates"""
        routes = db.query(Route).filter(Route.is_active == True).all()
        
        nearest = None
        min_distance = float('inf')
        
        seen_origins = set()
        
        for route in routes:
            if route.origin in seen_origins:
                continue
            seen_origins.add(route.origin)
            
            distance = cls.estimate_distance(lat, lon, route.origin_lat, route.origin_lon)
            
            if distance < min_distance and distance <= max_distance_km:
                min_distance = distance
                nearest = {
                    "name": route.origin,
                    "lat": route.origin_lat,
                    "lon": route.origin_lon,
                    "distance_km": distance
                }
        
        return nearest
