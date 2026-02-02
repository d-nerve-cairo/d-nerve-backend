from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from app.models import get_db, Badge, DriverBadge, Driver

router = APIRouter(prefix="/badges", tags=["Badges"])


# Pydantic models
class BadgeResponse(BaseModel):
    badge_id: str
    name: str
    name_ar: Optional[str]
    description: str
    description_ar: Optional[str]
    icon: str
    category: str
    requirement_type: str
    requirement_value: int
    points_reward: int

    class Config:
        from_attributes = True


class DriverBadgeResponse(BaseModel):
    badge_id: str
    name: str
    name_ar: Optional[str]
    description: str
    description_ar: Optional[str]
    icon: str
    category: str
    earned_at: str
    points_reward: int


class BadgeProgressResponse(BaseModel):
    badge_id: str
    name: str
    name_ar: Optional[str]
    description: str
    description_ar: Optional[str]
    icon: str
    category: str
    requirement_type: str
    requirement_value: int
    current_value: int
    progress_percent: float
    is_earned: bool
    earned_at: Optional[str]
    points_reward: int


# Initialize default badges
def init_badges(db: Session):
    """Initialize default badges if they don't exist"""
    default_badges = [
        # Trip milestones
        {"badge_id": "first_trip", "name": "First Trip", "name_ar": "الرحلة الأولى",
         "description": "Complete your first trip", "description_ar": "أكمل رحلتك الأولى",
         "icon": "ic_badge_first_trip", "category": "trips", 
         "requirement_type": "trips_count", "requirement_value": 1, "points_reward": 10},
        
        {"badge_id": "trips_10", "name": "Road Regular", "name_ar": "سائق منتظم",
         "description": "Complete 10 trips", "description_ar": "أكمل 10 رحلات",
         "icon": "ic_badge_trips", "category": "trips",
         "requirement_type": "trips_count", "requirement_value": 10, "points_reward": 25},
        
        {"badge_id": "trips_50", "name": "Road Warrior", "name_ar": "محارب الطريق",
         "description": "Complete 50 trips", "description_ar": "أكمل 50 رحلة",
         "icon": "ic_badge_trips", "category": "trips",
         "requirement_type": "trips_count", "requirement_value": 50, "points_reward": 100},
        
        {"badge_id": "trips_100", "name": "Century Driver", "name_ar": "سائق المئة",
         "description": "Complete 100 trips", "description_ar": "أكمل 100 رحلة",
         "icon": "ic_badge_trips", "category": "trips",
         "requirement_type": "trips_count", "requirement_value": 100, "points_reward": 250},
        
        # Quality badges
        {"badge_id": "quality_champion", "name": "Quality Champion", "name_ar": "بطل الجودة",
         "description": "Maintain 90%+ quality average", "description_ar": "حافظ على متوسط جودة 90%+",
         "icon": "ic_badge_quality", "category": "quality",
         "requirement_type": "quality_avg", "requirement_value": 90, "points_reward": 50},
        
        {"badge_id": "perfect_trip", "name": "Perfect Trip", "name_ar": "رحلة مثالية",
         "description": "Complete a trip with 100% quality", "description_ar": "أكمل رحلة بجودة 100%",
         "icon": "ic_badge_perfect", "category": "quality",
         "requirement_type": "perfect_trips", "requirement_value": 1, "points_reward": 20},
        
        # Streak badges
        {"badge_id": "streak_3", "name": "Getting Started", "name_ar": "بداية موفقة",
         "description": "3-day driving streak", "description_ar": "3 أيام متتالية من القيادة",
         "icon": "ic_badge_streak", "category": "streak",
         "requirement_type": "streak_days", "requirement_value": 3, "points_reward": 15},
        
        {"badge_id": "streak_7", "name": "Week Warrior", "name_ar": "محارب الأسبوع",
         "description": "7-day driving streak", "description_ar": "7 أيام متتالية من القيادة",
         "icon": "ic_badge_streak", "category": "streak",
         "requirement_type": "streak_days", "requirement_value": 7, "points_reward": 50},
        
        {"badge_id": "streak_30", "name": "Monthly Master", "name_ar": "سيد الشهر",
         "description": "30-day driving streak", "description_ar": "30 يوماً متتالياً من القيادة",
         "icon": "ic_badge_streak", "category": "streak",
         "requirement_type": "streak_days", "requirement_value": 30, "points_reward": 200},
        
        # Points badges
        {"badge_id": "points_100", "name": "Point Collector", "name_ar": "جامع النقاط",
         "description": "Earn 100 total points", "description_ar": "اكسب 100 نقطة",
         "icon": "ic_badge_points", "category": "points",
         "requirement_type": "total_points", "requirement_value": 100, "points_reward": 10},
        
        {"badge_id": "points_500", "name": "Point Hunter", "name_ar": "صياد النقاط",
         "description": "Earn 500 total points", "description_ar": "اكسب 500 نقطة",
         "icon": "ic_badge_points", "category": "points",
         "requirement_type": "total_points", "requirement_value": 500, "points_reward": 50},
        
        {"badge_id": "points_1000", "name": "Point Master", "name_ar": "سيد النقاط",
         "description": "Earn 1000 total points", "description_ar": "اكسب 1000 نقطة",
         "icon": "ic_badge_points", "category": "points",
         "requirement_type": "total_points", "requirement_value": 1000, "points_reward": 100},
    ]
    
    for badge_data in default_badges:
        existing = db.query(Badge).filter(Badge.badge_id == badge_data["badge_id"]).first()
        if not existing:
            badge = Badge(**badge_data)
            db.add(badge)
    
    db.commit()


@router.get("", response_model=List[BadgeResponse])
def get_all_badges(db: Session = Depends(get_db)):
    """Get all available badges"""
    badges = db.query(Badge).filter(Badge.is_active == True).all()
    return badges


@router.get("/driver/{driver_id}", response_model=List[DriverBadgeResponse])
def get_driver_badges(driver_id: str, db: Session = Depends(get_db)):
    """Get badges earned by a driver"""
    driver = db.query(Driver).filter(Driver.driver_id == driver_id).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    
    driver_badges = db.query(DriverBadge, Badge).join(
        Badge, DriverBadge.badge_id == Badge.badge_id
    ).filter(DriverBadge.driver_id == driver_id).all()
    
    result = []
    for db_entry, badge in driver_badges:
        result.append({
            "badge_id": badge.badge_id,
            "name": badge.name,
            "name_ar": badge.name_ar,
            "description": badge.description,
            "description_ar": badge.description_ar,
            "icon": badge.icon,
            "category": badge.category,
            "earned_at": db_entry.earned_at.isoformat() if db_entry.earned_at else None,
            "points_reward": badge.points_reward
        })
    
    return result


@router.get("/driver/{driver_id}/progress", response_model=List[BadgeProgressResponse])
def get_driver_badge_progress(driver_id: str, db: Session = Depends(get_db)):
    """Get badge progress for a driver"""
    driver = db.query(Driver).filter(Driver.driver_id == driver_id).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    
    all_badges = db.query(Badge).filter(Badge.is_active == True).all()
    earned_badges = {db.badge_id: db.earned_at for db in 
                     db.query(DriverBadge).filter(DriverBadge.driver_id == driver_id).all()}
    
    result = []
    for badge in all_badges:
        # Calculate current value based on requirement type
        current_value = 0
        if badge.requirement_type == "trips_count":
            current_value = driver.trips_completed
        elif badge.requirement_type == "quality_avg":
            current_value = int(driver.quality_avg * 100) if driver.quality_avg else 0
        elif badge.requirement_type == "streak_days":
            current_value = driver.longest_streak
        elif badge.requirement_type == "total_points":
            current_value = driver.total_points + int(driver.rewards_withdrawn * 10)  # Include withdrawn
        elif badge.requirement_type == "perfect_trips":
            # Count trips with quality >= 0.99
            from app.models import Trip
            current_value = db.query(func.count(Trip.id)).filter(
                Trip.driver_id == driver_id,
                Trip.quality_score >= 0.99
            ).scalar() or 0
        
        progress = min(100, (current_value / badge.requirement_value) * 100) if badge.requirement_value > 0 else 0
        is_earned = badge.badge_id in earned_badges
        
        result.append({
            "badge_id": badge.badge_id,
            "name": badge.name,
            "name_ar": badge.name_ar,
            "description": badge.description,
            "description_ar": badge.description_ar,
            "icon": badge.icon,
            "category": badge.category,
            "requirement_type": badge.requirement_type,
            "requirement_value": badge.requirement_value,
            "current_value": current_value,
            "progress_percent": round(progress, 1),
            "is_earned": is_earned,
            "earned_at": earned_badges.get(badge.badge_id).isoformat() if is_earned and earned_badges.get(badge.badge_id) else None,
            "points_reward": badge.points_reward
        })
    
    return result


@router.post("/driver/{driver_id}/check")
def check_and_award_badges(driver_id: str, db: Session = Depends(get_db)):
    """Check and award any newly earned badges"""
    driver = db.query(Driver).filter(Driver.driver_id == driver_id).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    
    all_badges = db.query(Badge).filter(Badge.is_active == True).all()
    earned_badge_ids = {db.badge_id for db in 
                        db.query(DriverBadge).filter(DriverBadge.driver_id == driver_id).all()}
    
    newly_earned = []
    
    for badge in all_badges:
        if badge.badge_id in earned_badge_ids:
            continue  # Already earned
        
        # Check if requirements are met
        earned = False
        if badge.requirement_type == "trips_count":
            earned = driver.trips_completed >= badge.requirement_value
        elif badge.requirement_type == "quality_avg":
            earned = (driver.quality_avg or 0) * 100 >= badge.requirement_value
        elif badge.requirement_type == "streak_days":
            earned = driver.longest_streak >= badge.requirement_value
        elif badge.requirement_type == "total_points":
            total = driver.total_points + int(driver.rewards_withdrawn * 10)
            earned = total >= badge.requirement_value
        elif badge.requirement_type == "perfect_trips":
            from app.models import Trip
            perfect_count = db.query(func.count(Trip.id)).filter(
                Trip.driver_id == driver_id,
                Trip.quality_score >= 0.99
            ).scalar() or 0
            earned = perfect_count >= badge.requirement_value
        
        if earned:
            # Award badge
            driver_badge = DriverBadge(
                driver_id=driver_id,
                badge_id=badge.badge_id
            )
            db.add(driver_badge)
            
            # Award bonus points
            if badge.points_reward > 0:
                driver.total_points += badge.points_reward
            
            newly_earned.append({
                "badge_id": badge.badge_id,
                "name": badge.name,
                "name_ar": badge.name_ar,
                "points_reward": badge.points_reward
            })
    
    db.commit()
    
    return {
        "newly_earned": newly_earned,
        "total_badges": len(earned_badge_ids) + len(newly_earned)
    }