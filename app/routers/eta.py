"""
ETA Prediction Router

Provides ML-powered trip duration predictions using LightGBM model.

Endpoints:
- POST /api/v1/predict-eta: Predict trip duration
- GET /api/v1/model-info: Get model metadata
- GET /api/v1/health: ML health check

Author: D-Nerve Backend Team (Group 1)
ML Integration: Group 2 - ML Team
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
import logging

# Import ML model loader
from app.ml.model_loader import DNerveModelLoader, PredictionRequest as MLRequest

# Configure logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(
    prefix="/api/v1",
    tags=["ETA Prediction"]
)

# Initialize model loader (singleton - loads once at startup)
try:
    model_loader = DNerveModelLoader()
    logger.info("ML model loader initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize ML model loader: {e}")
    model_loader = None


# ============================================================
# REQUEST/RESPONSE MODELS
# ============================================================

class ETARequest(BaseModel):
    """ETA prediction request schema"""
    distance_km: float = Field(..., gt=0, le=200, description="Trip distance in km")
    start_lon: float = Field(..., description="Starting longitude")
    start_lat: float = Field(..., description="Starting latitude")
    end_lon: float = Field(..., description="Ending longitude")
    end_lat: float = Field(..., description="Ending latitude")
    hour: int = Field(..., ge=0, le=23, description="Hour of day (0-23)")
    day_of_week: int = Field(..., ge=0, le=6, description="Day of week (0=Monday, 6=Sunday)")
    avg_speed_kph: float = Field(..., gt=0, le=200, description="Expected average speed in km/h")
    num_points: int = Field(30, ge=10, le=1000, description="Number of GPS points")
    is_rush_hour: int = Field(0, ge=0, le=1, description="Rush hour flag (0 or 1)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "distance_km": 12.5,
                "start_lon": 31.2357,
                "start_lat": 30.0444,
                "end_lon": 31.3387,
                "end_lat": 30.0626,
                "hour": 8,
                "day_of_week": 1,
                "avg_speed_kph": 22.0,
                "num_points": 35,
                "is_rush_hour": 1
            }
        }


class ETAResponse(BaseModel):
    """ETA prediction response schema"""
    predicted_duration_minutes: float
    confidence_interval: dict
    model_version: str
    timestamp: str


# ============================================================
# ENDPOINTS
# ============================================================

@router.post(
    "/predict-eta",
    response_model=ETAResponse,
    status_code=status.HTTP_200_OK,
    summary="Predict trip duration",
    description="Predict ETA for a trip using ML model (LightGBM). Returns predicted duration with 95% confidence interval."
)
async def predict_eta(request: ETARequest):
    """
    Predict trip ETA using LightGBM model
    
    **Parameters:**
    - distance_km: Trip distance in kilometers
    - start_lon/lat: Starting coordinates
    - end_lon/lat: Ending coordinates  
    - hour: Hour of day (0-23)
    - day_of_week: 0=Monday, 6=Sunday
    - avg_speed_kph: Expected average speed
    - is_rush_hour: 1 if rush hour, 0 otherwise
    
    **Returns:**
    - predicted_duration_minutes: Predicted trip duration
    - confidence_interval: 95% confidence bounds
    - model_version: ML model version
    - timestamp: Prediction timestamp
    """
    # Check if model loaded
    if model_loader is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ML models not initialized. Please contact support."
        )
    
    try:
        # Convert FastAPI request to ML request
        ml_request = MLRequest(
            distance_km=request.distance_km,
            num_points=request.num_points,
            start_lon=request.start_lon,
            start_lat=request.start_lat,
            end_lon=request.end_lon,
            end_lat=request.end_lat,
            hour=request.hour,
            day_of_week=request.day_of_week,
            is_weekend=1 if request.day_of_week >= 5 else 0,
            is_rush_hour=request.is_rush_hour,
            avg_speed_kph=request.avg_speed_kph
        )
        
        # Get prediction
        response = model_loader.predict_eta(ml_request)
        
        logger.info(
            f"ETA prediction: {response.predicted_duration_minutes:.1f} min "
            f"(dist: {request.distance_km:.1f} km, speed: {request.avg_speed_kph:.1f} km/h)"
        )
        
        # Return JSON response
        return response.to_dict()
        
    except ValueError as e:
        # Validation error (bad input)
        logger.warning(f"Validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid input: {str(e)}"
        )
    except Exception as e:
        # Unexpected error
        logger.error(f"Prediction failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Prediction failed: {str(e)}"
        )


@router.get(
    "/model-info",
    status_code=status.HTTP_200_OK,
    summary="Get model information",
    description="Returns ML model metadata and performance metrics"
)
async def get_model_info():
    """
    Get ML model information
    
    Returns model name, version, accuracy metrics, training date, etc.
    """
    if model_loader is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ML models not initialized"
        )
    
    return model_loader.get_model_info()


@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="ML health check",
    description="Check if ML models are loaded and operational"
)
async def health_check():
    """
    Health check for ML models
    
    Verifies:
    - Model files exist
    - Models can be loaded
    - Sample prediction works
    
    Returns 200 if healthy, 503 if unhealthy.
    """
    if model_loader is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ML models not initialized"
        )
    
    health = model_loader.health_check()
    
    if not health['healthy']:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ML models not healthy. Check logs for details."
        )
    
    return health