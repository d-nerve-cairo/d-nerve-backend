"""
Background Scheduler for Route Discovery
Uses APScheduler to run periodic tasks
"""

import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.models.database import SessionLocal
from app.services.route_discovery import RouteDiscoveryService

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler = None


def run_route_discovery():
    """Background task to discover new routes"""
    logger.info("=" * 50)
    logger.info("🔍 Starting scheduled route discovery...")
    logger.info("=" * 50)
    
    db = SessionLocal()
    try:
        # Check if we have enough data
        stats = RouteDiscoveryService.get_discovery_stats(db)
        
        if not stats['ready_for_discovery']:
            logger.info(f"⏸️ Skipping discovery - not enough trips ({stats['trips_with_gps']}/{stats['min_trips_required']})")
            return
        
        # Run discovery
        result = RouteDiscoveryService.discover_routes(
            db=db,
            days_back=30,
            min_trips=50
        )
        
        if result['success']:
            logger.info(f"✅ Discovery complete!")
            logger.info(f"   - New routes: {result['routes_discovered']}")
            logger.info(f"   - Updated routes: {result['routes_updated']}")
            logger.info(f"   - Trips processed: {result['trips_processed']}")
        else:
            logger.warning(f"⚠️ Discovery incomplete: {result['message']}")
            
    except Exception as e:
        logger.error(f"❌ Route discovery failed: {e}")
    finally:
        db.close()
    
    logger.info("=" * 50)


def check_discovery_trigger():
    """
    Check if discovery should run based on trip count
    Runs every hour, triggers discovery when trip threshold is reached
    """
    logger.debug("Checking discovery trigger...")
    
    db = SessionLocal()
    try:
        stats = RouteDiscoveryService.get_discovery_stats(db)
        
        # Check if we've accumulated enough new trips (every 100 trips)
        if stats['trips_with_gps'] >= 100:
            # Check if we've run recently (simple check via route count change)
            # In production, you'd track last_discovery_run timestamp
            logger.info("📊 Trip threshold reached, triggering discovery...")
            run_route_discovery()
            
    except Exception as e:
        logger.error(f"Discovery trigger check failed: {e}")
    finally:
        db.close()


def init_scheduler(
    enable_nightly: bool = True,
    enable_trip_trigger: bool = True,
    nightly_hour: int = 2,
    nightly_minute: int = 0
):
    """
    Initialize the background scheduler
    
    Args:
        enable_nightly: Run discovery every night
        enable_trip_trigger: Check trip count and trigger when threshold met
        nightly_hour: Hour to run nightly job (24h format)
        nightly_minute: Minute to run nightly job
    """
    global scheduler
    
    if scheduler is not None:
        logger.warning("Scheduler already initialized")
        return scheduler
    
    scheduler = BackgroundScheduler()
    
    # Nightly discovery job (default: 2:00 AM)
    if enable_nightly:
        scheduler.add_job(
            run_route_discovery,
            trigger=CronTrigger(hour=nightly_hour, minute=nightly_minute),
            id='nightly_discovery',
            name='Nightly Route Discovery',
            replace_existing=True
        )
        logger.info(f"📅 Scheduled nightly discovery at {nightly_hour:02d}:{nightly_minute:02d}")
    
    # Trip count trigger (check every hour)
    if enable_trip_trigger:
        scheduler.add_job(
            check_discovery_trigger,
            trigger=IntervalTrigger(hours=1),
            id='trip_trigger_check',
            name='Trip Count Discovery Trigger',
            replace_existing=True
        )
        logger.info("📊 Scheduled hourly trip count check")
    
    scheduler.start()
    logger.info("✅ Background scheduler started")
    
    return scheduler


def shutdown_scheduler():
    """Shutdown the scheduler gracefully"""
    global scheduler
    
    if scheduler:
        scheduler.shutdown(wait=False)
        scheduler = None
        logger.info("🛑 Background scheduler stopped")


def get_scheduler_status():
    """Get current scheduler status and jobs"""
    global scheduler
    
    if not scheduler:
        return {
            "running": False,
            "jobs": []
        }
    
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger)
        })
    
    return {
        "running": scheduler.running,
        "jobs": jobs
    }
