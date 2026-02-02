"""
D-Nerve Backend API Server - PostgreSQL
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
from app.routers import badges
from app.routers.badges import init_badges

from app.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =============================================================================
# APP INITIALIZATION
# =============================================================================

app = FastAPI(
    title=settings.APP_NAME,
    description="Backend API for D-Nerve Cairo Informal Transit Platform",
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# STARTUP & SHUTDOWN
# =============================================================================

@app.on_event("startup")
async def startup_event():
    """Run on application startup"""
    logger.info(f"🚀 Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    
    # Initialize database
    try:
        from app.models.database import create_tables, SessionLocal, init_sample_routes
        create_tables()
        
        # Initialize sample routes
        db = SessionLocal()
        try:
            init_sample_routes(db)
            init_badges(db)  
            logger.info("✓ Badges initialized")
        finally:
            db.close()
        
        logger.info("✓ Database initialized")
    except Exception as e:
        logger.error(f"✗ Database initialization failed: {e}")
    
    # Load ML models
    try:
        from app.ml.model_loader import DNerveModelLoader
        loader = DNerveModelLoader()
        _ = loader.eta_model
        logger.info("✓ ML models loaded")
    except Exception as e:
        logger.warning(f"⚠ ML models not loaded: {e}")
    
    logger.info("✓ Application started successfully")


@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown"""
    logger.info("👋 Shutting down application")


# =============================================================================
# INCLUDE ROUTERS
# =============================================================================

from app.routers import eta, drivers, trips, routes, gamification

app.include_router(eta.router, prefix="/api/v1", tags=["ETA Prediction"])
app.include_router(routes.router, prefix="/api/v1", tags=["Routes"])
app.include_router(trips.router, prefix="/api/v1", tags=["Trips"])
app.include_router(drivers.router, prefix="/api/v1", tags=["Drivers"])
app.include_router(gamification.router, prefix="/api/v1", tags=["Gamification"])
app.include_router(badges.router, prefix="/api/v1")


# =============================================================================
# ROOT ENDPOINTS
# =============================================================================

@app.get("/", tags=["System"])
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/api/v1/health"
    }


@app.get("/api/v1/health", tags=["System"])
async def health_check():
    from app.models.database import SessionLocal, Driver
    
    # Check database
    db_healthy = False
    try:
        db = SessionLocal()
        db.query(Driver).first()
        db.close()
        db_healthy = True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
    
    # Check ML models
    ml_healthy = False
    try:
        from app.ml.model_loader import DNerveModelLoader
        loader = DNerveModelLoader()
        ml_healthy = loader.health_check().get('healthy', False)
    except:
        pass
    
    return {
        "status": "healthy" if db_healthy else "degraded",
        "components": {
            "api": {"status": "healthy"},
            "database": {"status": "healthy" if db_healthy else "unhealthy"},
            "ml_models": {"status": "healthy" if ml_healthy else "unavailable"}
        },
        "version": settings.APP_VERSION
    }


@app.get("/api/v1/model-info", tags=["System"])
async def get_model_info():
    try:
        from app.ml.model_loader import DNerveModelLoader
        loader = DNerveModelLoader()
        return loader.get_model_info()
    except Exception as e:
        return {"error": str(e), "status": "unavailable"}


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=settings.DEBUG)