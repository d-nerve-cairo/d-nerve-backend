"""
D-Nerve Gamification Service
Driver scoring, leaderboards, and incentive calculation
"""

import numpy as np
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from enum import Enum
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

class DriverTier(Enum):
    """Driver tier levels based on total points"""
    BRONZE = "Bronze"
    SILVER = "Silver"
    GOLD = "Gold"
    PLATINUM = "Platinum"
    DIAMOND = "Diamond"


TIER_THRESHOLDS = {
    DriverTier.BRONZE: 0,
    DriverTier.SILVER: 500,
    DriverTier.GOLD: 2000,
    DriverTier.PLATINUM: 5000,
    DriverTier.DIAMOND: 10000
}

POINTS_CONFIG = {
    'trip_base': 10,
    'quality_excellent': 1.5,
    'quality_good': 1.2,
    'quality_fair': 1.0,
    'quality_poor': 0.5,
    'daily_streak_bonus': 5,
    'weekly_streak_bonus': 50,
    'new_route_bonus': 100,
    'peak_hour_bonus': 1.3,
    'off_peak_bonus': 1.1,
    'monthly_active_bonus': 200,
    'referral_bonus': 50,
}

REWARD_RATE = 0.1  # 1 point = 0.1 EGP
MIN_WITHDRAWAL = 100


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class TripData:
    """GPS trip data submitted by driver"""
    trip_id: str
    driver_id: str
    start_time: datetime
    end_time: datetime
    gps_points: List[Tuple[float, float, datetime]]
    route_id: Optional[str] = None

    @property
    def duration_minutes(self) -> float:
        return (self.end_time - self.start_time).total_seconds() / 60

    @property
    def num_points(self) -> int:
        return len(self.gps_points)


@dataclass
class QualityScore:
    """Trip data quality assessment"""
    trip_id: str
    overall_score: float
    completeness: float
    accuracy: float
    consistency: float
    coverage: float
    details: Dict[str, Any] = None

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class DriverScore:
    """Driver's gamification score"""
    driver_id: str
    total_points: int
    current_tier: DriverTier
    trips_completed: int
    quality_avg: float
    current_streak: int
    longest_streak: int
    rank: Optional[int] = None
    rewards_earned: float = 0.0
    rewards_withdrawn: float = 0.0

    @property
    def rewards_available(self) -> float:
        return self.rewards_earned - self.rewards_withdrawn

    def to_dict(self) -> Dict:
        return {
            'driver_id': self.driver_id,
            'total_points': self.total_points,
            'current_tier': self.current_tier.value,
            'trips_completed': self.trips_completed,
            'quality_avg': round(self.quality_avg, 2),
            'current_streak': self.current_streak,
            'longest_streak': self.longest_streak,
            'rank': self.rank,
            'rewards_earned_egp': round(self.rewards_earned, 2),
            'rewards_available_egp': round(self.rewards_available, 2)
        }


@dataclass
class PointsEarned:
    """Points earned from a single trip"""
    trip_id: str
    driver_id: str
    base_points: int
    quality_multiplier: float
    streak_bonus: int
    coverage_bonus: int
    peak_bonus: float
    total_points: int
    breakdown: Dict[str, Any] = None

    def to_dict(self) -> Dict:
        return asdict(self)


# =============================================================================
# DATA QUALITY SCORER
# =============================================================================

class DataQualityScorer:
    """Evaluates the quality of GPS trip data"""

    def __init__(
        self,
        expected_interval_seconds: float = 30,
        min_points: int = 10,
        max_gap_seconds: float = 120,
        cairo_bounds: Dict = None
    ):
        self.expected_interval = expected_interval_seconds
        self.min_points = min_points
        self.max_gap = max_gap_seconds
        self.bounds = cairo_bounds or {
            'lat_min': 29.7,
            'lat_max': 30.3,
            'lon_min': 31.0,
            'lon_max': 31.6
        }

    def score_trip(self, trip: TripData) -> QualityScore:
        """Calculate quality score for a trip"""
        completeness = self._score_completeness(trip)
        accuracy = self._score_accuracy(trip)
        consistency = self._score_consistency(trip)
        coverage = self._score_coverage(trip)

        overall = (completeness + accuracy + consistency + coverage) / 4

        return QualityScore(
            trip_id=trip.trip_id,
            overall_score=round(overall, 2),
            completeness=round(completeness, 2),
            accuracy=round(accuracy, 2),
            consistency=round(consistency, 2),
            coverage=round(coverage, 2),
            details={
                'num_points': trip.num_points,
                'duration_min': round(trip.duration_minutes, 2),
                'expected_points': self._expected_points(trip)
            }
        )

    def _score_completeness(self, trip: TripData) -> float:
        expected = self._expected_points(trip)
        if expected == 0:
            return 0
        ratio = trip.num_points / expected
        return min(100, ratio * 100)

    def _expected_points(self, trip: TripData) -> int:
        duration_seconds = trip.duration_minutes * 60
        return max(self.min_points, int(duration_seconds / self.expected_interval))

    def _score_accuracy(self, trip: TripData) -> float:
        if not trip.gps_points:
            return 0
        valid = sum(1 for lat, lon, _ in trip.gps_points
                   if self.bounds['lat_min'] <= lat <= self.bounds['lat_max']
                   and self.bounds['lon_min'] <= lon <= self.bounds['lon_max'])
        return (valid / len(trip.gps_points)) * 100

    def _score_consistency(self, trip: TripData) -> float:
        if len(trip.gps_points) < 2:
            return 0
        gaps = []
        for i in range(1, len(trip.gps_points)):
            gap = (trip.gps_points[i][2] - trip.gps_points[i-1][2]).total_seconds()
            gaps.append(gap)
        good_gaps = sum(1 for g in gaps if g <= self.max_gap)
        return (good_gaps / len(gaps)) * 100

    def _score_coverage(self, trip: TripData) -> float:
        if len(trip.gps_points) < 2:
            return 0
        total_distance = 0
        for i in range(1, len(trip.gps_points)):
            lat1, lon1, _ = trip.gps_points[i-1]
            lat2, lon2, _ = trip.gps_points[i]
            total_distance += self._haversine(lat1, lon1, lat2, lon2)
        return min(100, (total_distance / 5.0) * 100)

    @staticmethod
    def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        R = 6371
        lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
        dlat, dlon = lat2 - lat1, lon2 - lon1
        a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
        return R * 2 * np.arcsin(np.sqrt(a))


# =============================================================================
# DRIVER SCORER
# =============================================================================

class DriverScorer:
    """Calculates driver scores and points"""

    def __init__(self, quality_scorer: DataQualityScorer = None):
        self.quality_scorer = quality_scorer or DataQualityScorer()
        self.config = POINTS_CONFIG

    def calculate_trip_points(
        self,
        trip: TripData,
        driver_streak: int = 0,
        is_new_route: bool = False
    ) -> PointsEarned:
        """Calculate points earned for a single trip"""
        quality = self.quality_scorer.score_trip(trip)
        base_points = self.config['trip_base']

        # Quality multiplier
        if quality.overall_score >= 90:
            quality_mult = self.config['quality_excellent']
        elif quality.overall_score >= 70:
            quality_mult = self.config['quality_good']
        elif quality.overall_score >= 50:
            quality_mult = self.config['quality_fair']
        else:
            quality_mult = self.config['quality_poor']

        streak_bonus = driver_streak * self.config['daily_streak_bonus']
        coverage_bonus = self.config['new_route_bonus'] if is_new_route else 0

        # Peak hour bonus
        hour = trip.start_time.hour
        if 7 <= hour <= 9 or 17 <= hour <= 19:
            peak_mult = self.config['peak_hour_bonus']
        elif 22 <= hour or hour <= 5:
            peak_mult = self.config['off_peak_bonus']
        else:
            peak_mult = 1.0

        trip_points = int(base_points * quality_mult * peak_mult)
        total_points = trip_points + streak_bonus + coverage_bonus

        return PointsEarned(
            trip_id=trip.trip_id,
            driver_id=trip.driver_id,
            base_points=base_points,
            quality_multiplier=quality_mult,
            streak_bonus=streak_bonus,
            coverage_bonus=coverage_bonus,
            peak_bonus=peak_mult,
            total_points=total_points,
            breakdown={
                'quality_score': quality.overall_score,
                'formula': f"({base_points} × {quality_mult} × {peak_mult}) + {streak_bonus} + {coverage_bonus}"
            }
        )

    def get_tier(self, total_points: int) -> DriverTier:
        tier = DriverTier.BRONZE
        for t, threshold in TIER_THRESHOLDS.items():
            if total_points >= threshold:
                tier = t
        return tier


# =============================================================================
# LEADERBOARD MANAGER
# =============================================================================

class LeaderboardManager:
    """Manages driver rankings and leaderboards"""

    def __init__(self):
        self._drivers: Dict[str, DriverScore] = {}

    def update_driver(self, driver_id: str, points_earned: PointsEarned, quality_score: float):
        if driver_id not in self._drivers:
            self._drivers[driver_id] = DriverScore(
                driver_id=driver_id,
                total_points=0,
                current_tier=DriverTier.BRONZE,
                trips_completed=0,
                quality_avg=0.0,
                current_streak=0,
                longest_streak=0
            )

        driver = self._drivers[driver_id]
        driver.total_points += points_earned.total_points
        driver.trips_completed += 1

        n = driver.trips_completed
        driver.quality_avg = ((driver.quality_avg * (n-1)) + quality_score) / n
        driver.current_tier = DriverScorer().get_tier(driver.total_points)
        driver.rewards_earned = driver.total_points * REWARD_RATE

    def get_leaderboard(self, limit: int = 10, sort_by: str = 'total_points') -> List[DriverScore]:
        drivers = list(self._drivers.values())
        
        if sort_by == 'quality_avg':
            drivers.sort(key=lambda d: d.quality_avg, reverse=True)
        elif sort_by == 'trips_completed':
            drivers.sort(key=lambda d: d.trips_completed, reverse=True)
        else:
            drivers.sort(key=lambda d: d.total_points, reverse=True)

        for i, driver in enumerate(drivers[:limit]):
            driver.rank = i + 1

        return drivers[:limit]

    def get_driver_score(self, driver_id: str) -> Optional[DriverScore]:
        if driver_id in self._drivers:
            driver = self._drivers[driver_id]
            # Calculate rank
            leaderboard = self.get_leaderboard(limit=len(self._drivers))
            for d in leaderboard:
                if d.driver_id == driver_id:
                    driver.rank = d.rank
                    break
            return driver
        return None

    def get_tier_distribution(self) -> Dict[str, int]:
        distribution = {tier.value: 0 for tier in DriverTier}
        for driver in self._drivers.values():
            distribution[driver.current_tier.value] += 1
        return distribution


# =============================================================================
# GAMIFICATION SERVICE
# =============================================================================

class GamificationService:
    """Main service class combining all gamification components"""

    def __init__(self):
        self.quality_scorer = DataQualityScorer()
        self.driver_scorer = DriverScorer(self.quality_scorer)
        self.leaderboard = LeaderboardManager()
        logger.info("✓ GamificationService initialized")

    def process_trip(
        self,
        trip: TripData,
        driver_streak: int = 0,
        is_new_route: bool = False
    ) -> Dict:
        """Process a completed trip and update driver score"""
        quality = self.quality_scorer.score_trip(trip)
        points = self.driver_scorer.calculate_trip_points(trip, driver_streak, is_new_route)
        self.leaderboard.update_driver(trip.driver_id, points, quality.overall_score)
        driver = self.leaderboard.get_driver_score(trip.driver_id)

        return {
            'trip_id': trip.trip_id,
            'quality': quality.to_dict(),
            'points_earned': points.to_dict(),
            'driver': driver.to_dict() if driver else None,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }

    def get_driver_stats(self, driver_id: str) -> Optional[Dict]:
        driver = self.leaderboard.get_driver_score(driver_id)
        return driver.to_dict() if driver else None

    def get_leaderboard(self, limit: int = 10) -> List[Dict]:
        drivers = self.leaderboard.get_leaderboard(limit)
        return [d.to_dict() for d in drivers]

    def get_tier_info(self) -> Dict:
        return {
            'thresholds': {t.value: p for t, p in TIER_THRESHOLDS.items()},
            'distribution': self.leaderboard.get_tier_distribution()
        }

    def calculate_withdrawal(self, driver_id: str, points: int) -> Dict:
        driver = self.leaderboard.get_driver_score(driver_id)
        if not driver:
            return {'error': 'Driver not found'}
        if points < MIN_WITHDRAWAL:
            return {'error': f'Minimum withdrawal is {MIN_WITHDRAWAL} points'}
        if points > driver.total_points:
            return {'error': 'Insufficient points'}

        return {
            'driver_id': driver_id,
            'points_to_withdraw': points,
            'amount_egp': round(points * REWARD_RATE, 2),
            'remaining_points': driver.total_points - points,
            'status': 'pending'
        }


# Global instance
gamification_service = GamificationService()
