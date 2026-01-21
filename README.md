# Backend Integration Package v2.0

**Updated ML model loader for D-Nerve backend team**

This package provides everything Group 1 (Backend) needs to integrate the ML models into FastAPI.

---

## What's Changed in v2.0

| Component | v1.0 | v2.0 |
|-----------|------|------|
| Best Model | LightGBM | **Linear Regression** |
| MAE | 9.04 min | **3.28 min** |
| R² Score | 0.9513 | **0.865** |
| Features | 13 | **12** |
| Model File | `lightgbm_eta_model.pkl` | **`eta_best_model.pkl`** |
| Coordinates | Beijing only | **Cairo + Beijing** |
| Validation | Synthetic only | **+ Beijing real data** |

---

## Package Contents

```
backend_integration/
├── model_loader.py          → Updated model loader (COPY THIS)
├── README.md                → This file
├── examples/
│   └── example_usage.py     → Usage examples
└── tests/
    └── test_model_loader.py → Unit tests

docs/
├── API_SPECIFICATION.md     → Updated API contract
└── BACKEND_INTEGRATION_GUIDE.md
```

---

## Quick Start (5 Minutes)

### Step 1: Test the Model Loader

```bash
cd C:\Users\LENOVO\Projects\d-nerve-ml-models
conda activate dnervenv

python backend_integration/model_loader.py
```

**Expected output:**
```
======================================================================
D-NERVE MODEL LOADER v2.0 - DEMO
======================================================================

📊 Model Information:
  Model: D-Nerve ETA Predictor v2.0.0
  Type: Linear Regression
  MAE: 3.28 minutes
  R²: 0.865
  
🛣️ Route Discovery Performance:
  F1 Score (Easy): 1.0
  F1 Score (Hard): 0.963
  Beijing Silhouette: 0.902

🏥 Health Check:
  Status: ✓ Healthy
  
🚌 Sample Predictions:
  3 km at 2pm (off-peak): 8.5 minutes
  8 km at 8am (peak): 22.3 minutes
  15 km at 7pm (peak): 38.1 minutes

✅ Demo complete!
```

---

## For Backend Team (Group 1)

### Files to Copy

**From ML repository:**

```
d-nerve-ml-models/
├── backend_integration/model_loader.py  → Copy this
└── outputs/
    ├── eta_prediction/eta_best_model.pkl  → Copy this
    └── cairo_hard_mode/hard_mode_results.pkl  → Optional
```

**To backend repository:**

```
d-nerve-backend/
└── app/
    └── ml/
        ├── model_loader.py  ← Paste here
        └── models/
            ├── eta_best_model.pkl  ← Paste here
            └── hard_mode_results.pkl  ← Optional
```

### Copy Commands (Windows)

```cmd
cd C:\Users\LENOVO\Projects\d-nerve-backend

mkdir app\ml\models

copy ..\d-nerve-ml-models\backend_integration\model_loader.py app\ml\
copy ..\d-nerve-ml-models\outputs\eta_prediction\eta_best_model.pkl app\ml\models\
```

### Update Model Path

After copying, edit `app/ml/model_loader.py` line ~95:

```python
# Change from:
self.eta_model_path = self.model_dir / "eta_prediction" / "eta_best_model.pkl"

# To:
self.eta_model_path = Path(__file__).parent / "models" / "eta_best_model.pkl"
```

---

## FastAPI Integration

### Create Router (app/routers/eta.py)

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from datetime import datetime
from app.ml.model_loader import DNerveModelLoader, ETAPredictionRequest

router = APIRouter(prefix="/api/v1", tags=["ETA"])

model_loader = DNerveModelLoader()


class SimpleETARequest(BaseModel):
    distance_km: float = Field(..., ge=0, le=100)
    hour: int = Field(12, ge=0, le=23)
    is_peak: int = Field(0, ge=0, le=1)


@router.post("/predict-eta/simple")
async def predict_eta(request: SimpleETARequest):
    """Simple ETA prediction"""
    try:
        duration = model_loader.predict_eta_simple(
            distance_km=request.distance_km,
            hour=request.hour,
            is_peak=request.is_peak
        )
        return {
            "predicted_duration_minutes": round(duration, 2),
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/health")
async def health():
    """Health check"""
    return model_loader.health_check()


@router.get("/model-info")
async def model_info():
    """Model information"""
    return model_loader.get_model_info()
```

### Register Router (app/main.py)

```python
from fastapi import FastAPI
from app.routers import eta

app = FastAPI(title="D-Nerve API", version="2.0.0")
app.include_router(eta.router)
```

### Test with cURL

```bash
# Health check
curl http://localhost:8000/api/v1/health

# Simple prediction
curl -X POST http://localhost:8000/api/v1/predict-eta/simple \
  -H "Content-Type: application/json" \
  -d '{"distance_km": 10, "hour": 8, "is_peak": 1}'

# Model info
curl http://localhost:8000/api/v1/model-info
```

---

## API Endpoints Summary

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/predict-eta` | Full ETA prediction (12 features) |
| POST | `/api/v1/predict-eta/simple` | Simple ETA (distance, hour, is_peak) |
| GET | `/api/v1/model-info` | Model metadata and metrics |
| GET | `/api/v1/health` | Health check |

---

## Model Performance

### ETA Prediction

| Metric | Value |
|--------|-------|
| Model | Linear Regression |
| MAE | 3.28 minutes |
| RMSE | 4.74 minutes |
| R² | 0.865 |
| CV MAE | 3.50 ± 0.35 minutes |
| Features | 12 |

### Route Discovery

| Dataset | F1 Score | Notes |
|---------|----------|-------|
| Cairo Easy (15m noise) | 1.000 | Perfect recovery |
| Cairo Hard (30-50m noise) | 0.963 | With overlapping routes |
| Beijing T-Drive (real) | 0.902 (silhouette) | 16 clusters, validates correctly |

---

## Troubleshooting

### Error: "FileNotFoundError: Model not found"

```
Ensure model file exists:
  app/ml/models/eta_best_model.pkl

Check path in model_loader.py matches your structure.
```

### Error: "ModuleNotFoundError: No module named 'sklearn'"

```bash
pip install scikit-learn pandas numpy
```

### Error: Invalid input

```
Check request matches schema:
- distance_km: 0-100 (float)
- hour: 0-23 (int)
- is_peak: 0 or 1 (int)
```

---

## Dependencies

Add to `requirements.txt`:

```
pandas>=1.5.0
numpy>=1.21.0
scikit-learn>=1.0.0
```

---

## Support

- **Issues:** https://github.com/d-nerve-cairo/d-nerve-ml-models/issues
- **Docs:** See `docs/API_SPECIFICATION.md`
- **Contact:** Group 2 - ML Team

---

**Version:** 2.0.0  
**Updated:** January 20, 2026  
**ML Team:** Group 2