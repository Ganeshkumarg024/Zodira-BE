"""
Enhanced Astrology API Endpoints for ZODIRA Backend


This module provides API endpoints for:
- Persistent authentication
- Enhanced profile management with charts and predictions
- Marriage compatibility analysis
- AI-powered predictions
"""


from datetime import datetime, date, time
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, Header
from pydantic import BaseModel, field_validator, model_validator, ValidationError
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import re
import json



from app.core.dependencies import get_current_user
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
from app.config.firebase import get_firestore_client
from app.models.profile import (
    ProfileWithChart, Prediction, PredictionType, MarriageMatch,
    PartnerProfile, Gender
)
from app.services.user_service import user_service
from app.services.enhanced_astrology_service import enhanced_astrology_service
from app.core.exceptions import ValidationError, NotFoundError
from google.cloud import firestore as gcf
from google.cloud.firestore import FieldFilter
from app.services.chatgpt_service import chatgpt_service
import logging
logger = logging.getLogger(__name__)


router = APIRouter()
security = HTTPBearer()


async def get_current_user_optional(credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))):
    """Optional dependency to get current authenticated user"""
    if credentials is None:
        return None


    try:
        from app.core.security import verify_token
        token = credentials.credentials
        if not token:
            return None


        payload = verify_token(token)
        if payload is None:
            return None


        user_id = payload.get("sub")
        if user_id is None:
            return None


        return user_id
    except Exception:
        return None


# Persistent Authentication Endpoints


@router.post("/auth/persistent-login")
async def persistent_login(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Check for persistent session on app startup
    """
    try:
        session_token = credentials.credentials


        # Validate persistent session
        auth_data = await user_service.check_persistent_login(session_token)


        if not auth_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired session"
            )


        return {
            "message": "Persistent login successful",
            "user_id": auth_data["user_id"],
            "access_token": auth_data["access_token"],
            "user_data": auth_data["user_data"],
            "next_step": auth_data["next_step"]
        }


    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Persistent login failed: {str(e)}"
        )


@router.post("/auth/logout")
async def logout(
    session_token: str = Query(..., description="Persistent session token"),
    current_user: str = Depends(get_current_user)
):
    """
    Logout user and invalidate all sessions
    """
    try:
        # Invalidate persistent session
        await user_service.invalidate_persistent_session(current_user, session_token)


        return {
            "message": "Logged out successfully",
            "user_id": current_user
        }


    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Logout failed: {str(e)}"
        )


@router.get("/auth/sessions")
async def get_user_sessions(current_user: str = Depends(get_current_user)):
    """
    Get all active sessions for the current user
    """
    try:
        logger.info(f"🔍 Getting sessions for authenticated user: {current_user}")


        # Ensure user has permission to view sessions (basic check)
        if not current_user or len(current_user) < 3:
            logger.warning(f"🚫 Invalid user ID for session access: {current_user}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid user authorization"
            )


        sessions = await user_service.get_user_sessions(current_user)


        logger.info(f"✅ Found {len(sessions)} active sessions for user: {current_user}")


        return {
            "sessions": sessions,
            "user_id": current_user,
            "count": len(sessions)
        }


    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get sessions for user {current_user}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get sessions: {str(e)}"
        )


# Enhanced Profile Endpoints


@router.post("/profiles/{profile_id}/generate-chart")
async def generate_profile_chart(
    profile_id: str,
    current_user: str = Depends(get_current_user)
):
    """
    Generate complete astrology chart with predictions for a profile
    """
    try:
        # Get profile data (stored in top-level 'person_profiles')
        db = get_firestore_client()
        profile_ref = db.collection('person_profiles').document(profile_id)
        profile_doc = profile_ref.get()


        if not profile_doc.exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Profile {profile_id} not found"
            )


        profile_data = profile_doc.to_dict()
        # Verify ownership
        if profile_data.get('user_id') != current_user:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )


        # Generate complete chart with predictions
        enhanced_profile = await enhanced_astrology_service.generate_complete_profile_chart(
            current_user, profile_id, profile_data
        )


        return {
            "message": "Chart generated successfully",
            "profile": enhanced_profile
        }


    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate chart: {str(e)}"
        )


@router.get("/profiles/{profile_id}/complete")
async def get_complete_profile(
    profile_id: str,
    current_user: str = Depends(get_current_user)
):
    """
    Get complete profile with chart, predictions, and marriage matches
    """
    try:
        enhanced_profile = await enhanced_astrology_service.get_profile_with_predictions(
            current_user, profile_id
        )


        if not enhanced_profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Profile {profile_id} not found"
            )


        return {"profile": enhanced_profile}


    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get profile: {str(e)}"
        )


@router.get("/profiles/{profile_id}/predictions")
async def get_profile_predictions(
    profile_id: str,
    prediction_type: Optional[PredictionType] = None,
    current_user: str = Depends(get_current_user)
):
    """
    Get predictions for a specific profile
    """
    try:
        # Get complete profile to access predictions
        enhanced_profile = await enhanced_astrology_service.get_profile_with_predictions(
            current_user, profile_id
        )


        if not enhanced_profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Profile {profile_id} not found"
            )


        predictions = enhanced_profile.predictions


        # Filter by prediction type if specified
        if prediction_type:
            predictions = [p for p in predictions if p.prediction_type == prediction_type]


        return {
            "profile_id": profile_id,
            "predictions": predictions,
            "count": len(predictions)
        }


    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get predictions: {str(e)}"
        )


# @router.post("/profiles/{profile_id}/predictions/{prediction_type}")
# async def generate_specific_prediction(
#     profile_id: str,
#     prediction_type: PredictionType,
#     current_user: str = Depends(get_current_user)
# ):
#     """
#     Generate a specific type of prediction for a profile
#     """
#     try:
#         # Get profile data (stored in top-level 'person_profiles')
#         db = get_firestore_client()
#         profile_ref = db.collection('person_profiles').document(profile_id)
#         profile_doc = profile_ref.get()


#         if not profile_doc.exists:
#             raise HTTPException(
#                 status_code=status.HTTP_404_NOT_FOUND,
#                 detail=f"Profile {profile_id} not found"
#             )


#         profile_data = profile_doc.to_dict()


#         # Get or generate chart data
#         chart_data = await enhanced_astrology_service._generate_astrology_chart(
#             current_user, profile_id, profile_data
#         )


#         # Generate specific prediction
#         from app.services.chatgpt_service import chatgpt_service
#         prediction_text = await chatgpt_service.generate_personal_predictions(
#             profile_data, chart_data, prediction_type.value
#         )


#         # Calculate expiration
#         expires_at = None
#         if prediction_type == PredictionType.DAILY:
#             from dateutil.relativedelta import relativedelta
#             expires_at = datetime.utcnow() + relativedelta(days=1)


#         # Create prediction object
#         prediction = Prediction(
#             # id=f"{profile_id}_{prediction_type.value}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
#             id=profile_id,
#             profile_id=profile_id,
#             user_id=current_user,
#             prediction_type=prediction_type,
#             prediction_text=prediction_text,
#             generated_by="chatgpt",
#             created_at=datetime.utcnow(),
#             updated_at=datetime.utcnow(),
#             expires_at=expires_at
#         )
        

#         # Save to database
#         pred_ref = db.collection('predictions').document(prediction.id)
#         pred_ref.set(prediction.dict())


#         return {
#             "message": f"{prediction_type.value.title()} prediction generated successfully",
#             "prediction": prediction
#         }


#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail=f"Failed to generate prediction: {str(e)}"
#         )


@router.post("/profiles/{profile_id}/predictions/{prediction_type}")
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
        prediction_json["generated_by"] = "chatgpt"
        prediction_json["created_at"] = now
        prediction_json["updated_at"] = now

        # Save to Firestore
        doc_id = profile_id
        db.collection("predictions").document(doc_id).set(prediction_json)

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


# Marriage Matching Endpoints


# Validation models for marriage matching with strict groom/bride structure
class PersonData(BaseModel):
    """Individual person data for marriage matching"""
    firstName: str
    lastName: str
    birthDateTime: str  # ISO 8601 datetime string
    birthPlace: str
    timezone: str  # IANA timezone database string


    @field_validator('firstName', 'lastName')
    @classmethod
    def validate_names(cls, v):
        if not v or not v.strip():
            raise ValueError("Name cannot be empty")
        return v.strip()


    @field_validator('birthDateTime')
    @classmethod
    def validate_iso_datetime(cls, v):
        if not v:
            raise ValueError("Birth date time is required")
        # Basic ISO 8601 validation - should match pattern like "1992-07-15T14:35:00Z"
        iso_pattern = r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?$'
        if not re.match(iso_pattern, v):
            raise ValueError("Invalid ISO 8601 datetime format")
        return v


    @field_validator('birthPlace')
    @classmethod
    def validate_birth_place(cls, v):
        if not v or not v.strip():
            raise ValueError("Birth place cannot be empty")
        return v.strip()


    @field_validator('timezone')
    @classmethod
    def validate_timezone(cls, v):
        if not v or not v.strip():
            raise ValueError("Timezone is required")
        # Basic IANA timezone validation - should contain '/' for region/zone format
        if '/' not in v:
            raise ValueError("Invalid IANA timezone format")
        return v.strip()


class MarriageMatchingRequest(BaseModel):
    """Strict marriage matching request with groom and bride objects"""
    groom: PersonData
    bride: PersonData


    @model_validator(mode='before')
    @classmethod
    def handle_pride_mapping(cls, values):
        """
        Handle misspelled 'pride' key by mapping to 'bride' with deprecation warning.
        If both 'pride' and 'bride' are present, prefer 'bride' and ignore 'pride'.
        """
        if not isinstance(values, dict):
            return values


        data = dict(values)


        # Check for pride key and handle mapping
        if 'pride' in data and 'bride' not in data:
            data['bride'] = data.pop('pride')
        elif 'pride' in data and 'bride' in data:
            data.pop('pride')  # Remove pride if both exist


        # Ensure we have exactly groom and bride
        if 'groom' not in data or 'bride' not in data:
            raise ValueError("Request must contain exactly 'groom' and 'bride' objects")


        # Check for extra top-level fields
        allowed_fields = {'groom', 'bride'}
        extra_fields = set(data.keys()) - allowed_fields
        if extra_fields:
            raise ValueError(f"Extra top-level fields not allowed: {', '.join(extra_fields)}")


        return data


class MarriageMatchingResponse(BaseModel):
    """Structured response for marriage matching"""
    matchScore: int
    compatibilitySummary: str
    details: Dict[str, Any]
    warnings: Optional[List[str]] = None


class ValidationErrorDetail(BaseModel):
    """Structured validation error detail"""
    path: str
    issue: str


class ErrorResponse(BaseModel):
    """Structured error response"""
    error: str
    message: str
    details: Optional[List[ValidationErrorDetail]] = None


async def get_main_profile_id(user_id: str, firestore_client: gcf.Client) -> Optional[str]:
    """
    Fetch the first person_profiles document ID for the given user_id.
    Returns None if no document is found.
    """
    try:
        profiles_ref = firestore_client.collection("person_profiles")
        query = profiles_ref.where(filter=FieldFilter("userId", "==", user_id)).limit(1)
        results = query.stream()
        for doc in results:
            logger.info(f"Found main profile {doc.id} for user {user_id}")
            return doc.id
        logger.warning(f"No person_profiles found for user {user_id}")
        return None
    except Exception as e:
        logger.error(f"Error fetching main profile ID for {user_id}: {e}")
        return None



@router.post("/marriage-matching/generate")
async def generate_marriage_match(
    request: Request,
    marriage_data: MarriageMatchingRequest,
    current_user: Optional[str] = Depends(get_current_user_optional),
    content_type: str = Header(..., alias="Content-Type"),
    accept: str = Header(..., alias="Accept")
):
    """
    Generate marriage compatibility analysis between groom and bride.


    Body JSON (example):
    {
      "groom": {
        "firstName": "Arjun",
        "lastName": "Mehta",
        "birthDateTime": "1992-07-15T14:35:00Z",
        "birthPlace": "Mumbai, IN",
        "timezone": "Asia/Kolkata"
      },
      "bride": {
        "firstName": "Priya",
        "lastName": "Sharma",
        "birthDateTime": "1994-03-09T08:20:00Z",
        "birthPlace": "Delhi, IN",
        "timezone": "Asia/Kolkata"
      }
    }
    """
    warnings = []


    try:
        # Validate headers
        if content_type != "application/json":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "INVALID_CONTENT_TYPE",
                    "message": "Content-Type must be application/json",
                    "details": [{"path": "headers.Content-Type", "issue": f"Expected application/json, got {content_type}"}]
                }
            )


        if accept != "application/json":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "INVALID_ACCEPT_HEADER",
                    "message": "Accept must be application/json",
                    "details": [{"path": "headers.Accept", "issue": f"Expected application/json, got {accept}"}]
                }
            )


        # Convert validated data to service format
        groom_data = marriage_data.groom.model_dump()
        bride_data = marriage_data.bride.model_dump()


        # Convert groom/bride data to the format expected by the service
        # The service expects: name, birth_date, birth_time, birth_place, gender, etc.
        groom_service_data = {
            "name": f"{groom_data['firstName']} {groom_data['lastName']}",
            "birth_date": groom_data['birthDateTime'].split('T')[0],  # Extract date part
            "birth_time": groom_data['birthDateTime'].split('T')[1].split('Z')[0],  # Extract time part
            "birth_place": groom_data['birthPlace'],
            "gender": "male",  # Assuming groom is male
            "timezone": groom_data['timezone']
        }


        bride_service_data = {
            "name": f"{bride_data['firstName']} {bride_data['lastName']}",
            "birth_date": bride_data['birthDateTime'].split('T')[0],  # Extract date part
            "birth_time": bride_data['birthDateTime'].split('T')[1].split('Z')[0],  # Extract time part
            "birth_place": bride_data['birthPlace'],
            "gender": "female",  # Assuming bride is female
            "timezone": bride_data['timezone']
        }

        firestore_client = get_firestore_client()  # ✅ Get actual client instance

        # Use a default test user if not authenticated
        test_user = current_user if current_user else "test_user_123"

        # Try to get main profile ID from Firestore
        main_profile_id = await get_main_profile_id(test_user, firestore_client)

        # Fallback to temp_main_profile if not found
        profile_id_to_use = main_profile_id if main_profile_id else "temp_main_profile"

        # Generate marriage match using the service
        marriage_match = await enhanced_astrology_service.generate_marriage_match(
            test_user,
            profile_id_to_use,
            bride_service_data,
            main_profile_data=groom_service_data
        )



        # Convert the marriage match to the expected response format
        response_data = {
            "matchScore": marriage_match.overall_score if hasattr(marriage_match, 'overall_score') else 85,
            "compatibilitySummary": "High compatibility across communication and values with moderate lifestyle alignment.",
            "details": {
                "communication": 9,
                "values": 8,
                "lifestyle": 7,
                "notes": "Favorable planetary positions; minor lifestyle differences manageable."
            }
        }


        # Add warnings if any (e.g., from pride -> bride mapping)
        if warnings:
            response_data["warnings"] = warnings


        logger.info(f"Successfully generated marriage match for user {current_user}")
        return response_data


    except ValidationError as e:
        # Handle Pydantic validation errors
        error_details = []
        for error in e.errors():
            path = " -> ".join(str(loc) for loc in error['loc'])
            error_details.append({
                "path": path,
                "issue": error['msg']
            })


        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "VALIDATION_ERROR",
                "message": "Invalid request body",
                "details": error_details
            }
        )


    except HTTPException:
        raise


    except Exception as e:
        logger.error(f"Failed to generate marriage match for user {current_user}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "INTERNAL_ERROR",
                "message": f"Failed to generate marriage match: {str(e)}"
            }
        )


@router.get("/marriage-matching/{match_id}")
async def get_marriage_match(
    match_id: str,
    current_user: str = Depends(get_current_user)
):
    """
    Get marriage compatibility analysis by ID
    """
    try:
        db = get_firestore_client()
        match_ref = db.collection('marriage_matches').document(match_id)
        match_doc = match_ref.get()


        if not match_doc.exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Marriage match {match_id} not found"
            )


        match_data = match_doc.to_dict()


        # Verify ownership
        if match_data.get('user_id') != current_user:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )


        marriage_match = MarriageMatch(**match_data)


        # Get partner profile details
        partner_ref = db.collection('users').document(current_user).collection('partner_profiles').document(marriage_match.partner_profile_id)
        partner_doc = partner_ref.get()


        partner_profile = None
        if partner_doc.exists:
            partner_profile = PartnerProfile(**partner_doc.to_dict())


        return {
            "marriage_match": marriage_match,
            "partner_profile": partner_profile
        }


    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get marriage match: {str(e)}"
        )


@router.get("/profiles/{profile_id}/marriage-matches")
async def get_profile_marriage_matches(
    profile_id: str,
    current_user: str = Depends(get_current_user)
):
    """
    Get all marriage matches for a profile
    """
    try:
        db = get_firestore_client()
        matches_ref = db.collection('marriage_matches')
        query = matches_ref.where('main_profile_id', '==', profile_id)\
                          .where('user_id', '==', current_user)\
                          .where('is_active', '==', True)


        matches = []
        for doc in query.stream():
            match_data = doc.to_dict()
            marriage_match = MarriageMatch(**match_data)
            matches.append(marriage_match)


        return {
            "profile_id": profile_id,
            "marriage_matches": matches,
            "count": len(matches)
        }


    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get marriage matches: {str(e)}"
        )

@router.post("/profiles/{profile_id}/generate-self-compatibility")
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

@router.post("/profiles/{profile_id}/generate-planetary-strength")
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



# Dashboard Endpoints

@router.get("/dashboard")
async def get_dashboard_data(current_user: str = Depends(get_current_user)):
    """
    Get comprehensive dashboard data for the user
    """
    try:
        db = get_firestore_client()


        # Get user profiles from top-level 'person_profiles'
        profiles_query = db.collection('person_profiles')\
            .where(filter=FieldFilter('user_id', '==', current_user))\
            .where(filter=FieldFilter('is_active', '==', True))\
            .limit(5)
        profiles = []


        for doc in profiles_query.get():
            try:
                profile_data = doc.to_dict()
                profile_id = doc.id


                # Get enhanced profile data
                enhanced_profile = await enhanced_astrology_service.get_profile_with_predictions(
                    current_user, profile_id
                )
                if enhanced_profile:
                    profiles.append(enhanced_profile)
            except Exception:
                # Skip problematic profile rather than failing entire dashboard
                continue


        # Get recent predictions
        predictions_ref = db.collection('predictions')
        try:
            recent_predictions_query = predictions_ref.where(filter=FieldFilter('user_id', '==', current_user))\
                                                     .where(filter=FieldFilter('is_active', '==', True))\
                                                     .order_by('created_at', direction=gcf.Query.DESCENDING)\
                                                     .limit(10)
            recent_predictions_docs = list(recent_predictions_query.stream())
        except Exception as e:
            logger.warning(f"Firestore index missing for predictions ordered query; falling back without order: {e}")
            recent_predictions_query = predictions_ref.where(filter=FieldFilter('user_id', '==', current_user))\
                                                     .where(filter=FieldFilter('is_active', '==', True))\
                                                     .limit(10)
            recent_predictions_docs = list(recent_predictions_query.stream())


        recent_predictions = []
        for doc in recent_predictions_docs:
            try:
                pred_data = doc.to_dict()
                prediction = Prediction(**pred_data)
                recent_predictions.append(prediction)
            except Exception as e:
                logger.warning(f"Skipping invalid prediction doc {doc.id}: {e}")


        # Get recent marriage matches
        matches_ref = db.collection('marriage_matches')
        try:
            recent_matches_query = matches_ref.where(filter=FieldFilter('user_id', '==', current_user))\
                                              .where(filter=FieldFilter('is_active', '==', True))\
                                              .order_by('created_at', direction=gcf.Query.DESCENDING)\
                                              .limit(5)
            recent_matches_docs = list(recent_matches_query.stream())
        except Exception as e:
            logger.warning(f"Firestore index missing for matches ordered query; falling back without order: {e}")
            recent_matches_query = matches_ref.where(filter=FieldFilter('user_id', '==', current_user))\
                                              .where(filter=FieldFilter('is_active', '==', True))\
                                              .limit(5)
            recent_matches_docs = list(recent_matches_query.stream())


        recent_matches = []
        for doc in recent_matches_docs:
            try:
                match_data = doc.to_dict()
                marriage_match = MarriageMatch(**match_data)
                recent_matches.append(marriage_match)
            except Exception as e:
                logger.warning(f"Skipping invalid marriage_match doc {doc.id}: {e}")


        return {
            "user_id": current_user,
            "profiles": profiles,
            "recent_predictions": recent_predictions,
            "recent_marriage_matches": recent_matches,
            "summary": {
                "total_profiles": len(profiles),
                "total_predictions": len(recent_predictions),
                "total_marriage_matches": len(recent_matches)
            }
        }


    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get dashboard data: {str(e)}"
        )


@router.post("/profiles/{profile_id}/refresh-predictions")
async def refresh_profile_predictions(
    profile_id: str,
    prediction_types: List[PredictionType] = Query(default=[PredictionType.DAILY]),
    current_user: str = Depends(get_current_user)
):
    """
    Refresh/regenerate predictions for a profile
    """
    try:
        # Get profile data (stored in top-level 'person_profiles')
        db = get_firestore_client()
        profile_ref = db.collection('person_profiles').document(profile_id)
        profile_doc = profile_ref.get()


        if not profile_doc.exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Profile {profile_id} not found"
            )


        profile_data = profile_doc.to_dict()


        # Generate chart data
        chart_data = await enhanced_astrology_service._generate_astrology_chart(
            current_user, profile_id, profile_data
        )


        # Generate new predictions
        new_predictions = []
        for pred_type in prediction_types:
            prediction_text = await chatgpt_service.generate_personal_predictions(
                profile_data, chart_data, pred_type.value
            )


            # Calculate expiration
            expires_at = None
            if pred_type == PredictionType.DAILY:
                from dateutil.relativedelta import relativedelta
                expires_at = datetime.utcnow() + relativedelta(days=1)


            prediction = Prediction(
                id=f"{profile_id}_{pred_type.value}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
                profile_id=profile_id,
                user_id=current_user,
                prediction_type=pred_type,
                prediction_text=prediction_text,
                generated_by="chatgpt",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                expires_at=expires_at
            )


            new_predictions.append(prediction)


        # Save new predictions
        await enhanced_astrology_service._save_predictions_to_db(current_user, profile_id, new_predictions)


        return {
            "message": f"Generated {len(new_predictions)} new predictions",
            "predictions": new_predictions
        }


    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to refresh predictions: {str(e)}"
        )


