from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, EmailStr


class User(BaseModel):
    """User model for Firestore"""
    userId: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    displayName: Optional[str] = None
    photoURL: Optional[str] = None
    emailVerified: bool = False
    phoneVerified: bool = False
    subscriptionType: str = "free"
    language: str = "en"
    timezone: str = "Asia/Kolkata"
    createdAt: datetime
    lastLoginAt: Optional[datetime] = None
    isActive: bool = True
    preferences: Optional[Dict[str, Any]] = None
    profileComplete: bool = False
    primaryProfileId: Optional[str] = None
    # Wallet fields
    walletBalance: float = 0.0
    walletCurrency: str = "INR"

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class UserResponse(BaseModel):
    """Response model for user data"""
    id: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    displayName: Optional[str] = None
    subscriptionType: str = "free"
    createdAt: datetime
    profileComplete: bool = False
    hasProfiles: bool = False
    walletBalance: float = 0.0

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
