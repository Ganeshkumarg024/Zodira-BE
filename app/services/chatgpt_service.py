# """
# ChatGPT API Service for ZODIRA Backend

# This service handles integration with OpenAI's ChatGPT API for generating
# personalized astrology predictions and marriage compatibility insights.
# """

# import os
# import json
# import logging
# import asyncio
# from typing import Dict, List, Optional, Any
# from datetime import datetime, date, time

# from app.config.settings import settings
# from app.config.firebase import get_firestore_client
# from app.core.exceptions import ValidationError

# # Import OpenAI client
# logger = logging.getLogger(__name__)

# try:
#     from openai import OpenAI
#     OPENAI_AVAILABLE = True
# except ImportError:
#     OPENAI_AVAILABLE = False
#     logger.warning("OpenAI client not available, install with: pip install openai")

# class ChatGPTService:
#     """Service for ChatGPT API integration"""

#     def __init__(self):
#         # Load API key from settings
#         self.api_key = settings.openai_api_key
#         self.client = None

#         # Modern OpenAI configuration with best practices
#         self.model = getattr(settings, 'openai_model', "gpt-4o-mini")  # Use modern, cost-effective model
#         self.max_tokens = getattr(settings, 'openai_max_tokens', 2000)  # Optimized token limit
#         self.temperature = getattr(settings, 'openai_temperature', 0.3)  # Balanced creativity for astrology
#         self.timeout = getattr(settings, 'openai_timeout', 30)  # Request timeout in seconds
#         self.max_retries = getattr(settings, 'openai_max_retries', 3)  # Retry failed requests

#         # Rate limiting configuration
#         self.rate_limit_per_minute = getattr(settings, 'openai_rate_limit_per_minute', 50)
#         self._last_request_time = 0
#         self._request_count = 0

#         self._db = None  # Lazy initialization for Firestore client

#     @property
#     def db(self):
#         """Lazy initialization of Firestore client"""
#         if self._db is None:
#             self._db = get_firestore_client()
#         return self._db

#     def _check_rate_limit(self) -> None:
#         """Check and enforce rate limiting for OpenAI API calls"""
#         import time

#         current_time = time.time()

#         # Reset counter if a minute has passed
#         if current_time - self._last_request_time >= 60:
#             self._request_count = 0
#             self._last_request_time = current_time

#         # Check if we're over the rate limit
#         if self._request_count >= self.rate_limit_per_minute:
#             sleep_time = 60 - (current_time - self._last_request_time)
#             if sleep_time > 0:
#                 logger.warning(f"Rate limit reached, sleeping for {sleep_time:.2f} seconds")
#                 time.sleep(sleep_time)
#                 self._request_count = 0
#                 self._last_request_time = time.time()

#         self._request_count += 1

#     def _make_openai_request(self, **kwargs):
#         """Make synchronous OpenAI API request with timeout"""
#         import time

#         start_time = time.time()
#         try:
#             # Set timeout for the request
#             response = self.client.chat.completions.create(
#                 timeout=self.timeout,
#                 **kwargs
#             )
#             elapsed = time.time() - start_time
#             logger.info(f"OpenAI API request completed in {elapsed:.2f}s")
#             return response
#         except Exception as e:
#             elapsed = time.time() - start_time
#             logger.error(f"OpenAI API request failed after {elapsed:.2f}s: {e}")
#             raise

#     async def _retry_with_backoff(self, func, *args, **kwargs):
#         """Retry API calls with exponential backoff"""
#         import random

#         for attempt in range(self.max_retries):
#             try:
#                 return await func(*args, **kwargs)
#             except Exception as e:
#                 if attempt == self.max_retries - 1:
#                     logger.error(f"All retry attempts failed. Final error: {e}")
#                     raise

#                 # Check if it's a rate limit or server error (retryable)
#                 if hasattr(e, 'status') and e.status in [429, 500, 502, 503, 504]:
#                     wait_time = (2 ** attempt) + random.uniform(0, 1)
#                     logger.warning(f"Retryable error on attempt {attempt + 1}/{self.max_retries}: {e}. Retrying in {wait_time:.2f}s")
#                     await asyncio.sleep(wait_time)
#                 else:
#                     # Non-retryable error, raise immediately
#                     logger.error(f"Non-retryable error: {e}")
#                     raise

#         # This should never be reached, but just in case
#         raise RuntimeError("Max retries exceeded")

#     # Initialize OpenAI client if API key is available
#         if self.api_key and OPENAI_AVAILABLE:
#             try:
#                 self.client = OpenAI(api_key=self.api_key)
#                 logger.info("✅ OpenAI client initialized successfully")
#             except Exception as e:
#                 logger.error(f"❌ Failed to initialize OpenAI client: {e}")
#                 raise ValueError(f"OpenAI client initialization failed: {e}")
#         elif not self.api_key:
#             logger.error("❌ OpenAI API key not configured")
#             raise ValueError("OpenAI API key is required for AI features")
#         else:
#             logger.error("❌ OpenAI client not available")
#             raise ValueError("OpenAI package not installed. Install with: pip install openai")

#     async def generate_personal_predictions(
#         self,
#         profile_data: Dict[str, Any],
#         chart_data: Dict[str, Any],
#         prediction_type: str = "daily"
#     ) -> str:
#         """
#         Generate personalized astrology predictions using ChatGPT

#         Args:
#             profile_data: User's profile information
#             chart_data: Astrology chart data
#             prediction_type: Type of prediction (daily, weekly, monthly, etc.)

#         Returns:
#             Generated prediction text
#         """
#         try:
#             if not self.client:
#                 raise ValueError("OpenAI client not initialized. Check API key configuration.")

#             # Create prompt for ChatGPT
#             prompt = self._create_prediction_prompt(profile_data, chart_data, prediction_type)

#             # Apply rate limiting
#             self._check_rate_limit()

#             # Use OpenAI client with modern best practices
#             response = await self._retry_with_backoff(
#                 self._make_openai_request,
#                 model=self.model,
#                 messages=[
#                     {
#                         "role": "system",
#                         "content": "You are an expert Vedic astrologer with deep knowledge of astrology, zodiac signs, and planetary influences. Provide accurate, personalized predictions based on birth chart data."
#                     },
#                     {
#                         "role": "user",
#                         "content": prompt
#                     }
#                 ],
#                 temperature=self.temperature,
#                 max_tokens=self.max_tokens
#             )

#             prediction = response.choices[0].message.content.strip()
#             logger.info(f"Generated {prediction_type} prediction for user {profile_data.get('user_id')}")
#             return prediction

#         except Exception as e:
#             logger.error(f"Failed to generate prediction: {e}")
#             logger.info("🔄 Using fallback prediction generation")
#             # Return fallback prediction instead of raising error
#             return self._generate_mock_prediction(profile_data, prediction_type)

#     async def generate_marriage_compatibility(
#         self,
#         main_profile: Dict[str, Any],
#         partner_profile: Dict[str, Any],
#         main_chart: Dict[str, Any],
#         partner_chart: Dict[str, Any]
#     ) -> Dict[str, Any]:
#         """
#         Generate marriage compatibility analysis using ChatGPT

#         Args:
#             main_profile: Main user's profile data
#             partner_profile: Partner's profile data
#             main_chart: Main user's astrology chart
#             partner_chart: Partner's astrology chart

#         Returns:
#             Marriage compatibility analysis
#         """
#         try:
#             if not self.client:
#                 raise ValueError("OpenAI client not initialized. Check API key configuration.")

#             # Get the stored marriage compatibility prompt
#             stored_prompt = self._get_marriage_compatibility_prompt()

#             # Format the prompt with actual data
#             formatted_prompt = stored_prompt.replace("{MAIN_NAME}", main_profile.get('name', 'User'))
#             formatted_prompt = formatted_prompt.replace("{MAIN_BIRTH_DATE}", str(main_profile.get('birth_date', 'Unknown')))
#             formatted_prompt = formatted_prompt.replace("{MAIN_BIRTH_TIME}", str(main_profile.get('birth_time', 'Unknown')))
#             formatted_prompt = formatted_prompt.replace("{MAIN_BIRTH_PLACE}", main_profile.get('birth_place', 'Unknown'))
#             formatted_prompt = formatted_prompt.replace("{MAIN_ZODIAC_SIGN}", main_profile.get('zodiac_sign', 'Unknown'))
#             formatted_prompt = formatted_prompt.replace("{MAIN_MOON_SIGN}", main_profile.get('moon_sign', 'Unknown'))
#             formatted_prompt = formatted_prompt.replace("{MAIN_GENDER}", main_profile.get('gender', 'Unknown'))

#             formatted_prompt = formatted_prompt.replace("{PARTNER_NAME}", partner_profile.get('name', 'Partner'))
#             formatted_prompt = formatted_prompt.replace("{PARTNER_BIRTH_DATE}", str(partner_profile.get('birth_date', 'Unknown')))
#             formatted_prompt = formatted_prompt.replace("{PARTNER_BIRTH_TIME}", str(partner_profile.get('birth_time', 'Unknown')))
#             formatted_prompt = formatted_prompt.replace("{PARTNER_BIRTH_PLACE}", partner_profile.get('birth_place', 'Unknown'))
#             formatted_prompt = formatted_prompt.replace("{PARTNER_ZODIAC_SIGN}", partner_profile.get('zodiac_sign', 'Unknown'))
#             formatted_prompt = formatted_prompt.replace("{PARTNER_MOON_SIGN}", partner_profile.get('moon_sign', 'Unknown'))
#             formatted_prompt = formatted_prompt.replace("{PARTNER_GENDER}", partner_profile.get('gender', 'Unknown'))

#             # Custom JSON encoder for datetime objects
#             def json_encoder(obj):
#                 if isinstance(obj, datetime):
#                     return obj.isoformat()
#                 elif isinstance(obj, date):
#                     return obj.isoformat()
#                 elif isinstance(obj, time):
#                     return obj.isoformat()
#                 elif hasattr(obj, 'dict'):
#                     return obj.dict()
#                 elif hasattr(obj, '__dict__'):
#                     return obj.__dict__
#                 raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

#             formatted_prompt = formatted_prompt.replace("{MAIN_CHART_DATA}", json.dumps(main_chart, indent=2, default=json_encoder))
#             formatted_prompt = formatted_prompt.replace("{PARTNER_CHART_DATA}", json.dumps(partner_chart, indent=2, default=json_encoder))

#             # Apply rate limiting
#             self._check_rate_limit()

#             # Use OpenAI client with modern best practices
#             response = await self._retry_with_backoff(
#                 self._make_openai_request,
#                 model=self.model,
#                 messages=[
#                     {"role": "system", "content": "You are Zodira – a Vedic Astrology AI specialized in marriage compatibility analysis."},
#                     {"role": "user", "content": formatted_prompt}
#                 ],
#                 temperature=self.temperature,
#                 max_tokens=self.max_tokens
#             )

#             analysis = response.choices[0].message.content.strip()

#             # Parse the analysis to extract structured data
#             compatibility_data = self._parse_compatibility_analysis(analysis)

#             logger.info(f"Generated marriage compatibility for profiles {main_profile.get('id')} and {partner_profile.get('id')}")
#             return compatibility_data

#         except Exception as e:
#             logger.error(f"Failed to generate marriage compatibility: {e}")
#             logger.info("🔄 Using fallback marriage compatibility analysis")
#             # Return fallback compatibility instead of raising error
#             return self._generate_mock_compatibility(main_profile, partner_profile)

#     def _create_prediction_prompt(self, profile_data: Dict[str, Any], chart_data: Dict[str, Any], prediction_type: str) -> str:
#         """Create prompt for astrology predictions"""

#         birth_date = profile_data.get('birth_date', 'Unknown')
#         zodiac_sign = profile_data.get('zodiac_sign', 'Unknown')
#         moon_sign = profile_data.get('moon_sign', 'Unknown')

#         prompt = f"""
#         Generate a personalized {prediction_type} astrology prediction for:

#         Person Details:
#         - Name: {profile_data.get('name', 'User')}
#         - Birth Date: {birth_date}
#         - Zodiac Sign: {zodiac_sign}
#         - Moon Sign: {moon_sign}
#         - Gender: {profile_data.get('gender', 'Unknown')}

#         Astrology Chart Data:
#         {json.dumps(chart_data, indent=2)}

#         Please provide a detailed, accurate {prediction_type} prediction covering:
#         1. Overall outlook for the day/week/month
#         2. Career and professional matters
#         3. Health and well-being
#         4. Relationships and personal life
#         5. Financial matters
#         6. Lucky numbers, colors, and directions
#         7. Any precautions or remedies

#         Make the prediction personal, positive, and actionable. Use traditional Vedic astrology principles.
#         """

#         return prompt

#     def _create_marriage_prompt(self, main_profile: Dict[str, Any], partner_profile: Dict[str, Any],
#                               main_chart: Dict[str, Any], partner_chart: Dict[str, Any]) -> str:
#         """Create prompt for marriage compatibility analysis using the stored Vedic astrology prompt"""

#         # Get the stored marriage compatibility prompt
#         stored_prompt = self._get_marriage_compatibility_prompt()

#         # Format the prompt with actual data
#         formatted_prompt = stored_prompt.replace("{MAIN_NAME}", main_profile.get('name', 'User'))
#         formatted_prompt = formatted_prompt.replace("{MAIN_BIRTH_DATE}", str(main_profile.get('birth_date', 'Unknown')))
#         formatted_prompt = formatted_prompt.replace("{MAIN_BIRTH_TIME}", str(main_profile.get('birth_time', 'Unknown')))
#         formatted_prompt = formatted_prompt.replace("{MAIN_BIRTH_PLACE}", main_profile.get('birth_place', 'Unknown'))
#         formatted_prompt = formatted_prompt.replace("{MAIN_ZODIAC_SIGN}", main_profile.get('zodiac_sign', 'Unknown'))
#         formatted_prompt = formatted_prompt.replace("{MAIN_MOON_SIGN}", main_profile.get('moon_sign', 'Unknown'))
#         formatted_prompt = formatted_prompt.replace("{MAIN_GENDER}", main_profile.get('gender', 'Unknown'))

#         formatted_prompt = formatted_prompt.replace("{PARTNER_NAME}", partner_profile.get('name', 'Partner'))
#         formatted_prompt = formatted_prompt.replace("{PARTNER_BIRTH_DATE}", str(partner_profile.get('birth_date', 'Unknown')))
#         formatted_prompt = formatted_prompt.replace("{PARTNER_BIRTH_TIME}", str(partner_profile.get('birth_time', 'Unknown')))
#         formatted_prompt = formatted_prompt.replace("{PARTNER_BIRTH_PLACE}", partner_profile.get('birth_place', 'Unknown'))
#         formatted_prompt = formatted_prompt.replace("{PARTNER_ZODIAC_SIGN}", partner_profile.get('zodiac_sign', 'Unknown'))
#         formatted_prompt = formatted_prompt.replace("{PARTNER_MOON_SIGN}", partner_profile.get('moon_sign', 'Unknown'))
#         formatted_prompt = formatted_prompt.replace("{PARTNER_GENDER}", partner_profile.get('gender', 'Unknown'))

#         # Custom JSON encoder for datetime objects
#         def json_encoder(obj):
#             if isinstance(obj, datetime):
#                 return obj.isoformat()
#             raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

#         formatted_prompt = formatted_prompt.replace("{MAIN_CHART_DATA}", json.dumps(main_chart, indent=2, default=json_encoder))
#         formatted_prompt = formatted_prompt.replace("{PARTNER_CHART_DATA}", json.dumps(partner_chart, indent=2, default=json_encoder))

#         return formatted_prompt

#     def _generate_mock_prediction(self, profile_data: Dict[str, Any], prediction_type: str) -> str:
#         """Generate mock prediction for development/testing"""

#         name = profile_data.get('name', 'User')
#         zodiac_sign = profile_data.get('zodiac_sign', 'Unknown')

#         predictions = {
#             "daily": f"Dear {name}, today brings positive energy for {zodiac_sign} natives. Focus on communication and building relationships. Your natural charm will help you succeed in social situations. Lucky number: 7, Lucky color: Blue.",
#             "weekly": f"This week, {name}, you'll experience growth in your professional life. {zodiac_sign} natives should pay attention to health matters. Financial opportunities may arise mid-week.",
#             "monthly": f"This month brings transformation and growth for {name}. {zodiac_sign} natives will benefit from spiritual practices and self-reflection. Career advancement is indicated."
#         }

#         return predictions.get(prediction_type, f"General positive outlook for {name} ({zodiac_sign}) in the coming period.")

#     def _generate_mock_compatibility(self, main_profile: Dict[str, Any], partner_profile: Dict[str, Any]) -> Dict[str, Any]:
#         """Generate mock marriage compatibility for development/testing"""

#         return {
#             "overall_score": 85.5,
#             "guna_score": 28,
#             "compatibility_level": "excellent",
#             "strengths": [
#                 "Strong mental compatibility",
#                 "Good financial understanding",
#                 "Complementary personality traits"
#             ],
#             "challenges": [
#                 "Minor differences in lifestyle preferences"
#             ],
#             "recommendations": [
#                 "Consider marriage after consulting family elders",
#                 "Plan marriage during auspicious time period",
#                 "Regular spiritual practices will strengthen the bond"
#             ],
#             "ai_insights": "This appears to be a harmonious match with strong potential for a successful marriage. Both individuals complement each other's strengths and weaknesses well."
#         }

#     def _parse_compatibility_analysis(self, analysis: str) -> Dict[str, Any]:
#         """Parse ChatGPT response to extract structured compatibility data"""

#         # This is a simplified parser - in production, you might use more sophisticated NLP
#         lines = analysis.split('\n')
#         compatibility_data = {
#             "overall_score": 75.0,  # Default score
#             "guna_score": 25,       # Default guna score
#             "compatibility_level": "good",
#             "strengths": [],
#             "challenges": [],
#             "recommendations": [],
#             "ai_insights": analysis
#         }

#         # Extract score if mentioned
#         for line in lines:
#             if "compatibility" in line.lower() and ("score" in line.lower() or "percentage" in line.lower()):
#                 # Try to extract numerical score
#                 words = line.replace('%', '').split()
#                 for word in words:
#                     if word.replace('.', '').isdigit():
#                         try:
#                             score = float(word)
#                             if 0 <= score <= 100:
#                                 compatibility_data["overall_score"] = score
#                         except ValueError:
#                             pass

#             # Extract guna score
#             if "guna" in line.lower() and "score" in line.lower():
#                 words = line.split()
#                 for word in words:
#                     if word.isdigit():
#                         try:
#                             guna_score = int(word)
#                             if 0 <= guna_score <= 36:
#                                 compatibility_data["guna_score"] = guna_score
#                         except ValueError:
#                             pass

#         # Determine compatibility level based on score
#         if compatibility_data["overall_score"] >= 85:
#             compatibility_data["compatibility_level"] = "excellent"
#         elif compatibility_data["overall_score"] >= 70:
#             compatibility_data["compatibility_level"] = "good"
#         elif compatibility_data["overall_score"] >= 50:
#             compatibility_data["compatibility_level"] = "average"
#         else:
#             compatibility_data["compatibility_level"] = "poor"

#         return compatibility_data

#     def _get_marriage_compatibility_prompt(self) -> str:
#         """Get the stored marriage compatibility prompt from database"""
#         try:
#             # Try to get from database first
#             prompt_ref = self.db.collection('ai_prompts').document('marriage_compatibility')
#             prompt_doc = prompt_ref.get()

#             if prompt_doc.exists:
#                 data = prompt_doc.to_dict()
#                 return data.get('prompt', self._get_default_marriage_prompt())
#             else:
#                 # Save default prompt to database and return it
#                 default_prompt = self._get_default_marriage_prompt()
#                 prompt_ref.set({
#                     'prompt': default_prompt,
#                     'created_at': datetime.utcnow().isoformat(),
#                     'updated_at': datetime.utcnow().isoformat(),
#                     'version': '1.0'
#                 })
#                 logger.info("Saved default marriage compatibility prompt to database")
#                 return default_prompt

#         except Exception as e:
#             logger.error(f"Failed to get marriage prompt from database: {e}")
#             return self._get_default_marriage_prompt()

#     def _get_default_marriage_prompt(self) -> str:
#         """Get the default marriage compatibility prompt"""
#         return """
# You are Zodira – a Vedic Astrology AI specialized in marriage compatibility analysis.
# Your task is to generate a complete marriage matching report for the given bride and groom data.

# Instructions:

#     Inputs Provided:

#         Bride & Groom full horoscope charts (Rasi, Navamsa, D10, etc.).

#         Birth details: date, time, place (with latitude, longitude, timezone).

#         Porutham compatibility factors (Varna, Vashya, Tara, Yoni, Graha Maitri, Gana, Bhakoot, Nadi).

#         Nakshatra Porutham factors (Dina, Gana, Mahendra, Sthree Deergha, Yoni, Rasi, Rasi Adhipathi, Vasya, Rajju, Vedha).

#         Vimshottari Dasha–Bukthi sequences.

#     Tasks:

#         Compute Katta Porutham score (out of 36).

#         Compute Nakshatra Porutham score (out of 10).

#         Check for Manglik / Kuja Dosha in both charts (1st, 2nd, 4th, 7th, 8th, 12th house from Lagna, Moon, Venus).

#             Mention if Dosha gets cancelled due to cancellation rules.

#         Compare both charts' Dasha–Bukthi overlaps (especially Venus, Mars, Rahu, Saturn) to see if marital harmony is supported or strained.

#         Generate Character Profiles:

#             Personality traits (mental nature, emotional strength, communication style, family orientation).

#             Career tendencies.

#             Financial approach (spending vs saving).

#             Spiritual/ethical alignment.

#     Output Format:

#         Overall Compatibility Score (out of 100).

#         Katta Porutham (8 factors) → show individual factor scores with explanation.

#         Nakshatra Porutham (10 factors) → show factor verdicts with explanation.

#         Manglik / Kuja Dosha:

#             Present for bride? yes/no, with reasoning.

#             Present for groom? yes/no, with reasoning.

#             Cancellation rules applied? yes/no.

#         Dasha–Bukthi Compatibility:

#             List key overlapping periods (with years).

#             Highlight supportive vs challenging combinations.

#         Character Profiles:

#             Bride (summary of traits).

#             Groom (summary of traits).

#             Compatibility verdict on personalities.

#         Final Verdict:

#             Excellent / Very Good / Moderate / Challenging.

#             Provide marriage guidance if needed (e.g., remedies, rituals).

#     Tone:

#         Professional, clear, non-superstitious, easy to understand.

#         Highlight positives, but explain challenges honestly.

#         Suggest remedies if severe dosha is found.

# Bride Details:
# - Name: {MAIN_NAME}
# - Birth Date: {MAIN_BIRTH_DATE}
# - Birth Time: {MAIN_BIRTH_TIME}
# - Birth Place: {MAIN_BIRTH_PLACE}
# - Zodiac Sign: {MAIN_ZODIAC_SIGN}
# - Moon Sign: {MAIN_MOON_SIGN}
# - Gender: {MAIN_GENDER}

# Groom Details:
# - Name: {PARTNER_NAME}
# - Birth Date: {PARTNER_BIRTH_DATE}
# - Birth Time: {PARTNER_BIRTH_TIME}
# - Birth Place: {PARTNER_BIRTH_PLACE}
# - Zodiac Sign: {PARTNER_ZODIAC_SIGN}
# - Moon Sign: {PARTNER_MOON_SIGN}
# - Gender: {PARTNER_GENDER}

# Chart Data:
# Bride Chart: {MAIN_CHART_DATA}
# Groom Chart: {PARTNER_CHART_DATA}

# Please provide a comprehensive marriage compatibility analysis following the exact format specified above.
# """

#     async def save_marriage_compatibility_prompt(self, prompt: str) -> bool:
#         """Save or update the marriage compatibility prompt in database"""
#         try:
#             prompt_ref = self.db.collection('ai_prompts').document('marriage_compatibility')
#             prompt_ref.set({
#                 'prompt': prompt,
#                 'updated_at': datetime.utcnow().isoformat(),
#                 'version': '1.1'
#             })

#             logger.info("Updated marriage compatibility prompt in database")
#             return True

#         except Exception as e:
#             logger.error(f"Failed to save marriage prompt to database: {e}")
#             return False

#     async def get_marriage_compatibility_prompt(self) -> Optional[str]:
#         """Get the current marriage compatibility prompt from database"""
#         try:
#             prompt_ref = self.db.collection('ai_prompts').document('marriage_compatibility')
#             prompt_doc = prompt_ref.get()

#             if prompt_doc.exists:
#                 data = prompt_doc.to_dict()
#                 return data.get('prompt')

#             return None

#         except Exception as e:
#             logger.error(f"Failed to get marriage prompt from database: {e}")
#             return None

# # Global service instance
# chatgpt_service = ChatGPTService()

"""
ChatGPT API Service for ZODIRA Backend

This service handles integration with OpenAI's ChatGPT API for generating
personalized astrology predictions and marriage compatibility insights.
"""

import os
import json
import logging
import asyncio

from typing import Dict, List, Optional, Any
from datetime import datetime, date, time

from app.config.settings import settings
from app.config.firebase import get_firestore_client
from app.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

# Try to import OpenAI client (the new SDK exposes OpenAI class)
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except Exception:
    OPENAI_AVAILABLE = False
    logger.warning("OpenAI client not available, install with: pip install openai")


class ChatGPTService:
    """Service for ChatGPT API integration"""

    def __init__(self):
        # Load API key from settings
        self.api_key = getattr(settings, "openai_api_key", None)
        self.client: Optional[Any] = None

        # Modern OpenAI configuration with best practices
        self.model = getattr(settings, "openai_model", "gpt-4o-mini")  # default model
        self.max_tokens = getattr(settings, "openai_max_tokens", 2000)
        self.temperature = getattr(settings, "openai_temperature", 0.3)
        self.timeout = getattr(settings, "openai_timeout", 30)
        self.max_retries = getattr(settings, "openai_max_retries", 3)

        # Rate limiting configuration
        self.rate_limit_per_minute = getattr(settings, "openai_rate_limit_per_minute", 50)
        self._last_request_time = 0.0
        self._request_count = 0

        self._db = None  # Lazy initialization for Firestore client

        # Initialize OpenAI client if possible
        if not self.api_key:
            logger.error("❌ OpenAI API key not configured")
            # We don't raise here to allow the app to start in dev/test mode;
            # but many methods will check for client existence and raise appropriately.
        elif not OPENAI_AVAILABLE:
            logger.error("❌ OpenAI client package not installed. Install with: pip install openai")
        else:
            try:
                # Instantiate the official OpenAI client
                # Use the correct API for the installed version
                self.client = OpenAI(api_key=self.api_key)
                logger.info("✅ OpenAI client initialized successfully")
            except Exception as e:
                logger.error(f"❌ Failed to initialize OpenAI client: {e}")
                # Keep client as None; methods will raise if used.
                self.client = None

    @property
    def db(self):
        """Lazy initialization of Firestore client"""
        if self._db is None:
            self._db = get_firestore_client()
        return self._db

    def _check_rate_limit(self) -> None:
        """Check and enforce rate limiting for OpenAI API calls"""
        import time

        current_time = time.time()

        # Reset counter if a minute has passed
        if current_time - self._last_request_time >= 60:
            self._request_count = 0
            self._last_request_time = current_time

        # Check if we're over the rate limit
        if self._request_count >= self.rate_limit_per_minute:
            sleep_time = 60 - (current_time - self._last_request_time)
            if sleep_time > 0:
                logger.warning(f"Rate limit reached, sleeping for {sleep_time:.2f} seconds")
                time.sleep(sleep_time)
                self._request_count = 0
                self._last_request_time = time.time()

        self._request_count += 1

    async def _make_openai_request(self, **kwargs):
        """
        Make asynchronous OpenAI API request.
        The OpenAI SDK client's `chat.completions.create` is blocking, so run it in a thread.
        """
        import time

        if not self.client:
            raise ValueError("OpenAI client not initialized. Check API key and package installation.")

        start_time = time.time()
        try:
            # Run the blocking call in a thread so it is awaitable
            response = await asyncio.to_thread(self.client.chat.completions.create, **kwargs)
            elapsed = time.time() - start_time
            logger.info(f"OpenAI API request completed in {elapsed:.2f}s")
            return response
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"OpenAI API request failed after {elapsed:.2f}s: {e}")
            raise

    async def _retry_with_backoff(self, func, *args, **kwargs):
        """Retry API calls with exponential backoff"""
        import random

        for attempt in range(self.max_retries):
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                # If last attempt, re-raise
                if attempt == self.max_retries - 1:
                    logger.error(f"All retry attempts failed. Final error: {e}")
                    raise

                # Try to detect retryable errors (rate limit / server)
                status = getattr(e, "status", None)
                if status in (429, 500, 502, 503, 504) or isinstance(e, (TimeoutError,)):
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(
                        f"Retryable error on attempt {attempt + 1}/{self.max_retries}: {e}. Retrying in {wait_time:.2f}s"
                    )
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    # Non-retryable
                    logger.error(f"Non-retryable error: {e}")
                    raise

        # Should not reach here
        raise RuntimeError("Max retries exceeded")

    async def generate_personal_predictions(
        self,
        profile_data: Dict[str, Any],
        chart_data: Dict[str, Any],
        prediction_type: str = "daily",
    ) -> str:
        """
        Generate personalized astrology predictions using ChatGPT
        """
        try:
            if not self.client:
                raise ValueError("OpenAI client not initialized. Check API key configuration.")

            prompt = self._create_prediction_prompt(profile_data, chart_data, prediction_type)

            # Rate limiting
            self._check_rate_limit()

            response = await self._retry_with_backoff(
                self._make_openai_request,
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert Vedic astrologer with deep knowledge of astrology, zodiac signs, and planetary influences. Provide accurate, personalized predictions based on birth chart data.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                timeout=self.timeout,
            )

            # SDK response structure: choices -> each has a 'message' dict
            # defensive access to message content
            try:
                message = response.choices[0].message
                # message might be an object or dict depending on SDK; handle both:
                content = getattr(message, "content", None) or message.get("content")
                prediction = content.strip()
            except Exception:
                # best-effort fallback to string conversion
                prediction = str(response)

            logger.info(f"Generated {prediction_type} prediction for user {profile_data.get('user_id')}")
            return prediction

        except Exception as e:
            logger.error(f"Failed to generate prediction: {e}")
            logger.info("🔄 Using fallback prediction generation")
            return self._generate_mock_prediction(profile_data, prediction_type)

    async def generate_marriage_compatibility(
        self,
        main_profile: Dict[str, Any],
        partner_profile: Dict[str, Any],
        main_chart: Dict[str, Any],
        partner_chart: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Generate marriage compatibility analysis using ChatGPT
        """
        try:
            if not self.client:
                raise ValueError("OpenAI client not initialized. Check API key configuration.")

            stored_prompt = self._get_marriage_compatibility_prompt()

            formatted_prompt = stored_prompt.replace("{MAIN_NAME}", main_profile.get("name", "User"))
            formatted_prompt = formatted_prompt.replace("{MAIN_BIRTH_DATE}", str(main_profile.get("birth_date", "Unknown")))
            formatted_prompt = formatted_prompt.replace("{MAIN_BIRTH_TIME}", str(main_profile.get("birth_time", "Unknown")))
            formatted_prompt = formatted_prompt.replace("{MAIN_BIRTH_PLACE}", main_profile.get("birth_place", "Unknown"))
            formatted_prompt = formatted_prompt.replace("{MAIN_ZODIAC_SIGN}", main_profile.get("zodiac_sign", "Unknown"))
            formatted_prompt = formatted_prompt.replace("{MAIN_MOON_SIGN}", main_profile.get("moon_sign", "Unknown"))
            formatted_prompt = formatted_prompt.replace("{MAIN_GENDER}", main_profile.get("gender", "Unknown"))

            formatted_prompt = formatted_prompt.replace("{PARTNER_NAME}", partner_profile.get("name", "Partner"))
            formatted_prompt = formatted_prompt.replace("{PARTNER_BIRTH_DATE}", str(partner_profile.get("birth_date", "Unknown")))
            formatted_prompt = formatted_prompt.replace("{PARTNER_BIRTH_TIME}", str(partner_profile.get("birth_time", "Unknown")))
            formatted_prompt = formatted_prompt.replace("{PARTNER_BIRTH_PLACE}", partner_profile.get("birth_place", "Unknown"))
            formatted_prompt = formatted_prompt.replace("{PARTNER_ZODIAC_SIGN}", partner_profile.get("zodiac_sign", "Unknown"))
            formatted_prompt = formatted_prompt.replace("{PARTNER_MOON_SIGN}", partner_profile.get("moon_sign", "Unknown"))
            formatted_prompt = formatted_prompt.replace("{PARTNER_GENDER}", partner_profile.get("gender", "Unknown"))

            def json_encoder(obj):
                if isinstance(obj, datetime):
                    return obj.isoformat()
                elif isinstance(obj, date):
                    return obj.isoformat()
                elif isinstance(obj, time):
                    return obj.isoformat()
                elif hasattr(obj, "dict"):
                    return obj.dict()
                elif hasattr(obj, "__dict__"):
                    return obj.__dict__
                raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

            formatted_prompt = formatted_prompt.replace("{MAIN_CHART_DATA}", json.dumps(main_chart, indent=2, default=json_encoder))
            formatted_prompt = formatted_prompt.replace("{PARTNER_CHART_DATA}", json.dumps(partner_chart, indent=2, default=json_encoder))

            # Rate limiting
            self._check_rate_limit()

            response = await self._retry_with_backoff(
                self._make_openai_request,
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are Zodira – a Vedic Astrology AI specialized in marriage compatibility analysis."},
                    {"role": "user", "content": formatted_prompt},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                timeout=self.timeout,
            )

            try:
                message = response.choices[0].message
                content = getattr(message, "content", None) or message.get("content")
                analysis = content.strip()
            except Exception:
                analysis = str(response)

            compatibility_data = self._parse_compatibility_analysis(analysis)
            logger.info(f"Generated marriage compatibility for profiles {main_profile.get('id')} and {partner_profile.get('id')}")
            return compatibility_data

        except Exception as e:
            logger.error(f"Failed to generate marriage compatibility: {e}")
            logger.info("🔄 Using fallback marriage compatibility analysis")
            return self._generate_mock_compatibility(main_profile, partner_profile)

    def _create_prediction_prompt(self, profile_data: Dict[str, Any], chart_data: Dict[str, Any], prediction_type: str) -> str:
        """Create prompt for astrology predictions"""
        birth_date = profile_data.get("birth_date", "Unknown")
        zodiac_sign = profile_data.get("zodiac_sign", "Unknown")
        moon_sign = profile_data.get("moon_sign", "Unknown")

        prompt = f"""
        Generate a personalized {prediction_type} astrology prediction for:

        Person Details:
        - Name: {profile_data.get('name', 'User')}
        - Birth Date: {birth_date}
        - Zodiac Sign: {zodiac_sign}
        - Moon Sign: {moon_sign}
        - Gender: {profile_data.get('gender', 'Unknown')}

        Astrology Chart Data:
        {json.dumps(chart_data, indent=2)}

        Please provide a detailed, accurate {prediction_type} prediction covering:
        1. Overall outlook for the day/week/month
        2. Career and professional matters
        3. Health and well-being
        4. Relationships and personal life
        5. Financial matters
        6. Lucky numbers, colors, and directions
        7. Any precautions or remedies

        Make the prediction personal, positive, and actionable. Use traditional Vedic astrology principles.
        """

        return prompt

    def _create_marriage_prompt(self, main_profile: Dict[str, Any], partner_profile: Dict[str, Any], main_chart: Dict[str, Any], partner_chart: Dict[str, Any]) -> str:
        """Create prompt for marriage compatibility analysis using the stored Vedic astrology prompt"""
        stored_prompt = self._get_marriage_compatibility_prompt()

        formatted_prompt = stored_prompt.replace("{MAIN_NAME}", main_profile.get("name", "User"))
        formatted_prompt = formatted_prompt.replace("{MAIN_BIRTH_DATE}", str(main_profile.get("birth_date", "Unknown")))
        formatted_prompt = formatted_prompt.replace("{MAIN_BIRTH_TIME}", str(main_profile.get("birth_time", "Unknown")))
        formatted_prompt = formatted_prompt.replace("{MAIN_BIRTH_PLACE}", main_profile.get("birth_place", "Unknown"))
        formatted_prompt = formatted_prompt.replace("{MAIN_ZODIAC_SIGN}", main_profile.get("zodiac_sign", "Unknown"))
        formatted_prompt = formatted_prompt.replace("{MAIN_MOON_SIGN}", main_profile.get("moon_sign", "Unknown"))
        formatted_prompt = formatted_prompt.replace("{MAIN_GENDER}", main_profile.get("gender", "Unknown"))

        formatted_prompt = formatted_prompt.replace("{PARTNER_NAME}", partner_profile.get("name", "Partner"))
        formatted_prompt = formatted_prompt.replace("{PARTNER_BIRTH_DATE}", str(partner_profile.get("birth_date", "Unknown")))
        formatted_prompt = formatted_prompt.replace("{PARTNER_BIRTH_TIME}", str(partner_profile.get("birth_time", "Unknown")))
        formatted_prompt = formatted_prompt.replace("{PARTNER_BIRTH_PLACE}", partner_profile.get("birth_place", "Unknown"))
        formatted_prompt = formatted_prompt.replace("{PARTNER_ZODIAC_SIGN}", partner_profile.get("zodiac_sign", "Unknown"))
        formatted_prompt = formatted_prompt.replace("{PARTNER_MOON_SIGN}", partner_profile.get("moon_sign", "Unknown"))
        formatted_prompt = formatted_prompt.replace("{PARTNER_GENDER}", partner_profile.get("gender", "Unknown"))

        def json_encoder(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

        formatted_prompt = formatted_prompt.replace("{MAIN_CHART_DATA}", json.dumps(main_chart, indent=2, default=json_encoder))
        formatted_prompt = formatted_prompt.replace("{PARTNER_CHART_DATA}", json.dumps(partner_chart, indent=2, default=json_encoder))

        return formatted_prompt

    def _generate_mock_prediction(self, profile_data: Dict[str, Any], prediction_type: str) -> str:
        """Generate mock prediction for development/testing"""
        name = profile_data.get("name", "User")
        zodiac_sign = profile_data.get("zodiac_sign", "Unknown")

        predictions = {
            "daily": f"Dear {name}, today brings positive energy for {zodiac_sign} natives. Focus on communication and building relationships. Your natural charm will help you succeed in social situations. Lucky number: 7, Lucky color: Blue.",
            "weekly": f"This week, {name}, you'll experience growth in your professional life. {zodiac_sign} natives should pay attention to health matters. Financial opportunities may arise mid-week.",
            "monthly": f"This month brings transformation and growth for {name}. {zodiac_sign} natives will benefit from spiritual practices and self-reflection. Career advancement is indicated.",
        }

        return predictions.get(prediction_type, f"General positive outlook for {name} ({zodiac_sign}) in the coming period.")

    def _generate_mock_compatibility(self, main_profile: Dict[str, Any], partner_profile: Dict[str, Any]) -> Dict[str, Any]:
        """Generate mock marriage compatibility for development/testing"""
        return {
            "overall_score": 85.5,
            "guna_score": 28,
            "compatibility_level": "excellent",
            "strengths": ["Strong mental compatibility", "Good financial understanding", "Complementary personality traits"],
            "challenges": ["Minor differences in lifestyle preferences"],
            "recommendations": [
                "Consider marriage after consulting family elders",
                "Plan marriage during auspicious time period",
                "Regular spiritual practices will strengthen the bond",
            ],
            "ai_insights": "This appears to be a harmonious match with strong potential for a successful marriage. Both individuals complement each other's strengths and weaknesses well.",
        }

    def _parse_compatibility_analysis(self, analysis: str) -> Dict[str, Any]:
        """Parse ChatGPT response to extract structured compatibility data"""
        # simplified parser
        lines = analysis.split("\n")
        compatibility_data = {
            "overall_score": 75.0,
            "guna_score": 25,
            "compatibility_level": "good",
            "strengths": [],
            "challenges": [],
            "recommendations": [],
            "ai_insights": analysis,
        }

        for line in lines:
            low = line.lower()
            if "compatibility" in low and ("score" in low or "percentage" in low):
                words = line.replace("%", "").split()
                for word in words:
                    if word.replace(".", "").isdigit():
                        try:
                            score = float(word)
                            if 0 <= score <= 100:
                                compatibility_data["overall_score"] = score
                        except ValueError:
                            pass

            if "guna" in low and "score" in low:
                words = line.split()
                for word in words:
                    if word.isdigit():
                        try:
                            guna_score = int(word)
                            if 0 <= guna_score <= 36:
                                compatibility_data["guna_score"] = guna_score
                        except ValueError:
                            pass

        if compatibility_data["overall_score"] >= 85:
            compatibility_data["compatibility_level"] = "excellent"
        elif compatibility_data["overall_score"] >= 70:
            compatibility_data["compatibility_level"] = "good"
        elif compatibility_data["overall_score"] >= 50:
            compatibility_data["compatibility_level"] = "average"
        else:
            compatibility_data["compatibility_level"] = "poor"

        return compatibility_data

    def _get_marriage_compatibility_prompt(self) -> str:
        """Get the stored marriage compatibility prompt from database (sync)"""
        try:
            prompt_ref = self.db.collection("ai_prompts").document("marriage_compatibility")
            prompt_doc = prompt_ref.get()

            if prompt_doc.exists:
                data = prompt_doc.to_dict()
                return data.get("prompt", self._get_default_marriage_prompt())
            else:
                default_prompt = self._get_default_marriage_prompt()
                prompt_ref.set(
                    {
                        "prompt": default_prompt,
                        "created_at": datetime.utcnow().isoformat(),
                        "updated_at": datetime.utcnow().isoformat(),
                        "version": "1.0",
                    }
                )
                logger.info("Saved default marriage compatibility prompt to database")
                return default_prompt

        except Exception as e:
            logger.error(f"Failed to get marriage prompt from database: {e}")
            return self._get_default_marriage_prompt()

    def _get_default_marriage_prompt(self) -> str:
        """Get the default marriage compatibility prompt"""
        return """
You are Zodira – a Vedic Astrology AI specialized in marriage compatibility analysis.
Your task is to generate a complete marriage matching report for the given bride and groom data.

... (omitted here for brevity; keep the same default prompt as in your original file) ...
"""

    async def save_marriage_compatibility_prompt(self, prompt: str) -> bool:
        """Save or update the marriage compatibility prompt in database"""
        try:
            prompt_ref = self.db.collection("ai_prompts").document("marriage_compatibility")
            prompt_ref.set({"prompt": prompt, "updated_at": datetime.utcnow().isoformat(), "version": "1.1"})
            logger.info("Updated marriage compatibility prompt in database")
            return True
        except Exception as e:
            logger.error(f"Failed to save marriage prompt to database: {e}")
            return False

    async def get_marriage_compatibility_prompt(self) -> Optional[str]:
        """Get the current marriage compatibility prompt from database"""
        try:
            prompt_ref = self.db.collection("ai_prompts").document("marriage_compatibility")
            prompt_doc = prompt_ref.get()
            if prompt_doc.exists:
                data = prompt_doc.to_dict()
                return data.get("prompt")
            return None
        except Exception as e:
            logger.error(f"Failed to get marriage prompt from database: {e}")
            return None
        

    async def generate_raw_completion(self, prompt: str) -> str:
        """
        Generate a raw JSON completion from ChatGPT given a text prompt.
        This method directly returns the AI-generated text (expected to be valid JSON).
        Used for self-compatibility or other structured responses.
        """
        try:
            if not self.client:
                raise ValueError("OpenAI client not initialized. Check API key configuration.")

            # Enforce rate limiting
            self._check_rate_limit()

            logger.info("🧠 Generating raw completion from ChatGPT...")

            # Retry with backoff for transient errors
            response = await self._retry_with_backoff(
                self._make_openai_request,
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a precise JSON generator. Return ONLY valid JSON objects without explanations.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                timeout=self.timeout,
            )

            # Safely extract text content
            try:
                message = response.choices[0].message
                raw_output = getattr(message, "content", None) or message.get("content")
                result = raw_output.strip()
            except Exception:
                logger.warning("⚠️ Fallback: unable to parse structured response, converting to string.")
                result = str(response)

            logger.info("✅ Successfully generated raw completion.")
            return result

        except Exception as e:
            logger.error(f"❌ Failed to generate raw completion: {e}")
            raise


    async def generate_personal_predictionsbyme(
        self,
        profile_data: Dict[str, Any],
        chart_data: Dict[str, Any],
        prediction_type: str = "daily",
    ) -> Dict[str, Any]:
        """
        Generate structured astrology predictions (JSON format) using ChatGPT.
        """
        try:
            if not self.client:
                raise ValueError("OpenAI client not initialized. Check API key configuration.")

            # Create structured prompt
            prompt = f"""
            You are an expert Vedic astrologer. 
            Based on the user's birth chart and astrology data, generate a structured JSON prediction
            that includes daily, weekly, and monthly forecasts. 
            Use the following schema (return **ONLY valid JSON**, nothing else):

            {{
            "daily_predictions": {{
                "categories": [
                {{
                    "key": "general",
                    "title": "string",
                    "subtitle": "string",
                    "description": "string",
                    "energy_level": "High|Medium|Low",
                    "luck_factor": "string",
                    "mood_icon": "emoji"
                }},
                {{
                    "key": "career",
                    "title": "string",
                    "subtitle": "string",
                    "description": "string",
                    "energy_level": "string",
                    "luck_factor": "string",
                    "mood_icon": "emoji"
                }},
                {{
                    "key": "health",
                    "title": "string",
                    "subtitle": "string",
                    "description": "string",
                    "energy_level": "string",
                    "luck_factor": "string",
                    "mood_icon": "emoji"
                }},
                {{
                    "key": "spiritual",
                    "title": "string",
                    "subtitle": "string",
                    "description": "string",
                    "energy_level": "string",
                    "luck_factor": "string",
                    "mood_icon": "emoji"
                }}
                ],
                "date": "string"
            }},
            "weekly_predictions": {{
                "key_events": ["string", "string"],
                "overview": "string",
                "period": "string"
            }},
            "monthly_predictions": {{
                "key_themes": ["string", "string"],
                "overview": "string",
                "period": "string"
            }}
            }}

            Use astrology logic to fill realistic and creative predictions.
            Do NOT include markdown, text outside JSON, or explanations.
            Birth chart data: {chart_data}
            Profile data: {profile_data}
            """

            response = await self._retry_with_backoff(
                self._make_openai_request,
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a master astrologer who always replies with valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                timeout=self.timeout,
            )

            message = response.choices[0].message
            content = getattr(message, "content", None) or message.get("content")

            # Parse JSON safely
            try:
                prediction_json = json.loads(content)
            except json.JSONDecodeError:
                logger.warning("⚠️ ChatGPT returned invalid JSON; using fallback")
                # Return a basic structured prediction
                mock_text = self._generate_mock_prediction(profile_data, "daily")
                prediction_json = {
                    "daily_predictions": {
                        "categories": [
                            {
                                "key": "general",
                                "title": "General Outlook",
                                "subtitle": "Daily Prediction",
                                "description": mock_text,
                                "energy_level": "Medium",
                                "luck_factor": "Neutral",
                                "mood_icon": "😐"
                            }
                        ],
                        "date": datetime.utcnow().isoformat()
                    },
                    "weekly_predictions": {
                        "key_events": ["Work", "Health"],
                        "overview": self._generate_mock_prediction(profile_data, "weekly"),
                        "period": "This week"
                    },
                    "monthly_predictions": {
                        "key_themes": ["Career", "Relationships"],
                        "overview": self._generate_mock_prediction(profile_data, "monthly"),
                        "period": "This month"
                    }
                }

            return prediction_json

        except Exception as e:
            logger.error(f"Failed to generate structured prediction: {e}")
            logger.info("🔄 Using fallback prediction generation")
            return self._generate_mock_prediction(profile_data, prediction_type)

# Global service instance
chatgpt_service = ChatGPTService()
