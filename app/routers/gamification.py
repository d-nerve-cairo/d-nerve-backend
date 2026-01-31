"""
Gamification Router - PostgreSQL
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
from typing import List, Dict, Optional
from datetime import datetime
import uuid
from sqlalchemy.orm import Session

from app.models.database import get_db, Driver, Withdrawal, PointsTransaction

router = APIRouter()


# =============================================================================
# CONFIGURATION
# =============================================================================

TIER_THRESHOLDS = {
    "Bronze": 0,
    "Silver": 500,
    "Gold": 2000,
    "Platinum": 5000,
    "Diamond": 10000
}

REWARD_RATE = 0.1  # 10 points = 1 EGP
MIN_WITHDRAWAL_EGP = 5


# =============================================================================
# SCHEMAS
# =============================================================================

class WithdrawalRequest(BaseModel):
    amount: float
    payment_method: str
    account_number: str


class WithdrawalResponse(BaseModel):
    withdrawal_id: str
    driver_id: str
    amount: float
    payment_method: str
    account_number: str
    status: str
    created_at: str


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def calculate_tier(points: int) -> str:
    if points >= 10000:
        return "Diamond"
    elif points >= 5000:
        return "Platinum"
    elif points >= 2000:
        return "Gold"
    elif points >= 500:
        return "Silver"
    return "Bronze"


def get_tier_benefits(tier: str) -> List[str]:
    benefits = {
        "Bronze": ["Basic rewards", "Standard support"],
        "Silver": ["5% bonus on all points", "Priority support", "Monthly bonus: 50 points"],
        "Gold": ["10% bonus on all points", "Priority support", "Monthly bonus: 100 points", "Exclusive badge"],
        "Platinum": ["15% bonus on all points", "VIP support", "Monthly bonus: 200 points", "Exclusive badge", "Featured on leaderboard"],
        "Diamond": ["20% bonus on all points", "VIP support", "Monthly bonus: 500 points", "Diamond badge", "Featured on leaderboard", "Early access to new features"]
    }
    return benefits.get(tier, [])


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.get("/gamification/leaderboard")
async def get_leaderboard(
    limit: int = Query(10, ge=1, le=100),
    sort_by: str = Query("total_points"),
    db: Session = Depends(get_db)
):
    """Get driver leaderboard"""
    
    if sort_by == "quality_avg":
        drivers = db.query(Driver).order_by(Driver.quality_avg.desc()).limit(limit).all()
    elif sort_by == "trips_completed":
        drivers = db.query(Driver).order_by(Driver.trips_completed.desc()).limit(limit).all()
    else:
        drivers = db.query(Driver).order_by(Driver.total_points.desc()).limit(limit).all()
    
    leaderboard = []
    for rank, driver in enumerate(drivers, 1):
        leaderboard.append({
            "rank": rank,
            "driver_id": driver.driver_id,
            "name": driver.user.name,
            "total_points": driver.total_points,
            "tier": driver.tier,
            "current_tier": driver.tier,
            "trips_completed": driver.trips_completed,
            "quality_avg": round(driver.quality_avg, 2)
        })
    
    return {
        "leaderboard": leaderboard,
        "sort_by": sort_by,
        "total_drivers": len(leaderboard),
        "updated_at": datetime.utcnow().isoformat() + 'Z'
    }


@router.get("/gamification/tiers")
async def get_tier_info(db: Session = Depends(get_db)):
    """Get tier information"""
    
    # Get tier distribution
    distribution = {}
    for tier in TIER_THRESHOLDS.keys():
        distribution[tier] = db.query(Driver).filter(Driver.tier == tier).count()
    
    return {
        "tiers": [
            {
                "name": tier,
                "min_points": points,
                "benefits": get_tier_benefits(tier)
            }
            for tier, points in TIER_THRESHOLDS.items()
        ],
        "distribution": distribution,
        "reward_rate": {
            "points_per_egp": 10,
            "egp_per_point": REWARD_RATE,
            "description": "10 points = 1 EGP"
        },
        "min_withdrawal_egp": MIN_WITHDRAWAL_EGP
    }


@router.get("/gamification/drivers/{driver_id}/score")
async def get_driver_score(driver_id: str, db: Session = Depends(get_db)):
    """Get driver's gamification score"""
    
    driver = db.query(Driver).filter(Driver.driver_id == driver_id).first()
    
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    
    # Calculate rank
    rank = db.query(Driver).filter(Driver.total_points > driver.total_points).count() + 1
    
    # Calculate next tier
    current_points = driver.total_points
    next_tier = None
    
    for tier, threshold in sorted(TIER_THRESHOLDS.items(), key=lambda x: x[1]):
        if threshold > current_points:
            next_tier = {
                "name": tier,
                "points_required": threshold,
                "points_needed": threshold - current_points,
                "progress_percent": round((current_points / threshold) * 100, 1) if threshold > 0 else 100
            }
            break
    
    if not next_tier:
        next_tier = {"name": "Diamond", "points_needed": 0, "progress_percent": 100, "message": "Maximum tier reached!"}
    
    return {
        "driver_id": driver.driver_id,
        "total_points": driver.total_points,
        "current_tier": driver.tier,
        "trips_completed": driver.trips_completed,
        "quality_avg": round(driver.quality_avg, 2),
        "current_streak": driver.current_streak,
        "longest_streak": driver.longest_streak,
        "rank": rank,
        "rewards_earned_egp": round(driver.rewards_earned or 0, 2),
        "rewards_available_egp": round((driver.rewards_earned or 0) - (driver.rewards_withdrawn or 0), 2),
        "next_tier": next_tier
    }


@router.post("/gamification/drivers/{driver_id}/withdraw", response_model=WithdrawalResponse)
async def request_withdrawal(driver_id: str, request: WithdrawalRequest, db: Session = Depends(get_db)):
    """Request a withdrawal"""
    
    driver = db.query(Driver).filter(Driver.driver_id == driver_id).first()
    
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    
    # Calculate available balance
    available_balance = driver.total_points * REWARD_RATE
    
    # Validate
    if request.amount < MIN_WITHDRAWAL_EGP:
        raise HTTPException(status_code=400, detail=f"Minimum withdrawal is {MIN_WITHDRAWAL_EGP} EGP")
    
    if request.amount > available_balance:
        raise HTTPException(status_code=400, detail=f"Insufficient balance. Available: {available_balance:.2f} EGP")
    
    # Calculate points to deduct
    points_to_deduct = int(request.amount / REWARD_RATE)
    
    # Create withdrawal
    withdrawal_id = f"wd_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"
    
    withdrawal = Withdrawal(
        withdrawal_id=withdrawal_id,
        driver_id=driver_id,
        amount=request.amount,
        points_deducted=points_to_deduct,
        payment_method=request.payment_method,
        account_number=request.account_number,
        status="pending"
    )
    
    db.add(withdrawal)
    
    # Deduct points
    driver.total_points -= points_to_deduct
    driver.rewards_withdrawn = (driver.rewards_withdrawn or 0) + request.amount
    driver.tier = calculate_tier(driver.total_points)
    
    # Log transaction
    transaction = PointsTransaction(
        driver_id=driver_id,
        points=-points_to_deduct,
        transaction_type="withdrawn",
        description=f"Withdrawal: {request.amount} EGP via {request.payment_method}",
        reference_type="withdrawal",
        reference_id=withdrawal_id,
        balance_after=driver.total_points
    )
    
    db.add(transaction)
    db.commit()
    db.refresh(withdrawal)
    
    return WithdrawalResponse(
        withdrawal_id=withdrawal.withdrawal_id,
        driver_id=withdrawal.driver_id,
        amount=withdrawal.amount,
        payment_method=withdrawal.payment_method,
        account_number=withdrawal.account_number,
        status=withdrawal.status,
        created_at=withdrawal.created_at.isoformat() + "Z"
    )


@router.get("/gamification/drivers/{driver_id}/withdrawals")
async def get_withdrawal_history(driver_id: str, db: Session = Depends(get_db)):
    """Get withdrawal history"""
    
    driver = db.query(Driver).filter(Driver.driver_id == driver_id).first()
    
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    
    withdrawals = db.query(Withdrawal).filter(Withdrawal.driver_id == driver_id).order_by(Withdrawal.created_at.desc()).all()
    
    return {
        "withdrawals": [
            {
                "withdrawal_id": w.withdrawal_id,
                "amount": w.amount,
                "points_deducted": w.points_deducted,
                "payment_method": w.payment_method,
                "account_number": w.account_number,
                "status": w.status,
                "created_at": w.created_at.isoformat() + "Z" if w.created_at else None
            }
            for w in withdrawals
        ],
        "total": len(withdrawals)
    }


@router.get("/gamification/drivers/{driver_id}/history")
async def get_points_history(
    driver_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """Get points transaction history"""
    
    driver = db.query(Driver).filter(Driver.driver_id == driver_id).first()
    
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    
    total = db.query(PointsTransaction).filter(PointsTransaction.driver_id == driver_id).count()
    transactions = db.query(PointsTransaction).filter(
        PointsTransaction.driver_id == driver_id
    ).order_by(PointsTransaction.created_at.desc()).offset(offset).limit(limit).all()
    
    return {
        "driver_id": driver_id,
        "transactions": [
            {
                "type": t.transaction_type,
                "points": t.points,
                "description": t.description,
                "balance_after": t.balance_after,
                "timestamp": t.created_at.isoformat() + "Z" if t.created_at else None
            }
            for t in transactions
        ],
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.get("/gamification/points-config")
async def get_points_config():
    """Get points configuration"""
    return {
        "base_points": {
            "per_trip": 10,
            "description": "Base points earned per GPS point recorded"
        },
        "quality_multipliers": {
            "excellent": {"threshold": "≥90%", "multiplier": 1.5},
            "good": {"threshold": "≥70%", "multiplier": 1.2},
            "fair": {"threshold": "≥50%", "multiplier": 1.0},
            "poor": {"threshold": "<50%", "multiplier": 0.5}
        },
        "rewards": {
            "rate": "10 points = 1 EGP",
            "min_withdrawal": f"{MIN_WITHDRAWAL_EGP} EGP"
        }
    }