"""
D-Nerve ML Model Loader - Backend Version

Model loading and prediction interface for FastAPI backend.

Author: Group 2 - ML Team
Version: 2.0.0
Date: January 2026
"""

import pickle
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
import numpy as np
import pandas as pd
from datetime import datetime

logger = logging.getLogger(__name__)


# =============================================================================
# REQUEST/RESPONSE DATACLASSES
# =============================================================================

@dataclass
class ETAPredictionRequest:
    """ETA prediction request matching trained model features"""
    distance_km: float
    hour: int = 12
    day_of_week: int = 2
    is_weekend: int = 0
    is_peak: int = 0
    time_period_encoded: int = 2
    route_avg_duration: float = 15.0
    route_std_duration: float = 3.0
    route_avg_distance: float = 5.0
    origin_encoded: int = 0
    dest_encoded: int = 0
    overlap_group: int = 0

    def validate(self) -> Tuple[bool, Optional[str]]:
        """Validate all input parameters"""
        if not 0 < self.distance_km <= 100:
            return False, f"Invalid distance: {self.distance_km} km (must be 0-100)"
        if not 0 <= self.hour <= 23:
            return False, f"Invalid hour: {self.hour} (must be 0-23)"
        if not 0 <= self.day_of_week <= 6:
            return False, f"Invalid day_of_week: {self.day_of_week} (must be 0-6)"
        if self.is_weekend not in [0, 1]:
            return False, f"Invalid is_weekend: {self.is_weekend} (must be 0 or 1)"
        if self.is_peak not in [0, 1]:
            return False, f"Invalid is_peak: {self.is_peak} (must be 0 or 1)"
        if not 0 <= self.time_period_encoded <= 3:
            return False, f"Invalid time_period: {self.time_period_encoded} (must be 0-3)"
        if self.route_avg_duration < 0:
            return False, f"Invalid route_avg_duration: {self.route_avg_duration}"
        return True, None

    def to_feature_dict(self) -> Dict[str, Any]:
        """Convert to feature dictionary matching model training order"""
        return {
            'distance_km': self.distance_km,
            'hour': self.hour,
            'day_of_week': self.day_of_week,
            'is_weekend': self.is_weekend,
            'is_peak': self.is_peak,
            'time_period_encoded': self.time_period_encoded,
            'route_avg_duration': self.route_avg_duration,
            'route_std_duration': self.route_std_duration,
            'route_avg_distance': self.route_avg_distance,
            'origin_encoded': self.origin_encoded,
            'dest_encoded': self.dest_encoded,
            'overlap_group': self.overlap_group
        }


@dataclass
class ETAPredictionResponse:
    """ETA prediction response"""
    predicted_duration_minutes: float
    confidence_interval: Tuple[float, float]
    model_version: str
    model_type: str
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            'predicted_duration_minutes': round(self.predicted_duration_minutes, 2),
            'confidence_interval': {
                'lower': round(self.confidence_interval[0], 2),
                'upper': round(self.confidence_interval[1], 2)
            },
            'model_version': self.model_version,
            'model_type': self.model_type,
            'timestamp': self.timestamp
        }


# =============================================================================
# MODEL LOADER CLASS
# =============================================================================

class DNerveModelLoader:
    """
    ML model loader for D-Nerve ETA prediction
    
    Model Performance:
        - ETA Prediction: MAE = 3.28 minutes, R² = 0.865
    """

    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, model_dir: Optional[Path] = None):
        if self._initialized:
            return

        # Set model directory (relative to this file)
        if model_dir is None:
            self.model_dir = Path(__file__).parent / "models"
        else:
            self.model_dir = Path(model_dir)

        self.eta_model_path = self.model_dir / "eta_best_model.pkl"

        # Models (lazy loaded)
        self._eta_model = None
        self._feature_cols = []

        # Model metadata
        self._metadata = {
            'name': 'D-Nerve ETA Predictor',
            'version': '2.0.0',
            'model_type': 'Linear Regression',
            'mae_minutes': 3.28,
            'rmse_minutes': 4.74,
            'r2_score': 0.865,
            'cv_mae': 3.50,
            'cv_std': 0.35,
            'training_date': '2026-01-20',
            'feature_count': 12
        }

        # Route discovery metadata
        self._route_metadata = {
            'algorithm': 'DBSCAN',
            'distance_metric': 'Hausdorff',
            'f1_score_easy': 1.000,
            'f1_score_hard': 0.963,
            'beijing_silhouette': 0.902
        }

        self._initialized = True
        logger.info(f"✓ DNerveModelLoader initialized (model_dir: {self.model_dir})")

    @property
    def eta_model(self):
        """Lazy load ETA prediction model"""
        if self._eta_model is None:
            self._load_eta_model()
        return self._eta_model

    def _load_eta_model(self) -> None:
        """Load ETA model from disk"""
        try:
            if not self.eta_model_path.exists():
                raise FileNotFoundError(
                    f"ETA model not found at {self.eta_model_path}. "
                    f"Please copy eta_best_model.pkl to {self.model_dir}"
                )

            logger.info(f"Loading ETA model from {self.eta_model_path}...")
            with open(self.eta_model_path, 'rb') as f:
                data = pickle.load(f)

            # Handle both dict format and direct model format
            if isinstance(data, dict):
                self._eta_model = data['model']
                self._feature_cols = data.get('feature_cols', [])
                logger.info(f"  Model type: {data.get('model_name', 'Unknown')}")
                logger.info(f"  Features: {len(self._feature_cols)}")
            else:
                self._eta_model = data
                self._feature_cols = []

            logger.info("✓ ETA model loaded successfully")

        except Exception as e:
            logger.error(f"✗ Failed to load ETA model: {e}")
            raise RuntimeError(f"Model loading failed: {e}") from e

    def predict_eta(
        self,
        request: ETAPredictionRequest,
        return_confidence: bool = True
    ) -> ETAPredictionResponse:
        """Predict trip duration (ETA)"""
        is_valid, error_msg = request.validate()
        if not is_valid:
            logger.error(f"✗ Input validation failed: {error_msg}")
            raise ValueError(error_msg)

        try:
            features = pd.DataFrame([request.to_feature_dict()])
            prediction = self.eta_model.predict(features)[0]

            if return_confidence:
                mae = self._metadata['mae_minutes']
                confidence_interval = (
                    max(0, prediction - 2 * mae),
                    prediction + 2 * mae
                )
            else:
                confidence_interval = (prediction, prediction)

            response = ETAPredictionResponse(
                predicted_duration_minutes=float(prediction),
                confidence_interval=confidence_interval,
                model_version=self._metadata['version'],
                model_type=self._metadata['model_type'],
                timestamp=datetime.utcnow().isoformat() + 'Z'
            )

            logger.info(
                f"✓ Prediction: {prediction:.2f} min "
                f"(distance: {request.distance_km:.2f} km, hour: {request.hour})"
            )

            return response

        except Exception as e:
            logger.error(f"✗ Prediction failed: {e}")
            raise RuntimeError(f"Prediction error: {e}") from e

    def predict_eta_simple(
        self,
        distance_km: float,
        hour: int = 12,
        is_peak: int = 0
    ) -> float:
        """Simple ETA prediction with minimal inputs"""
        if 0 <= hour < 6:
            time_period = 0
        elif 6 <= hour < 12:
            time_period = 1
        elif 12 <= hour < 18:
            time_period = 2
        else:
            time_period = 3

        day_of_week = datetime.now().weekday()
        is_weekend = 1 if day_of_week >= 5 else 0

        avg_speed = 20 if is_peak else 30
        route_avg_duration = (distance_km / avg_speed) * 60

        request = ETAPredictionRequest(
            distance_km=distance_km,
            hour=hour,
            day_of_week=day_of_week,
            is_weekend=is_weekend,
            is_peak=is_peak,
            time_period_encoded=time_period,
            route_avg_duration=route_avg_duration,
            route_std_duration=route_avg_duration * 0.2,
            route_avg_distance=distance_km
        )

        response = self.predict_eta(request, return_confidence=False)
        return response.predicted_duration_minutes

    def get_model_info(self) -> Dict[str, Any]:
        """Get model metadata and performance metrics"""
        return {
            'model_name': self._metadata['name'],
            'version': self._metadata['version'],
            'model_type': self._metadata['model_type'],
            'mae_minutes': self._metadata['mae_minutes'],
            'rmse_minutes': self._metadata['rmse_minutes'],
            'r2_score': self._metadata['r2_score'],
            'cv_mae': f"{self._metadata['cv_mae']} ± {self._metadata['cv_std']}",
            'training_date': self._metadata['training_date'],
            'feature_count': self._metadata['feature_count'],
            'status': 'loaded' if self._eta_model is not None else 'not_loaded',
            'route_discovery': {
                'algorithm': self._route_metadata['algorithm'],
                'f1_score_easy': self._route_metadata['f1_score_easy'],
                'f1_score_hard': self._route_metadata['f1_score_hard'],
                'beijing_validation_silhouette': self._route_metadata['beijing_silhouette']
            }
        }

    def health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check"""
        status = {
            'healthy': True,
            'checks': {},
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }

        status['checks']['eta_model_exists'] = self.eta_model_path.exists()
        if not status['checks']['eta_model_exists']:
            status['healthy'] = False

        try:
            _ = self.eta_model
            status['checks']['eta_model_loadable'] = True
        except Exception as e:
            status['checks']['eta_model_loadable'] = False
            status['checks']['eta_model_error'] = str(e)
            status['healthy'] = False

        try:
            result = self.predict_eta_simple(distance_km=5.0, hour=12, is_peak=0)
            status['checks']['sample_prediction'] = True
            status['checks']['sample_result_minutes'] = round(result, 2)
        except Exception as e:
            status['checks']['sample_prediction'] = False
            status['checks']['prediction_error'] = str(e)
            status['healthy'] = False

        return status
