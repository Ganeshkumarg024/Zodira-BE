from datetime import datetime, date, time
from typing import Optional, Dict, List, Any
from pydantic import BaseModel, validator, Field
from enum import Enum

class Gender(str, Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"

class ProfileType(str, Enum):
    SELF = "self"
    FAMILY_MEMBER = "family_member"
    CONSULTATION = "consultation"


class PersonProfile(BaseModel):
    """Person profile model for astrology calculations"""
    id: str
    user_id: str
    name: str
    birth_date: date
    birth_time: time
    birth_place: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    timezone: str = "Asia/Kolkata"
    gender: Gender
    relationship: str = "self" # Renamed from profileType for clarity
    
    # Calculated astrology data
    zodiac_sign: Optional[str] = None
    moon_sign: Optional[str] = None  # Rasi
    nakshatra: Optional[str] = None
    ascendant: Optional[str] = None

    # Metadata
    created_at: datetime
    updated_at: Optional[datetime] = None
    is_active: bool = True

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            date: lambda v: v.isoformat()
        }

class PredictionType(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"
    CAREER = "career"
    HEALTH = "health"
    RELATIONSHIP = "relationship"
    FINANCE = "finance"

class PredictionCreate(BaseModel):
    """Model for creating predictions"""
    profile_id: str
    prediction_type: PredictionType
    prediction_text: str
    confidence_score: Optional[float] = None
    generated_by: str = "chatgpt"  # chatgpt, astrologer, system
    metadata: Optional[Dict[str, Any]] = None

    class Config:
        use_enum_values = True

class Prediction(BaseModel):
    """Model for astrology predictions"""
    id: str
    profile_id: str
    user_id: str
    prediction_type: PredictionType
    prediction_text: str
    confidence_score: Optional[float] = None
    generated_by: str = "chatgpt"
    is_active: bool = True
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
    expires_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        use_enum_values = True
        extra = "ignore"  # Allow extra fields to be ignored

class PredictionResponse(BaseModel):
    """Response model for predictions"""
    id: str
    profile_id: str
    prediction_type: str
    prediction_text: str
    confidence_score: Optional[float] = None
    created_at: datetime
    expires_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

    def dict(self):
        """Backward compatibility method for Pydantic V2"""
        return self.model_dump()

class PartnerProfile(BaseModel):
    """Model for marriage matching partner profiles"""
    id: str
    main_profile_id: str
    user_id: str
    name: str
    birth_date: date
    birth_time: time
    birth_place: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    gender: Gender
    relationship: str = "partner"

    # Calculated astrology data
    zodiac_sign: Optional[str] = None
    moon_sign: Optional[str] = None
    nakshatra: Optional[str] = None
    ascendant: Optional[str] = None

    # Chart data
    astrology_chart: Optional[Dict[str, Any]] = None

    # Metadata
    created_at: datetime
    updated_at: datetime
    is_active: bool = True

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            date: lambda v: v.isoformat()
        }

class MarriageMatch(BaseModel):
    """Model for marriage compatibility analysis"""
    id: str
    main_profile_id: str
    partner_profile_id: str
    user_id: str

    # Compatibility scores
    overall_score: float
    guna_score: int
    mangal_compatibility: str = "neutral"
    mental_compatibility: str = "good"
    physical_compatibility: str = "good"

    # Detailed analysis
    guna_breakdown: Dict[str, int] = {}
    strengths: List[str] = []
    challenges: List[str] = []
    recommendations: List[str] = []

    # Dosha analysis
    dosha_analysis: Dict[str, str] = {}

    # AI-generated insights
    ai_insights: Optional[str] = None
    compatibility_level: str = "unknown"  # excellent, good, average, poor

    # Metadata
    generated_by: str = "system"
    is_active: bool = True
    created_at: datetime
    updated_at: datetime
    expires_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class MarriageMatchResponse(BaseModel):
    """Response model for marriage matching results"""
    id: str
    main_profile_id: str
    partner_profile_id: str
    overall_score: float
    guna_score: int
    compatibility_level: str
    strengths: List[str]
    challenges: List[str]
    recommendations: List[str]
    ai_insights: Optional[str] = None
    created_at: datetime

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class ChartGenerationRequest(BaseModel):
    """Request model for astrology chart generation"""
    profile_id: str
    include_predictions: bool = True
    prediction_types: List[PredictionType] = [PredictionType.DAILY, PredictionType.WEEKLY]

    class Config:
        use_enum_values = True

class ProfileWithChart(BaseModel):
    """Extended profile model with astrology chart and predictions"""
    # Basic profile data
    id: str
    user_id: str
    name: str
    birth_date: date
    birth_time: time
    birth_place: str
    gender: Gender
    relationship: str

    # Astrology calculations
    zodiac_sign: Optional[str] = None
    moon_sign: Optional[str] = None
    nakshatra: Optional[str] = None
    ascendant: Optional[str] = None

    # Chart data
    astrology_chart: Optional[Dict[str, Any]] = None

    # Predictions
    predictions: List[Prediction] = []

    # Marriage matching
    marriage_matches: List[MarriageMatch] = []
    partner_profiles: List[PartnerProfile] = []

    # Metadata
    created_at: datetime
    updated_at: datetime
    is_active: bool = True

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            date: lambda v: v.isoformat()
        }

class ProfileResponse(BaseModel):
    """Response model for profile data"""
    id: str
    userId: str = Field(alias='user_id')  # Frontend expects userId
    name: str
    birth_date: date
    birth_time: time
    birth_place: str
    gender: Gender
    zodiac_sign: Optional[str] = None
    nakshatra: Optional[str] = None
    moon_sign: Optional[str] = None
    createdAt: datetime = Field(alias='created_at')  # Frontend expects createdAt
    updated_at: datetime

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            date: lambda v: v.isoformat()
        }