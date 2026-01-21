"""
Gamification Router
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from datetime import datetime

from app.services.gamification import (
    gamification_service, 
    TIER_THRESHOLDS, 
    REWARD_RATE,
    MIN_WITHDRAWAL,
    DriverTier
)

router = APIRouter()


# =============================================================================
# SCHEMAS
# =============================================================================

class WithdrawalRequest(BaseModel):
    """Withdrawal request"""
    points: int = Field(..., ge=100, description="Points to withdraw (min 100)")
    payment_method: str = Field(..., description="vodafone_cash, orange_money, etc.")
    payment_number: str = Field(..., min_length=10, max_length=20)


class LeaderboardEntry(BaseModel):
    """Single leaderboard entry"""
    rank: int
    driver_id: str
    total_points: int
    current_tier: str
    trips_completed: int
    quality_avg: float


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.get("/gamification/leaderboard")
async def get_leaderboard(
    limit: int = Query(10, ge=1, le=100),
    sort_by: str = Query("total_points")
):
    """
    Get driver leaderboard
    
    Sort options:
    - total_points: Most points (default)
    - quality_avg: Highest quality scores
    - trips_completed: Most trips
    """
    if sort_by not in ['total_points', 'quality_avg', 'trips_completed']:
        sort_by = 'total_points'
    
    leaderboard = gamification_service.get_leaderboard(limit)
    
    return {
        "leaderboard": leaderboard,
        "sort_by": sort_by,
        "total_drivers": len(leaderboard),
        "updated_at": datetime.utcnow().isoformat() + 'Z'
    }


@router.get("/gamification/tiers")
async def get_tier_info():
    """
    Get tier thresholds and distribution
    """
    tier_info = gamification_service.get_tier_info()
    
    return {
        "tiers": [
            {
                "name": tier.value,
                "min_points": points,
                "benefits": get_tier_benefits(tier)
            }
            for tier, points in TIER_THRESHOLDS.items()
        ],
        "distribution": tier_info['distribution'],
        "reward_rate": {
            "points_per_egp": int(1 / REWARD_RATE),
            "egp_per_point": REWARD_RATE,
            "description": f"1 point = {REWARD_RATE} EGP"
        },
        "min_withdrawal_points": MIN_WITHDRAWAL,
        "min_withdrawal_egp": MIN_WITHDRAWAL * REWARD_RATE
    }


@router.get("/gamification/drivers/{driver_id}/score")
async def get_driver_score(driver_id: str):
    """
    Get driver's gamification score and stats
    """
    stats = gamification_service.get_driver_stats(driver_id)
    
    if not stats:
        raise HTTPException(status_code=404, detail="Driver not found")
    
    # Add next tier info
    current_points = stats['total_points']
    next_tier = get_next_tier(current_points)
    
    stats['next_tier'] = next_tier
    
    return stats


@router.post("/gamification/drivers/{driver_id}/withdraw")
async def request_withdrawal(driver_id: str, request: WithdrawalRequest):
    """
    Request points withdrawal
    
    Minimum withdrawal: 100 points (10 EGP)
    """
    result = gamification_service.calculate_withdrawal(driver_id, request.points)
    
    if 'error' in result:
        raise HTTPException(status_code=400, detail=result['error'])
    
    # Add payment info
    result['payment_method'] = request.payment_method
    result['payment_number'] = request.payment_number
    result['requested_at'] = datetime.utcnow().isoformat() + 'Z'
    result['message'] = f"Withdrawal request submitted. {result['amount_egp']} EGP will be sent to {request.payment_number}"
    
    return result


@router.get("/gamification/points-config")
async def get_points_config():
    """
    Get points configuration
    """
    from app.services.gamification import POINTS_CONFIG
    
    return {
        "base_points": {
            "per_trip": POINTS_CONFIG['trip_base'],
            "description": "Base points earned for each completed trip"
        },
        "quality_multipliers": {
            "excellent": {"threshold": "≥90%", "multiplier": POINTS_CONFIG['quality_excellent']},
            "good": {"threshold": "≥70%", "multiplier": POINTS_CONFIG['quality_good']},
            "fair": {"threshold": "≥50%", "multiplier": POINTS_CONFIG['quality_fair']},
            "poor": {"threshold": "<50%", "multiplier": POINTS_CONFIG['quality_poor']}
        },
        "bonuses": {
            "daily_streak": {
                "points": POINTS_CONFIG['daily_streak_bonus'],
                "description": "Per consecutive day of driving"
            },
            "weekly_streak": {
                "points": POINTS_CONFIG['weekly_streak_bonus'],
                "description": "Complete 7 consecutive days"
            },
            "new_route": {
                "points": POINTS_CONFIG['new_route_bonus'],
                "description": "First to discover a new route"
            },
            "peak_hour": {
                "multiplier": POINTS_CONFIG['peak_hour_bonus'],
                "hours": "7-9 AM, 5-7 PM"
            },
            "monthly_active": {
                "points": POINTS_CONFIG['monthly_active_bonus'],
                "requirement": "20+ active days per month"
            }
        },
        "rewards": {
            "rate": f"{REWARD_RATE} EGP per point",
            "min_withdrawal": f"{MIN_WITHDRAWAL} points ({MIN_WITHDRAWAL * REWARD_RATE} EGP)"
        }
    }


@router.get("/gamification/drivers/{driver_id}/history")
async def get_points_history(
    driver_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """
    Get driver's points transaction history
    """
    # In production, fetch from database
    # For now, return placeholder
    return {
        "driver_id": driver_id,
        "transactions": [],
        "total": 0,
        "limit": limit,
        "offset": offset,
        "message": "Points history will be available when database is connected"
    }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_tier_benefits(tier: DriverTier) -> List[str]:
    """Get benefits for a tier"""
    benefits = {
        DriverTier.BRONZE: [
            "Basic rewards",
            "Standard support"
        ],
        DriverTier.SILVER: [
            "5% bonus on all points",
            "Priority support",
            "Monthly bonus: 50 points"
        ],
        DriverTier.GOLD: [
            "10% bonus on all points",
            "Priority support",
            "Monthly bonus: 100 points",
            "Exclusive badge"
        ],
        DriverTier.PLATINUM: [
            "15% bonus on all points",
            "VIP support",
            "Monthly bonus: 200 points",
            "Exclusive badge",
            "Featured on leaderboard"
        ],
        DriverTier.DIAMOND: [
            "20% bonus on all points",
            "VIP support",
            "Monthly bonus: 500 points",
            "Diamond badge",
            "Featured on leaderboard",
            "Early access to new features"
        ]
    }
    return benefits.get(tier, [])


def get_next_tier(current_points: int) -> Optional[Dict]:
    """Get info about next tier"""
    sorted_tiers = sorted(TIER_THRESHOLDS.items(), key=lambda x: x[1])
    
    for tier, threshold in sorted_tiers:
        if threshold > current_points:
            return {
                "name": tier.value,
                "points_required": threshold,
                "points_needed": threshold - current_points,
                "progress_percent": round((current_points / threshold) * 100, 1)
            }
    
    # Already at max tier
    return {
        "name": "Diamond",
        "points_required": TIER_THRESHOLDS[DriverTier.DIAMOND],
        "points_needed": 0,
        "progress_percent": 100,
        "message": "Maximum tier reached!"
    }
