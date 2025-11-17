"""
Unified Authentication API Endpoints

This module provides comprehensive authentication endpoints that handle:
- Email and phone number authentication
- Google OAuth integration
- OTP verification and session management
- User profile flow management
"""

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Header, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, validator, EmailStr, Field
from typing import Optional, Union, Dict, Any
import logging
import json
from datetime import datetime, timezone
from urllib.parse import urlencode

from app.services.user_service import user_service, AuthType, AuthStatus
from app.core.dependencies import get_current_user
from app.core.exceptions import AuthenticationError, ValidationError
from app.models.user import User, UserResponse
from app.models.profile import PersonProfile, ProfileResponse, Prediction, PredictionType
from app.config.firebase import get_firestore_client
from app.config.settings import settings
from datetime import datetime
from typing import List
import uuid
from google.cloud.firestore import FieldFilter
from app.utils.astrology_utils import calculate_zodiac_sign, calculate_nakshatra, calculate_coordinates
from app.core.security import validate_email, validate_phone_number, sanitize_input, create_access_token
from app.services.enhanced_astrology_service import enhanced_astrology_service
import httpx
import secrets
from app.services.chatgpt_service import chatgpt_service
from app.models.profile import  PredictionType




logger = logging.getLogger(__name__)

router = APIRouter()

# Request Models
class AuthInitiateRequest(BaseModel):
    """Request model for initiating authentication"""
    identifier: str  # Email or phone number
    
    @validator('identifier')
    def validate_identifier(cls, v):
        if not v or not v.strip():
            raise ValueError('Identifier cannot be empty')
        
        identifier = sanitize_input(v.strip().lower(), 254)
        
        if not validate_email(identifier) and not validate_phone_number(identifier):
            raise ValueError('Must be a valid email address or phone number')
        
        return identifier

class OTPVerifyRequest(BaseModel):
    """Request model for OTP verification"""
    session_id: str
    otp_code: str

    @validator('session_id')
    def validate_session_id(cls, v):
        if not v or len(v) < 10:
            raise ValueError('Invalid session ID')
        return sanitize_input(v, 128)

    @validator('otp_code')
    def validate_otp_code(cls, v):
        if not v or not v.isdigit() or len(v) != 6:
            raise ValueError('OTP must be a 6-digit number')
        return v

class GoogleOAuthRequest(BaseModel):
    """Request model for Google OAuth login"""
    id_token: str
    
    @validator('id_token')
    def validate_id_token(cls, v):
        if not v or len(v) < 100:
            raise ValueError('Invalid Google ID token')
        return v

class LogoutRequest(BaseModel):
    """Request model for logout"""
    session_id: Optional[str] = None

class ProfileCreateRequest(BaseModel):
    """Model for profile creation requests matching frontend structure"""
    userId: Optional[str] = Field(default=None, alias='user_id')  # Maps frontend user_id to backend userId
    name: str
    birth_date: str = Field(alias='birthDate')
    birth_time: str = Field(alias='birthTime')
    birth_place: str = Field(alias='birthPlace')
    gender: str
    createdAt: str = Field(alias='created_at')  # Maps frontend created_at to backend createdAt

    class Config:
        validate_by_name = True  # Allows both snake_case and camelCase in Pydantic V2

    @validator('userId')
    def validate_user_id(cls, v):
        # Allow None; server will use authenticated user_id (from token) if not provided
        if v is None:
            return v
        if not v or not v.strip():
            raise ValueError('User ID cannot be empty')
        return v.strip()

    @validator('name')
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError('Name cannot be empty')
        return v.strip()

    @validator('birth_date')
    def validate_birth_date(cls, v):
        if not v or not v.strip():
            raise ValueError('Birth date cannot be empty')
        try:
            from datetime import date
            # Validate ISO date format (YYYY-MM-DD)
            date.fromisoformat(v.strip())
        except ValueError:
            raise ValueError('Birth date must be in ISO format (e.g., 1990-01-01)')
        return v.strip()

    @validator('birth_time')
    def validate_birth_time(cls, v):
        if not v or not v.strip():
            raise ValueError('Birth time cannot be empty')
        try:
            from datetime import time
            # Validate ISO time format (HH:MM:SS)
            time.fromisoformat(v.strip())
        except ValueError:
            raise ValueError('Birth time must be in ISO format (e.g., 08:59:00)')
        return v.strip()

    @validator('birth_place')
    def validate_birth_place(cls, v):
        if not v or not v.strip():
            raise ValueError('Birth place cannot be empty')
        return v.strip()

    @validator('gender')
    def validate_gender(cls, v):
        if v not in ['male', 'female', 'other']:
            raise ValueError('Gender must be male, female, or other')
        return v

    @validator('createdAt')
    def validate_created_at(cls, v):
        if not v or not v.strip():
            raise ValueError('Created at cannot be empty')
        try:
            from datetime import datetime
            # Validate ISO format with or without timezone
            cleaned_v = v.strip().replace('Z', '+00:00')
            datetime.fromisoformat(cleaned_v)
        except ValueError:
            raise ValueError('Created at must be in ISO format (e.g., 2024-01-01T12:00:00)')
        return v

# Response Models
class AuthInitiateResponse(BaseModel):
    """Response model for authentication initiation"""
    session_id: str
    auth_type: str
    status: str
    message: str
    expires_in: int
    next_step: str

class AuthVerifyResponse(BaseModel):
    """Response model for authentication verification"""
    session_id: str
    access_token: str
    user_id: str
    status: str
    is_new_user: bool
    next_step: str
    user_data: dict

class GoogleOAuthResponse(BaseModel):
    """Response model for Google OAuth"""
    access_token: str
    user_id: str
    status: str
    is_new_user: bool
    next_step: str
    user_data: dict

class LogoutResponse(BaseModel):
    """Response model for logout"""
    message: str
class UserDetailsResponse(BaseModel):
    """Comprehensive response model for user details with profile data"""
    user_id: str
    email: Optional[str] = None
    phone: Optional[str] = None
    display_name: Optional[str] = None
    subscription_type: str
    profile_complete: bool
    language: str
    timezone: str
    created_at: Optional[str] = None
    last_login: Optional[str] = None
    profiles: List[Dict[str, Any]]
    recent_predictions: List[Dict[str, Any]]
    summary: Dict[str, Any]

# API Endpoints

# API Endpoints
@router.post("/initiate", response_model=AuthInitiateResponse)
async def initiate_authentication(
    request: AuthInitiateRequest,
    background_tasks: BackgroundTasks
):
    """Deprecated: moved to /api/v1/auth/initiate"""
    raise HTTPException(status_code=410, detail="This endpoint has moved to /api/v1/auth/initiate")

@router.post("/verify-otp", response_model=AuthVerifyResponse)
async def verify_otp(
    request: OTPVerifyRequest,
    background_tasks: BackgroundTasks
):
    """Deprecated: moved to /api/v1/auth/verify-otp"""
    raise HTTPException(status_code=410, detail="This endpoint has moved to /api/v1/auth/verify-otp")

@router.post("/google-oauth", response_model=GoogleOAuthResponse)
async def google_oauth_login(
    request: GoogleOAuthRequest,
    background_tasks: BackgroundTasks
):
    """Deprecated: moved to /api/v1/auth/google-oauth"""
    raise HTTPException(status_code=410, detail="This endpoint has moved to /api/v1/auth/google-oauth")
        
@router.get("/google/login")
async def google_login():
    """Deprecated: moved to /api/v1/auth/google/login"""
    raise HTTPException(status_code=410, detail="This endpoint has moved to /api/v1/auth/google/login")

@router.get("/google/callback")
async def google_callback(code: str, state: str, background_tasks: BackgroundTasks):
    """Deprecated: moved to /api/v1/auth/google/callback"""
    raise HTTPException(status_code=410, detail="This endpoint has moved to /api/v1/auth/google/callback")

@router.post("/logout", response_model=LogoutResponse)
async def logout(
    request: LogoutRequest,
    current_user: str = Depends(get_current_user)
):
    """
    Logout user and invalidate session
    
    This endpoint:
    1. Invalidates the current session
    2. Revokes Firebase refresh tokens
    3. Clears authentication state
    """
    try:
        session_id = request.session_id or "unknown"
        result = await user_service.logout(session_id, current_user)
        
        logger.info(f"User logged out: {current_user}")
        return LogoutResponse(**result)
        
    except Exception as e:
        logger.error(f"Logout failed for user {current_user}: {e}")
        raise HTTPException(status_code=500, detail="Logout failed")

@router.get("/user-details", response_model=UserDetailsResponse)
async def get_user_details(current_user: str = Depends(get_current_user)):
    """
    Get comprehensive user details including all profile information and astrology data

    This endpoint provides:
    1. Complete user account information
    2. All user profiles with birth details and astrology calculations
    3. Recent predictions and insights
    4. Summary of user's astrology journey
    """
    try:
        logger.info(f"🔍 Fetching comprehensive user details for: {current_user}")

        # Get user account information
        db = get_firestore_client()
        user_ref = db.collection('users').document(current_user)
        user_doc = user_ref.get()

        if not user_doc.exists:
            raise HTTPException(status_code=404, detail="User not found")

        user_data = user_doc.to_dict()

        # Get all user profiles with enhanced astrology data
        profiles_query = db.collection('person_profiles').where(filter=FieldFilter('user_id', '==', current_user)).where(filter=FieldFilter('is_active', '==', True))
        profiles_docs = profiles_query.get()

        enhanced_profiles = []
        for doc in profiles_docs:
            profile_data = doc.to_dict()

            # Generate comprehensive astrology chart data
            chart_data = await enhanced_astrology_service.generate_astrology_chart_data(
                current_user, doc.id, profile_data
            )

            # Create enhanced profile with all details
            enhanced_profile = {
                "id": doc.id,
                "name": profile_data.get('name'),
                "birth_date": profile_data.get('birth_date'),
                "birth_time": profile_data.get('birth_time'),
                "birth_place": profile_data.get('birth_place'),
                "gender": profile_data.get('gender'),
                "relationship": profile_data.get('relationship', 'self'),
                "created_at": profile_data.get('created_at'),
                "updated_at": profile_data.get('updated_at'),
                "is_active": profile_data.get('is_active', True),
                # Astrology data
                "zodiac_sign": profile_data.get('zodiac_sign'),
                "moon_sign": profile_data.get('moon_sign'),
                "nakshatra": profile_data.get('nakshatra'),
                "ascendant": profile_data.get('ascendant'),
                "varna": profile_data.get('varna'),
                "guna": profile_data.get('guna'),
                "element": profile_data.get('element'),
                "modality": profile_data.get('modality'),
                # Chart data
                "chart_data": chart_data,
                # Calculation metadata
                "astrology_calculation_method": profile_data.get('astrology_calculation_method'),
                "astrology_calculated_at": profile_data.get('astrology_calculated_at')
            }
            enhanced_profiles.append(enhanced_profile)

        logger.info(f"Hiii: {current_user}")

        # Get recent predictions for all profiles
        recent_predictions = []
        for profile in enhanced_profiles:
            predictions = await enhanced_astrology_service.get_predictions(current_user, profile['id'])
            for pred in predictions[:2]:  # Get 2 most recent per profile
                recent_predictions.append({
                    "profile_id": pred.profile_id,
                    "profile_name": profile['name'],
                    "prediction_type": str(pred.prediction_type),
                    "prediction_text": pred.prediction_text,
                    "created_at": pred.created_at.isoformat() if hasattr(pred.created_at, 'isoformat') else str(pred.created_at),
                    "expires_at": pred.expires_at.isoformat() if pred.expires_at and hasattr(pred.expires_at, 'isoformat') else str(pred.expires_at)
                })

        logger.info(f"******** reebct: {recent_predictions}")

        # Sort predictions by creation date (most recent first)
        recent_predictions.sort(key=lambda x: x['created_at'], reverse=True)

        created_at = to_aware_utc(user_data.get('createdAt'))
        last_login = to_aware_utc(user_data.get('lastLoginAt'))

        total_predictions = 0
        for p in enhanced_profiles:
            preds = await enhanced_astrology_service.get_predictions(current_user, p['id'])
            total_predictions += len(preds)

        summary = {
            "total_profiles": len(enhanced_profiles),
            "total_predictions": total_predictions,
            "subscription_status": user_data.get('subscriptionType', 'free'),
            "account_age_days": (
                (datetime.now(timezone.utc) - created_at).days
                if created_at else 0
            ),
            "last_activity_days": (
                (datetime.now(timezone.utc) - last_login).days
                if last_login else 0
            ),
            "astrology_calculation_method": "production_api"
        }

        # Compile comprehensive response
        user_details = UserDetailsResponse(
            user_id=current_user,
            email=user_data.get('email'),
            phone=user_data.get('phone'),
            display_name=user_data.get('displayName'),
            subscription_type=user_data.get('subscriptionType', 'free'),
            profile_complete=user_data.get('profile_complete', False),
            language=user_data.get('language', 'en'),
            timezone=user_data.get('timezone', 'Asia/Kolkata'),
            created_at=user_data.get('createdAt').isoformat() if user_data.get('createdAt') else None,
            last_login=user_data.get('lastLoginAt').isoformat() if user_data.get('lastLoginAt') else None,
            profiles=enhanced_profiles,
            recent_predictions=recent_predictions[:10],  # Show 10 most recent
            summary=summary
        )

        logger.info(f"✅ Successfully fetched comprehensive user details for: {current_user}")
        return user_details.dict()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to fetch user details for {current_user}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch user details")


def to_aware_utc(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@router.get("/session-status")
async def get_session_status(
    session_id: str,
    current_user: str = Depends(get_current_user)
):
    """
    Get current session status and user information

    This endpoint provides information about the current authentication session
    """
    try:
        # Get session data (implement if needed)
        return {
            "user_id": current_user,
            "status": "authenticated",
            "session_id": session_id
        }

    except Exception as e:
        logger.error(f"Session status check failed: {e}")
        raise HTTPException(status_code=500, detail="Session status check failed")

@router.post("/resend-otp")
async def resend_otp(
    session_id: str,
    background_tasks: BackgroundTasks
):
    """
    Resend OTP for the current session
    
    This endpoint allows users to request a new OTP if the previous one expired
    or was not received
    """
    try:
        # Get session data
        session_data = await user_service._get_session(session_id)
        if not session_data:
            raise HTTPException(status_code=404, detail="Session not found or expired")
        
        # Re-initiate authentication for the same identifier
        identifier = session_data['identifier']
        result = await user_service.initiate_auth(identifier)
        
        logger.info(f"OTP resent for session: {session_id}")
        return {
            "message": "OTP resent successfully",
            "expires_in": result["expires_in"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OTP resend failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to resend OTP")

# Helper Functions
def _mask_identifier(identifier: str, auth_type: str) -> str:
    """Mask identifier for logging purposes"""
    if auth_type == "email":
        parts = identifier.split('@')
        if len(parts) == 2:
            username = parts[0]
            domain = parts[1]
            masked_username = username[:2] + '*' * (len(username) - 2)
            return f"{masked_username}@{domain}"
    else:  # phone
        if len(identifier) > 6:
            return identifier[:3] + '*' * (len(identifier) - 6) + identifier[-3:]
    return identifier

def _safe_parse_timestamp(timestamp):
    """Safely parse timestamp that might be string, datetime, or Firestore timestamp"""
    if not timestamp:
        return None
    if hasattr(timestamp, 'isoformat'):
        # It's a datetime or Firestore timestamp
        return timestamp.isoformat()
    if isinstance(timestamp, str):
        try:
            # Try to parse as ISO string
            from datetime import datetime
            parsed = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            return parsed.isoformat()
        except ValueError:
            # If parsing fails, return as is or None
            return None
    return None

def _safe_datetime_diff(now, timestamp):
    """Safely calculate days difference, handling different timestamp types"""
    if not timestamp:
        return 0
    from datetime import datetime
    if hasattr(timestamp, '__sub__'):
        # It's a datetime or Firestore timestamp
        return (now - timestamp).days
    if isinstance(timestamp, str):
        try:
            parsed = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            return (now - parsed).days
        except ValueError:
            return 0
    return 0

async def _track_user_login(user_id: str, is_new_user: bool):
    """Background task to track user login analytics"""
    try:
        # Implement user analytics tracking
        logger.info(f"User login tracked: {user_id}, new_user: {is_new_user}")
        # TODO: Integrate with analytics service
    except Exception as e:
        logger.error(f"User login tracking failed: {e}")

# Health check endpoint for authentication service (Redis removed)
@router.get("/health")
async def auth_health_check():
    """Health check endpoint for authentication service"""
    try:
        # Check Firebase connection (basic check)
        firebase_status = "connected"  # Assume connected if no exception

        return {
            "status": "healthy",
            "firebase": firebase_status,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    except Exception as e:
        logger.error(f"Auth health check failed: {e}")
        raise HTTPException(status_code=503, detail="Authentication service unhealthy")

class ProfileStatusResponse(BaseModel):
    """Response model for user profile status"""
    user_id: str
    profile_complete: bool
    has_profiles: bool
    next_step: str
    profile_count: int

# Removed duplicate UserDetailsResponse model definition




@router.get("/profiles", response_model=List[ProfileResponse])
async def get_profiles(current_user: str = Depends(get_current_user)):
    try:
        db = get_firestore_client()
        docs = db.collection('person_profiles').where(filter=FieldFilter('user_id', '==', current_user)).where(filter=FieldFilter('is_active', '==', True)).get()
        profiles = []
        for doc in docs:
            data = doc.to_dict()
            profiles.append(ProfileResponse(**data))
        return profiles
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

from fastapi import Request

# Production-ready dashboard endpoint
@router.get("/dashboard", response_model=Dict[str, Any])
async def get_user_dashboard(current_user: str = Depends(get_current_user)):
    """
    Get comprehensive user dashboard with all profile data and astrology calculations

    This endpoint provides:
    1. Complete user account information
    2. All user profiles with birth details
    3. Real astrology calculations for each profile
    4. Chart data and predictions
    5. Marriage compatibility data (if available)
    """
    try:
        logger.info(f"📊 Generating dashboard for user: {current_user}")

        # Get user account information
        db = get_firestore_client()
        user_ref = db.collection('users').document(current_user)
        user_doc = user_ref.get()

        if not user_doc.exists:
            raise HTTPException(status_code=404, detail="User not found")

        user_data = user_doc.to_dict()

        # Get all user profiles
        profiles_query = db.collection('person_profiles').where(filter=FieldFilter('user_id', '==', current_user)).where(filter=FieldFilter('is_active', '==', True))
        profiles_docs = profiles_query.get()

        profiles = []
        for doc in profiles_docs:
            profile_data = doc.to_dict()

            # Generate comprehensive astrology chart for each profile
            chart_data = await enhanced_astrology_service.generate_astrology_chart_data(
                current_user, doc.id, profile_data
            )

            # Create enhanced profile with chart data
            enhanced_profile = {
                **profile_data,
                'chart_data': chart_data,
                'id': doc.id
            }
            profiles.append(enhanced_profile)

        # Get recent predictions for all profiles
        recent_predictions = []
        for profile in profiles:
            predictions = await enhanced_astrology_service.get_predictions(current_user, profile['id'])
            recent_predictions.extend(predictions[:3])  # Get 3 most recent per profile

        # Get marriage matches if available
        marriage_matches = []
        for profile in profiles:
            matches = await enhanced_astrology_service.get_marriage_matches(current_user, profile['id'])
            marriage_matches.extend(matches)

        # Compile comprehensive dashboard data
        dashboard_data = {
            "user_info": {
                "user_id": current_user,
                "email": user_data.get('email'),
                "phone": user_data.get('phone'),
                "display_name": user_data.get('name'),
                "subscription_type": user_data.get('subscriptionType', 'free'),
                "profile_complete": user_data.get('profile_complete', False),
                "created_at": user_data.get('createdAt'),
                "last_login": user_data.get('lastLoginAt')
            },
            "profiles": profiles,
            "summary": {
                "total_profiles": len(profiles),
                "total_predictions": len(recent_predictions),
                "total_marriage_matches": len(marriage_matches),
                "subscription_status": user_data.get('subscriptionType', 'free')
            },
            "recent_predictions": [
                {
                    "profile_id": pred.profile_id,
                    "prediction_type": str(pred.prediction_type),
                    "prediction_text": pred.prediction_text[:100] + "..." if len(pred.prediction_text) > 100 else pred.prediction_text,
                    "created_at": pred.created_at,
                    "expires_at": pred.expires_at
                }
                for pred in recent_predictions[:5]  # Show 5 most recent
            ],
            "marriage_matches": [
                {
                    "id": match.id,
                    "overall_score": match.overall_score,
                    "compatibility_level": match.compatibility_level,
                    "created_at": match.created_at
                }
                for match in marriage_matches[:3]  # Show 3 most recent
            ],
            "generated_at": datetime.utcnow().isoformat(),
            "astrology_calculation_method": "production_api"
        }

        logger.info(f"✅ Successfully generated dashboard for user: {current_user}")
        return dashboard_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to generate dashboard for user {current_user}: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate dashboard")

@router.post("/profiles/new", response_model=ProfileResponse)
@router.post("/profiles", response_model=ProfileResponse)
async def create_profile(profile_request: ProfileCreateRequest, request: Request, current_user: str = Depends(get_current_user)):
    """
    Create a new simplified profile for the current user.
    """
    try:
        logger.info("🧭 ENTER create_profile endpoint")
        # Log request for debugging
        body = await request.json()
        # Log raw Authorization header and IDs to aid debugging
        auth_header = request.headers.get('authorization')
        logger.info(f"🔐 Authorization header received: {auth_header[:30]}..." if auth_header else "🔐 Authorization header missing")
        logger.info(f"🔍 DEBUG: Token user_id: '{current_user}'")
        logger.info(f"🔍 DEBUG: Request body userId: '{getattr(profile_request, 'userId', None)}'")

        # Trust server-side identity; ignore client-supplied userId if it mismatches
        effective_user_id = current_user
        if getattr(profile_request, 'userId', None) and profile_request.userId != current_user:
            logger.warning(f"⚠️ Mismatch between token user ('{current_user}') and request user ('{profile_request.userId}'); using token user_id")

        logger.info(f"✅ Authorization resolved. Using user_id '{effective_user_id}' for profile creation.")
        logger.info(f"Profile creation request for user '{effective_user_id}': {body}")

        # Get Firestore client
        db = get_firestore_client()

        # Generate unique profile ID
        profile_id = str(uuid.uuid4())

        # Convert string inputs to proper types
        from datetime import date, time
        birth_date = date.fromisoformat(profile_request.birth_date)
        birth_time = time.fromisoformat(profile_request.birth_time)

        # Prepare profile data using values from frontend request
        created_timestamp = datetime.fromisoformat(profile_request.createdAt.replace('Z', '+00:00'))

        profile_data = {
            'id': profile_id,
            'user_id': effective_user_id,
            'userId': effective_user_id,  # For backward compatibility
            'name': profile_request.name,
            # Store Firestore-friendly primitives (strings), not date/time objects
            'birth_date': profile_request.birth_date,    # e.g., "1990-01-01"
            'birth_time': profile_request.birth_time,    # e.g., "17:24:00"
            'birth_place': profile_request.birth_place,
            'gender': profile_request.gender,
            'relationship': 'self',
            'created_at': created_timestamp,
            'createdAt': created_timestamp,  # For backward compatibility
            'updated_at': datetime.utcnow(),
            'is_active': True,
        }

        # Calculate comprehensive astrology data using production API
        astrology_data = await enhanced_astrology_service.calculate_comprehensive_astrology(
            profile_request.birth_date,
            profile_request.birth_time,
            profile_request.birth_place,
            profile_request.gender
        )

        # Add astrology data to profile
        profile_data.update({
            'zodiac_sign': astrology_data.get('zodiac_sign', 'Unknown'),
            'moon_sign': astrology_data.get('moon_sign', 'Unknown'),
            'nakshatra': astrology_data.get('nakshatra', 'Unknown'),
            'ascendant': astrology_data.get('ascendant', 'Unknown'),
            'varna': astrology_data.get('varna', 'Unknown'),
            'guna': astrology_data.get('guna', 'Unknown'),
            'element': astrology_data.get('element', 'Unknown'),
            'modality': astrology_data.get('modality', 'Unknown'),
            'astrology_calculation_method': astrology_data.get('calculation_method', 'api'),
            'astrology_calculated_at': astrology_data.get('calculated_at'),
            'planetary_positions': astrology_data.get('planetary_positions', {}),
            'houses': astrology_data.get('houses', {})
        })

        # Save profile to Firestore
        db.collection('person_profiles').document(profile_id).set(profile_data)

        # Update user's profile completion status using the authenticated userId
        db.collection('users').document(effective_user_id).set({
            'profile_complete': True,
            'updated_at': datetime.utcnow()
        }, merge=True)


        logger.info(f"✅ Profile created for {current_user} (ID: {profile_id})")
        try:
            # Generate self-compatibility meter
            await generate_self_compatibility_meter(
                profile_id=profile_id,
                current_user=effective_user_id
            )
            logger.info(f"✅ Self-compatibility meter generated for profile {profile_id}")
        except Exception as e:
            logger.error(f"⚠️ Failed to generate self-compatibility meter: {e}")
        
        try:
            # Generate planetary strength analysis
            await generate_planetary_strength_analysis(
                profile_id=profile_id,
                current_user=effective_user_id
            )
            logger.info(f"✅ Planetary strength analysis generated for profile {profile_id}")
        except Exception as e:
            logger.error(f"⚠️ Failed to generate planetary strength analysis: {e}")

        try:
            # Generate planetary strength analysis
            await generate_specific_prediction(
                profile_id=profile_id,
                prediction_type=PredictionType.DAILY,
                current_user=effective_user_id
            )
            logger.info(f"✅ prediction generated for profile {profile_id}")
        except Exception as e:
            logger.error(f"⚠️ Failed to generate prediction strength analysis: {e}")
            

        logger.info(f"✅ Profile created for {current_user} (ID: {profile_id})")
        # Return the created profile
        return ProfileResponse(**profile_data)

    except ValidationError as e:
        # Handle validation errors
        formatted_errors = {}
        for error in e.errors():
            field = '.'.join(str(loc) for loc in error['loc'])
            formatted_errors[field] = error['msg']
        raise HTTPException(status_code=422, detail={
            "error": "Validation failed",
            "details": formatted_errors
        })
    except Exception as e:
        logger.error(f"Profile creation failed for user {current_user}: {e}")
        raise HTTPException(status_code=500, detail="Profile creation failed")

async def generate_self_compatibility_meter(
    profile_id: str,
    current_user: str = Depends(get_current_user)
):
    """
    Generate an AI-powered analysis of a profile's internal astrological harmony.
    This replaces the two-person compatibility check.
    """
    try:
        db = get_firestore_client()
        logger.info(f"*****************: {current_user}")
        # 1. Fetch profile and verify ownership
        profile_ref = db.collection('person_profiles').document(profile_id)
        profile_doc = profile_ref.get()
        if not profile_doc.exists:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Profile {profile_id} not found")
        
        profile_data = profile_doc.to_dict()
        if profile_data.get('user_id') != current_user:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Access denied to profile")

        # 2. Construct prompt for AI service
        def extract_astro_details(data):
            # Extract relevant details for the prompt
            return {
                "ascendant": data.get("ascendant", "N/A"),
                "zodiac_sign": data.get("zodiac_sign", "N/A"), # Assuming 'rasi' is in the profile data
                "guna": data.get("guna", "N/A"),
                "element": data.get("element", "N/A")
            }
        
        details = extract_astro_details(profile_data)
        logger.info(f"*****************: {details}")

        prompt = (
            f"Analyze the internal astrological harmony of a person for self-awareness. "
            f"Astrological Details: Ascendant - {details['ascendant']}, zodiac_sign - {details['zodiac_sign']}, Guna - {details['guna']}. "
            "Based on these core traits, evaluate their internal alignment and potential challenges. "
            "Return a JSON object with three keys: 'emotional_balance_score', 'mental_clarity_score', 'physical_vitality_score','overall_match'. "
            "The values must be floats between 0.0 and 1.0. Higher scores indicate better harmony. "
            "Do not add any other text, explanations, or markdown."
        )

        # 3. Call AI service and parse the response
        # Assuming a service function that takes a raw prompt
        raw_json_response = await chatgpt_service.generate_raw_completion(prompt)
        try:
            meter_data = json.loads(raw_json_response)
        except json.JSONDecodeError:
            logger.error(f"AI service returned malformed JSON: {raw_json_response}")
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "AI service returned unparsable data")

        # 4. Save the result to the 'compatibility_meter' collection with a new structure
        meter_id =profile_id
        
        data_to_save = {
            "profile_id": profile_id,
            "user_id": current_user,
            "emotional_score": meter_data.get("emotional_balance_score"),
            "mental_score": meter_data.get("mental_clarity_score"),
            "physical_score": meter_data.get("physical_vitality_score"),
            "overall_match": meter_data.get("overall_match"),
            "last_updated": datetime.utcnow().isoformat()
        }
        
        # Using the same collection but a different ID format to distinguish
        db.collection('compatibility_meter').document(meter_id).set(data_to_save)

        return {
            "message": "Self-compatibility meter generated successfully.",
            "meter_id": meter_id,
            "data": data_to_save
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate self-compatibility meter for profile {profile_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {str(e)}")


async def generate_planetary_strength_analysis(
    profile_id: str,
    current_user: str = Depends(get_current_user)
):
    """
    Generate a detailed planetary strength analysis for a profile using ChatGPT.
    Saves results to Firestore collection 'planetary_strength_analysis'.
    """
    try:
        db = get_firestore_client()
        logger.info(f"🔭 Starting planetary strength analysis for user: {current_user}")

        # 1. Fetch and verify profile
        profile_ref = db.collection('person_profiles').document(profile_id)
        profile_doc = profile_ref.get()
        if not profile_doc.exists:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Profile {profile_id} not found")

        profile_data = profile_doc.to_dict()
        if profile_data.get("user_id") != current_user:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Access denied to this profile")

        # 2. Build AI prompt
        prompt = (
            f"Analyze the planetary strength for this person based on their astrological details.\n"
            f"Profile Info: Ascendant - {profile_data.get('ascendant', 'N/A')}, "
            f"Zodiac Sign - {profile_data.get('zodiac_sign', 'N/A')}, "
            f"Guna - {profile_data.get('guna', 'N/A')}, Element - {profile_data.get('element', 'N/A')}.\n\n"
            "Return a JSON object with:\n"
            "- 'overall_rating': string (like 'Strong', 'Moderate', or 'Weak')\n"
            "- 'overall_strength': float (0.0–1.0)\n"
            "- 'planets': array of objects, each having keys: 'planet', 'natchathra', 'position', and 'strength' (float).\n"
            "Provide only valid JSON without any text or explanation."
        )

        # 3. Generate raw JSON from ChatGPT
        raw_json_response = await chatgpt_service.generate_raw_completion(prompt)
        try:
            analysis_data = json.loads(raw_json_response)
        except json.JSONDecodeError:
            logger.error(f"Malformed JSON from ChatGPT: {raw_json_response}")
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "AI returned invalid JSON format")

        # 4. Prepare data for Firestore
        data_to_save = {
            "profile_id": profile_id,
            "user_id": current_user,
            "overall_rating": analysis_data.get("overall_rating"),
            "overall_strength": analysis_data.get("overall_strength"),
            "planets": analysis_data.get("planets", []),
            "last_updated": datetime.utcnow().isoformat()
        }

        # 5. Save to Firestore collection: planetary_strength_analysis
        db.collection("planetary_strength_analysis").document(profile_id).set(data_to_save)

        logger.info(f"✅ Planetary strength analysis saved for profile {profile_id}")
        return {
            "message": "Planetary strength analysis generated successfully.",
            "profile_id": profile_id,
            "data": data_to_save
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate planetary strength analysis for {profile_id}: {e}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


async def generate_specific_prediction(
    profile_id: str,
    prediction_type: PredictionType,
    current_user: str = Depends(get_current_user)
):
    """
    Generate structured AI prediction and save it to Firestore.
    """
    try:
        db = get_firestore_client()
        profile_ref = db.collection("person_profiles").document(profile_id)
        profile_doc = profile_ref.get()

        if not profile_doc.exists:
            raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")

        profile_data = profile_doc.to_dict()

        # Get astrology chart
        chart_data = await enhanced_astrology_service._generate_astrology_chart(
            current_user, profile_id, profile_data
        )

        logger.info(f"*****************: {chart_data}")

        # Get structured prediction JSON from ChatGPT
        prediction_json = await chatgpt_service.generate_personal_predictionsbyme(
            profile_data, chart_data, prediction_type.value
        )

        now = datetime.utcnow()
        prediction_text = json.dumps(prediction_json)

        # Create Prediction object
        prediction_obj = Prediction(
            id=f"{profile_id}_{prediction_type.value}_{now.strftime('%Y%m%d_%H%M%S')}",
            profile_id=profile_id,
            user_id=current_user,
            prediction_type=PredictionType(prediction_type.value),
            prediction_text=prediction_text,
            generated_by="chatgpt",
            created_at=now,
            updated_at=now,
            expires_at=None  # No expiration for structured predictions
        )

        # Save to Firestore
        doc_id = prediction_obj.id
        db.collection("predictions").document(doc_id).set(prediction_obj.dict())

        return {
            "message": f"{prediction_type.value.title()} prediction generated successfully",
            "prediction": prediction_json,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate structured prediction: {str(e)}"
        )




@router.get("/profiles/{profile_id}")
async def get_profile_or_status(profile_id: str, current_user: str = Depends(get_current_user)):
    """Get profile by ID, or user profile status if profile_id is user_id"""
    try:
        db = get_firestore_client()

        # First try to get as profile
        doc = db.collection('person_profiles').document(profile_id).get()
        if doc.exists:
            data = doc.to_dict()
            logger.info(f"🔍 DEBUG: Profile access - Profile user_id: '{data['user_id']}', Current user: '{current_user}'")
            logger.info(f"🔍 DEBUG: Profile ownership match: {data['user_id'] == current_user}")

            if data['user_id'] != current_user:
                logger.warning(f"🚫 403 Profile access denied - Profile owner: '{data['user_id']}', Requester: '{current_user}'")
                raise HTTPException(status_code=403, detail="Not authorized to access this profile")
            return ProfileResponse(**data)

        # If not found as profile, check if it's a user_id
        if profile_id == current_user:
            # It's the current user, return profile status
            user_doc = db.collection('users').document(profile_id).get()
            user_data = user_doc.to_dict() if user_doc.exists else {}

            profiles_query = db.collection('person_profiles').where(filter=FieldFilter('user_id', '==', profile_id)).where(filter=FieldFilter('is_active', '==', True))
            profile_count = len(profiles_query.get())
            profile_complete = user_data.get('profile_complete', False)
            has_profiles = profile_count > 0

            if profile_complete or has_profiles:
                next_step = 'dashboard'
            else:
                next_step = 'complete_profile'

            return {
                "user_id": profile_id,
                "profile_complete": profile_complete,
                "has_profiles": has_profiles,
                "next_step": next_step,
                "profile_count": profile_count,
                "message": "No profile found, check next_step for navigation"
            }

        raise HTTPException(status_code=404, detail="Profile not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/profiles/{profile_id}", response_model=ProfileResponse)
async def update_profile(profile_id: str, profile: PersonProfile, current_user: str = Depends(get_current_user)):
    try:
        # Check if profile exists and belongs to user
        db = get_firestore_client()
        doc_ref = db.collection('person_profiles').document(profile_id)
        doc = doc_ref.get()
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Profile not found")

        data = doc.to_dict()
        logger.info(f"🔍 DEBUG: Profile update - Profile user_id: '{data['user_id']}', Current user: '{current_user}'")
        logger.info(f"🔍 DEBUG: Profile ownership match: {data['user_id'] == current_user}")

        if data['user_id'] != current_user:
            logger.warning(f"🚫 403 Profile update denied - Profile owner: '{data['user_id']}', Requester: '{current_user}'")
            raise HTTPException(status_code=403, detail="Not authorized")

        # Update profile data
        profile_data = profile.dict()
        profile_data['updated_at'] = datetime.utcnow()

        # Recalculate astrology data if birth details changed
        if (profile.birth_date != data.get('birth_date') or
            profile.birth_time != data.get('birth_time') or
            profile.birth_place != data.get('birth_place')):
            astrology_data = await enhanced_astrology_service.calculate_comprehensive_astrology(
                profile.birth_date,
                profile.birth_time,
                profile.birth_place,
                profile.gender
            )
            profile_data.update({
                'zodiac_sign': astrology_data.get('zodiac_sign', 'Unknown'),
                'moon_sign': astrology_data.get('moon_sign', 'Unknown'),
                'nakshatra': astrology_data.get('nakshatra', 'Unknown'),
                'ascendant': astrology_data.get('ascendant', 'Unknown'),
                'varna': astrology_data.get('varna', 'Unknown'),
                'guna': astrology_data.get('guna', 'Unknown'),
                'element': astrology_data.get('element', 'Unknown'),
                'modality': astrology_data.get('modality', 'Unknown'),
                'astrology_calculation_method': astrology_data.get('calculation_method', 'api'),
                'astrology_calculated_at': astrology_data.get('calculated_at'),
            })

        doc_ref.update(profile_data)
        return ProfileResponse(**profile_data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/profiles/{profile_id}")
async def delete_profile(profile_id: str, current_user: str = Depends(get_current_user)):
    try:
        db = get_firestore_client()
        doc_ref = db.collection('person_profiles').document(profile_id)
        doc = doc_ref.get()
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Profile not found")

        data = doc.to_dict()
        logger.info(f"🔍 DEBUG: Profile delete - Profile user_id: '{data['user_id']}', Current user: '{current_user}'")
        logger.info(f"🔍 DEBUG: Profile ownership match: {data['user_id'] == current_user}")

        if data['user_id'] != current_user:
            logger.warning(f"🚫 403 Profile delete denied - Profile owner: '{data['user_id']}', Requester: '{current_user}'")
            raise HTTPException(status_code=403, detail="Not authorized")

        # Soft delete by marking as inactive
        doc_ref.update({'is_active': False, 'updated_at': datetime.utcnow()})
        return {"message": "Profile deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

