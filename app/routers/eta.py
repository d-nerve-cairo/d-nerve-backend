"""
ETA Prediction Router
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Dict
from datetime import datetime

from app.ml.model_loader import DNerveModelLoader, ETAPredictionRequest

router = APIRouter()

# Initialize model loader (singleton)
model_loader = DNerveModelLoader()


# =============================================================================
# SCHEMAS
# =============================================================================

class ETARequestSimple(BaseModel):
    """Simple ETA prediction request"""
    distance_km: float = Field(..., ge=0, le=100, description="Trip distance in km")
    hour: int = Field(12, ge=0, le=23, description="Hour of day")
    is_peak: int = Field(0, ge=0, le=1, description="Peak hour flag")


class ETARequestFull(BaseModel):
    """Full ETA prediction request with all features"""
    distance_km: float = Field(..., ge=0, le=100)
    hour: int = Field(..., ge=0, le=23)
    day_of_week: int = Field(..., ge=0, le=6)
    is_weekend: int = Field(..., ge=0, le=1)
    is_peak: int = Field(..., ge=0, le=1)
    time_period_encoded: int = Field(2, ge=0, le=3)
    route_avg_duration: float = Field(15.0, ge=0)
    route_std_duration: float = Field(3.0, ge=0)
    route_avg_distance: float = Field(5.0, ge=0)
    origin_encoded: int = Field(0, ge=0)
    dest_encoded: int = Field(0, ge=0)
    overlap_group: int = Field(0, ge=0)


class ETAResponse(BaseModel):
    """ETA prediction response"""
    predicted_duration_minutes: float
    confidence_interval: Dict[str, float]
    model_version: str
    timestamp: str


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.post("/predict-eta/simple", response_model=ETAResponse)
async def predict_eta_simple(request: ETARequestSimple):
    """
    Simple ETA prediction with minimal inputs
    
    Only requires distance, hour, and peak flag.
    """
    try:
        duration = model_loader.predict_eta_simple(
            distance_km=request.distance_km,
            hour=request.hour,
            is_peak=request.is_peak
        )
        
        mae = 3.28
        return ETAResponse(
            predicted_duration_minutes=round(duration, 2),
            confidence_interval={
                "lower": round(max(0, duration - 2*mae), 2),
                "upper": round(duration + 2*mae, 2)
            },
            model_version="2.0.0",
            timestamp=datetime.utcnow().isoformat() + 'Z'
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/predict-eta", response_model=ETAResponse)
async def predict_eta_full(request: ETARequestFull):
    """
    Full ETA prediction with all features
    """
    try:
        ml_request = ETAPredictionRequest(
            distance_km=request.distance_km,
            hour=request.hour,
            day_of_week=request.day_of_week,
            is_weekend=request.is_weekend,
            is_peak=request.is_peak,
            time_period_encoded=request.time_period_encoded,
            route_avg_duration=request.route_avg_duration,
            route_std_duration=request.route_std_duration,
            route_avg_distance=request.route_avg_distance,
            origin_encoded=request.origin_encoded,
            dest_encoded=request.dest_encoded,
            overlap_group=request.overlap_group
        )
        
        response = model_loader.predict_eta(ml_request)
        return ETAResponse(
            predicted_duration_minutes=response.predicted_duration_minutes,
            confidence_interval={
                "lower": response.confidence_interval[0],
                "upper": response.confidence_interval[1]
            },
            model_version=response.model_version,
            timestamp=response.timestamp
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
