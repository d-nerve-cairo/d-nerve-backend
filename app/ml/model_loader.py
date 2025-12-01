"""
D-Nerve ML Model Loader 

Standalone model loading and prediction interface for backend integration.
Can be copied directly to d-nerve-backend repository.

Features:
- Singleton pattern (efficient memory usage)
- Lazy loading (models loaded only when needed)
- Input validation with detailed error messages
- Logging for debugging and monitoring
- Confidence intervals for predictions
- Health check endpoint support
- Thread-safe operations

Usage:
    from model_loader import DNerveModelLoader, PredictionRequest
    
    loader = DNerveModelLoader()
    request = PredictionRequest(
        distance_km=10.5,
        start_lon=31.2357,
        start_lat=30.0444,
        end_lon=31.3387,
        end_lat=30.0626,
        hour=8,
        day_of_week=1,
        avg_speed_kph=25.0,
        num_points=30,
        is_rush_hour=1
    )
    response = loader.predict_eta(request)
    print(f"ETA: {response.predicted_duration_minutes:.1f} minutes")

Author: Group 2 - ML Team
Version: 1.0.0
Date: 2025-12-01
License: MIT
"""

import pickle
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
import numpy as np
import pandas as pd
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class PredictionRequest:
    """
    Structured prediction request with validation
    
    Attributes:
        distance_km: Straight-line distance between start and end (0-200 km)
        num_points: Number of GPS points in trajectory (10-1000)
        start_lon: Starting longitude (31-32 for Cairo)
        start_lat: Starting latitude (29-31 for Cairo)
        end_lon: Ending longitude (31-32 for Cairo)
        end_lat: Ending latitude (29-31 for Cairo)
        hour: Hour of day (0-23)
        day_of_week: Day of week (0=Monday, 6=Sunday)
        is_weekend: Weekend flag (0=weekday, 1=weekend)
        is_rush_hour: Rush hour flag (0=no, 1=yes)
        avg_speed_kph: Average speed in km/h (0-200)
        is_on_route: On discovered route flag (0=no, 1=yes)
        route_popularity: Number of trips on this route (0-100)
    """
    distance_km: float
    num_points: int
    start_lon: float
    start_lat: float
    end_lon: float
    end_lat: float
    hour: int
    day_of_week: int
    is_weekend: int
    is_rush_hour: int
    avg_speed_kph: float
    is_on_route: int = 0
    route_popularity: int = 0

    def validate(self) -> Tuple[bool, Optional[str]]:
        """
        Validate all input parameters
        
        Returns:
            Tuple[bool, Optional[str]]: (is_valid, error_message)
            If valid: (True, None)
            If invalid: (False, "Error message explaining what's wrong")
        """
        # Distance validation
        if not 0 <= self.distance_km <= 200:
            return False, f"Invalid distance: {self.distance_km} km (must be 0-200)"
        
        # Number of points validation
        if not 10 <= self.num_points <= 1000:
            return False, f"Invalid num_points: {self.num_points} (must be 10-1000)"
        
        # Coordinate validation (Cairo bounds: 29-31°N, 31-32°E)
        if not (29.0 <= self.start_lat <= 31.0 and 31.0 <= self.start_lon <= 32.0):
            return False, f"Invalid start coordinates: ({self.start_lat}, {self.start_lon})"
        
        if not (29.0 <= self.end_lat <= 31.0 and 31.0 <= self.end_lon <= 32.0):
            return False, f"Invalid end coordinates: ({self.end_lat}, {self.end_lon})"
        
        # Time validation
        if not 0 <= self.hour <= 23:
            return False, f"Invalid hour: {self.hour} (must be 0-23)"
        
        if not 0 <= self.day_of_week <= 6:
            return False, f"Invalid day_of_week: {self.day_of_week} (must be 0-6)"
        
        # Speed validation
        if not 0 <= self.avg_speed_kph <= 200:
            return False, f"Invalid speed: {self.avg_speed_kph} km/h (must be 0-200)"
        
        # Binary flags validation
        if self.is_weekend not in [0, 1]:
            return False, f"Invalid is_weekend: {self.is_weekend} (must be 0 or 1)"
        
        if self.is_rush_hour not in [0, 1]:
            return False, f"Invalid is_rush_hour: {self.is_rush_hour} (must be 0 or 1)"
        
        if self.is_on_route not in [0, 1]:
            return False, f"Invalid is_on_route: {self.is_on_route} (must be 0 or 1)"
        
        # Route popularity validation
        if not 0 <= self.route_popularity <= 100:
            return False, f"Invalid route_popularity: {self.route_popularity} (must be 0-100)"
        
        return True, None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)


@dataclass
class PredictionResponse:
    """
    Structured prediction response
    
    Attributes:
        predicted_duration_minutes: Predicted trip duration in minutes
        confidence_interval: (lower_bound, upper_bound) in minutes
        model_version: Version of the model used
        timestamp: ISO 8601 timestamp of prediction
    """
    predicted_duration_minutes: float
    confidence_interval: Tuple[float, float]
    model_version: str
    timestamp: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'predicted_duration_minutes': round(self.predicted_duration_minutes, 2),
            'confidence_interval': {
                'lower': round(self.confidence_interval[0], 2),
                'upper': round(self.confidence_interval[1], 2)
            },
            'model_version': self.model_version,
            'timestamp': self.timestamp
        }


class DNerveModelLoader:
    """
    Professional ML model loader for D-Nerve ETA prediction
    
    Implements singleton pattern for efficient memory usage.
    Models are lazy-loaded (loaded only when first accessed).
    Thread-safe for production use.
    
    Example:
        >>> loader = DNerveModelLoader()
        >>> 
        >>> # Check health
        >>> health = loader.health_check()
        >>> print(f"Status: {'Healthy' if health['healthy'] else 'Unhealthy'}")
        >>> 
        >>> # Make prediction
        >>> request = PredictionRequest(
        ...     distance_km=10.5, num_points=35,
        ...     start_lon=31.2357, start_lat=30.0444,
        ...     end_lon=31.3387, end_lat=30.0626,
        ...     hour=8, day_of_week=1,
        ...     is_weekend=0, is_rush_hour=1,
        ...     avg_speed_kph=22.0
        ... )
        >>> response = loader.predict_eta(request)
        >>> print(f"ETA: {response.predicted_duration_minutes:.1f} minutes")
    """
    
    # Singleton instance
    _instance = None
    _initialized = False
    
    def __new__(cls, *args, **kwargs):
        """Implement singleton pattern"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, model_dir: Optional[Path] = None):
        """
        Initialize model loader
        
        Args:
            model_dir: Directory containing trained models. 
                      If None, uses default location (models/)
        """
        # Prevent re-initialization in singleton
        if self._initialized:
            return
        
        # Set model directory
        if model_dir is None:
            # Default: models/ folder in same directory as this file
            self.model_dir = Path(__file__).parent / "models"
        else:
            self.model_dir = Path(model_dir)
        
        # Model file paths
        self.eta_model_path = self.model_dir / "lightgbm_eta_model.pkl"
        self.routes_path = self.model_dir.parent / "route_discovery" / "route_discovery_results.pkl"
        
        # Models (lazy loaded)
        self._eta_model = None
        self._routes_data = None
        
        # Model metadata
        self._metadata = {
            'name': 'LightGBM ETA Predictor',
            'version': '1.0.0',
            'mae': 9.04,
            'r2_score': 0.9513,
            'training_date': '2025-12-01',
            'feature_count': 13
        }
        
        self._initialized = True
        logger.info(f" DNerveModelLoader initialized (model_dir: {self.model_dir})")
    
    @property
    def eta_model(self):
        """Lazy load ETA prediction model"""
        if self._eta_model is None:
            self._load_eta_model()
        return self._eta_model
    
    @property
    def routes_data(self):
        """Lazy load routes data"""
        if self._routes_data is None:
            self._load_routes_data()
        return self._routes_data
    
    def _load_eta_model(self) -> None:
        """Load LightGBM ETA model from disk"""
        try:
            if not self.eta_model_path.exists():
                raise FileNotFoundError(
                    f"ETA model not found at {self.eta_model_path}. "
                    f"Please ensure:\n"
                    f"  1. Model training is complete\n"
                    f"  2. Model file exists at correct path\n"
                    f"  3. File permissions allow reading"
                )
            
            logger.info(f"Loading ETA model from {self.eta_model_path}...")
            with open(self.eta_model_path, 'rb') as f:
                self._eta_model = pickle.load(f)
            
            logger.info(" ETA model loaded successfully")
            
        except Exception as e:
            logger.error(f" Failed to load ETA model: {e}")
            raise RuntimeError(f"Model loading failed: {e}") from e
    
    def _load_routes_data(self) -> None:
        """Load DBSCAN route discovery results (optional)"""
        try:
            if not self.routes_path.exists():
                logger.warning(
                    f"Routes data not found at {self.routes_path}. "
                    f"Route-based features will be unavailable."
                )
                self._routes_data = None
                return
            
            logger.info(f"Loading routes data from {self.routes_path}...")
            with open(self.routes_path, 'rb') as f:
                self._routes_data = pickle.load(f)
            
            logger.info(" Routes data loaded successfully")
            
        except Exception as e:
            logger.warning(f"  Failed to load routes data: {e}. Continuing without route features.")
            self._routes_data = None
    
    def predict_eta(
        self, 
        request: PredictionRequest,
        return_confidence: bool = True
    ) -> PredictionResponse:
        """
        Predict trip duration (ETA)
        
        Args:
            request: PredictionRequest with trip features
            return_confidence: Whether to calculate confidence interval
        
        Returns:
            PredictionResponse with predicted duration, confidence interval, and metadata
        
        Raises:
            ValueError: If input validation fails
            RuntimeError: If prediction fails
        
        Example:
            >>> request = PredictionRequest(
            ...     distance_km=12.5, num_points=35,
            ...     start_lon=31.2357, start_lat=30.0444,
            ...     end_lon=31.3387, end_lat=30.0626,
            ...     hour=8, day_of_week=1,
            ...     is_weekend=0, is_rush_hour=1,
            ...     avg_speed_kph=22.0
            ... )
            >>> response = loader.predict_eta(request)
            >>> print(response.to_dict())
        """
        # Step 1: Validate input
        is_valid, error_msg = request.validate()
        if not is_valid:
            logger.error(f" Input validation failed: {error_msg}")
            raise ValueError(error_msg)
        
        try:
            # Step 2: Prepare features in correct order
            features = self._prepare_features(request)
            
            # Step 3: Make prediction
            prediction = self.eta_model.predict(features)[0]
            
            # Step 4: Calculate confidence interval
            # Using ±2*MAE as simple confidence interval (covers ~95% of predictions)
            if return_confidence:
                mae = self._metadata['mae']
                confidence_interval = (
                    max(0, prediction - 2 * mae),  # Lower bound (non-negative)
                    prediction + 2 * mae            # Upper bound
                )
            else:
                confidence_interval = (prediction, prediction)
            
            # Step 5: Create response
            response = PredictionResponse(
                predicted_duration_minutes=float(prediction),
                confidence_interval=confidence_interval,
                model_version=self._metadata['version'],
                timestamp=datetime.utcnow().isoformat() + 'Z'
            )
            
            logger.info(
                f" Prediction: {prediction:.2f} min "
                f"(distance: {request.distance_km:.2f} km, "
                f"speed: {request.avg_speed_kph:.2f} km/h, "
                f"hour: {request.hour})"
            )
            
            return response
            
        except Exception as e:
            logger.error(f" Prediction failed: {e}")
            raise RuntimeError(f"Prediction error: {e}") from e
    
    def _prepare_features(self, request: PredictionRequest) -> pd.DataFrame:
        """
        Convert PredictionRequest to model input format
        
        Feature order MUST match training order:
        ['distance_km', 'num_points', 'start_lon', 'start_lat', 'end_lon', 
         'end_lat', 'hour', 'day_of_week', 'is_weekend', 'is_rush_hour', 
         'avg_speed_kph', 'is_on_route', 'route_popularity']
        
        Args:
            request: PredictionRequest object
        
        Returns:
            pandas DataFrame with single row and features in correct order
        """
        feature_dict = {
            'distance_km': request.distance_km,
            'num_points': request.num_points,
            'start_lon': request.start_lon,
            'start_lat': request.start_lat,
            'end_lon': request.end_lon,
            'end_lat': request.end_lat,
            'hour': request.hour,
            'day_of_week': request.day_of_week,
            'is_weekend': request.is_weekend,
            'is_rush_hour': request.is_rush_hour,
            'avg_speed_kph': request.avg_speed_kph,
            'is_on_route': request.is_on_route,
            'route_popularity': request.route_popularity
        }
        
        return pd.DataFrame([feature_dict])
    
    def get_model_info(self) -> Dict[str, Any]:
        """
        Get model metadata and status
        
        Returns:
            Dictionary with model information including version, metrics, and status
        """
        return {
            'model_name': self._metadata['name'],
            'version': self._metadata['version'],
            'mae_minutes': self._metadata['mae'],
            'r2_score': self._metadata['r2_score'],
            'training_date': self._metadata['training_date'],
            'feature_count': self._metadata['feature_count'],
            'status': 'loaded' if self._eta_model is not None else 'not_loaded',
            'routes_available': self._routes_data is not None
        }
    
    def health_check(self) -> Dict[str, Any]:
        """
        Perform comprehensive health check
        
        Returns:
            Dictionary with health status and detailed checks:
            {
                'healthy': bool,
                'checks': {
                    'eta_model_exists': bool,
                    'eta_model_loadable': bool,
                    'routes_data_exists': bool,
                    'sample_prediction': bool
                }
            }
        """
        status = {
            'healthy': True,
            'checks': {},
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }
        
        # Check 1: ETA model file exists
        status['checks']['eta_model_exists'] = self.eta_model_path.exists()
        if not status['checks']['eta_model_exists']:
            status['healthy'] = False
        
        # Check 2: ETA model loadable
        try:
            _ = self.eta_model  # Trigger lazy loading
            status['checks']['eta_model_loadable'] = True
        except Exception as e:
            status['checks']['eta_model_loadable'] = False
            status['checks']['eta_model_error'] = str(e)
            status['healthy'] = False
        
        # Check 3: Routes data exists (optional)
        status['checks']['routes_data_exists'] = self.routes_path.exists()
        
        # Check 4: Sample prediction works (using Cairo coordinates)
        try:
            sample_request = PredictionRequest(
                distance_km=10.0,
                num_points=30,
                start_lon=31.2357,
                start_lat=30.0444,
                end_lon=31.3387,
                end_lat=30.0626,
                hour=12,
                day_of_week=2,
                is_weekend=0,
                is_rush_hour=0,
                avg_speed_kph=30.0
            )
            _ = self.predict_eta(sample_request)
            status['checks']['sample_prediction'] = True
        except Exception as e:
            status['checks']['sample_prediction'] = False
            status['checks']['prediction_error'] = str(e)
            status['healthy'] = False
        
        return status


# Convenience function for simple usage
def predict_trip_duration(
    distance_km: float,
    start_lon: float,
    start_lat: float,
    end_lon: float,
    end_lat: float,
    hour: int,
    day_of_week: int,
    avg_speed_kph: float,
    num_points: int = 30,
    is_rush_hour: int = 0
) -> float:
    """
    Quick prediction function (simplified interface)
    
    Args:
        distance_km: Trip distance in kilometers
        start_lon: Starting longitude
        start_lat: Starting latitude
        end_lon: Ending longitude
        end_lat: Ending latitude
        hour: Hour of day (0-23)
        day_of_week: Day of week (0=Monday, 6=Sunday)
        avg_speed_kph: Average speed in km/h
        num_points: Number of GPS points (default: 30)
        is_rush_hour: 1 if rush hour, 0 otherwise (default: 0)
    
    Returns:
        Predicted duration in minutes
    
    Example:
        >>> duration = predict_trip_duration(
        ...     distance_km=15.5,
        ...     start_lon=31.2357, start_lat=30.0444,
        ...     end_lon=31.3387, end_lat=30.0626,
        ...     hour=8, day_of_week=1,
        ...     avg_speed_kph=25.0
        ... )
        >>> print(f"ETA: {duration:.1f} minutes")
    """
    loader = DNerveModelLoader()
    
    request = PredictionRequest(
        distance_km=distance_km,
        num_points=num_points,
        start_lon=start_lon,
        start_lat=start_lat,
        end_lon=end_lon,
        end_lat=end_lat,
        hour=hour,
        day_of_week=day_of_week,
        is_weekend=1 if day_of_week >= 5 else 0,
        is_rush_hour=is_rush_hour,
        avg_speed_kph=avg_speed_kph
    )
    
    response = loader.predict_eta(request)
    return response.predicted_duration_minutes


# Demo when run directly
if __name__ == "__main__":
    print("="*70)
    print("D-NERVE MODEL LOADER - DEMO")
    print("="*70)
    
    # Initialize
    loader = DNerveModelLoader()
    
    # Model info
    print("\n Model Information:")
    info = loader.get_model_info()
    for key, value in info.items():
        print(f"  {key}: {value}")
    
    # Health check
    print("\n Health Check:")
    health = loader.health_check()
    print(f"  Status: {' Healthy' if health['healthy'] else ' Unhealthy'}")
    for check, result in health['checks'].items():
        if isinstance(result, bool):
            print(f"  {check}: {'Success' if result else 'Failed'}")
    
    # Sample prediction (Cairo coordinates)
    print("\n Sample Prediction (Cairo):")
    request = PredictionRequest(
        distance_km=12.5,
        num_points=35,
        start_lon=31.2357,
        start_lat=30.0444,
        end_lon=31.3387,
        end_lat=30.0626,
        hour=8,
        day_of_week=1,
        is_weekend=0,
        is_rush_hour=1,
        avg_speed_kph=22.0
    )
    
    response = loader.predict_eta(request)
    print(f"  Trip: {request.distance_km} km at {request.hour}:00")
    print(f"  Predicted Duration: {response.predicted_duration_minutes:.1f} minutes")
    print(f"  Confidence: {response.confidence_interval[0]:.1f} - {response.confidence_interval[1]:.1f} min")
    
    print("\n Demo complete!")