from pydantic_settings import BaseSettings
from decouple import config
from typing import List
import secrets
import logging


logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    # Firebase Configuration
    firebase_project_id: str = config('FIREBASE_PROJECT_ID', default='your-firebase-project-id')
    firebase_storage_bucket: str = config('FIREBASE_STORAGE_BUCKET', default='your-firebase-project-id.appspot.com')

    # Application Settings
    app_name: str = "ZODIRA Backend"
    app_version: str = "1.0.0"
    debug: bool = config('APP_DEBUG', default=False, cast=bool)
    environment: str = config('ENVIRONMENT', default='development')

    # Security Configuration
    secret_key: str = config('SECRET_KEY', default='dev-secret-key-change-in-production-min-32-chars')
    algorithm: str = "HS256"
    access_token_expire_minutes: int = config('ACCESS_TOKEN_EXPIRE_MINUTES', default=43200, cast=int)
    
    # CORS Configuration
    allowed_origins: List[str] = config(
        'ALLOWED_ORIGINS',
        default='*',
        cast=lambda v: [s.strip() for s in v.split(',')] if v != '*' else ['*']
    )
    
    # Rate Limiting
    rate_limit_requests: int = config('RATE_LIMIT_REQUESTS', default=100, cast=int)
    rate_limit_window: int = config('RATE_LIMIT_WINDOW', default=60, cast=int)
    
    # SMS Configuration
    sms_provider: str = config('SMS_PROVIDER', default='mydreams')
    mydreams_api_url: str = config('MYDREAMS_API_URL', default='http://app.mydreamstechnology.in/vb/apikey.php')
    mydreams_api_key: str = config('MYDREAMS_API_KEY', default='zbAG4xSPKhwqPCI3')
    mydreams_sender_id: str = config('MYDREAMS_SENDER_ID', default='MYDTEH')
    
    # Google OAuth Configuration
    google_client_id: str = config('GOOGLE_CLIENT_ID', default='')
    google_client_secret: str = config('GOOGLE_CLIENT_SECRET', default='')
    redirect_uri: str = config('REDIRECT_URI', default='')
    frontend_url: str = config('FRONTEND_URL', default='*')

    # Twilio Configuration (fallback)
    twilio_account_sid: str = config('TWILIO_ACCOUNT_SID', default='')
    twilio_auth_token: str = config('TWILIO_AUTH_TOKEN', default='')
    twilio_phone_number: str = config('TWILIO_PHONE_NUMBER', default='')
    
    # Application Contact Information
    zodira_support_email: str = config('ZODIRA_SUPPORT_EMAIL', default='enijerry0@gmail.com')

    # Astrology API Configuration
    free_astrology_api_key: str = config('FREE_ASTRO_API_KEY', default='')
    astro_api_key: str = config('ASTRO_API_KEY', default='')

    # OpenAI ChatGPT Configuration
    openai_api_key: str = config('OPENAI_API_KEY', default='')
    openai_model: str = config('OPENAI_MODEL', default='gpt-5-chat-latest')
    openai_max_tokens: int = config('OPENAI_MAX_TOKENS', default=2000, cast=int)
    openai_temperature: float = config('OPENAI_TEMPERATURE', default=0.3, cast=float)
    openai_timeout: int = config('OPENAI_TIMEOUT', default=30, cast=int)
    openai_max_retries: int = config('OPENAI_MAX_RETRIES', default=3, cast=int)
    openai_rate_limit_per_minute: int = config('OPENAI_RATE_LIMIT_PER_MINUTE', default=50, cast=int)

    # ========================================
    # 💰 RAZORPAY PAYMENT GATEWAY CONFIGURATION
    # ========================================
    razorpay_key_id: str = config('RAZORPAY_KEY_ID', default='')
    razorpay_key_secret: str = config('RAZORPAY_KEY_SECRET', default='')
    razorpay_webhook_secret: str = config('RAZORPAY_WEBHOOK_SECRET', default='')
    
    # Payment Configuration
    payment_min_amount: float = config('PAYMENT_MIN_AMOUNT', default=10.0, cast=float)
    payment_max_amount: float = config('PAYMENT_MAX_AMOUNT', default=100000.0, cast=float)
    payment_currency: str = config('PAYMENT_CURRENCY', default='INR')
    
    # Wallet Configuration
    wallet_enabled: bool = config('WALLET_ENABLED', default=True, cast=bool)
    wallet_bonus_on_first_add: float = config('WALLET_BONUS_ON_FIRST_ADD', default=0.0, cast=float)
    
    # Client/Frontend Configuration
    api_base_url: str = config('API_BASE_URL', default='')
    
    # Logging Configuration
    log_level: str = config('LOG_LEVEL', default='INFO')
    log_format: str = config('LOG_FORMAT', default='json')
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._validate_security_settings()
    
    def _validate_security_settings(self):
        """Validate critical security settings"""
        # Generate secure secret key if using default
        if not self.secret_key or self.secret_key in ['your-secret-key-here', 'dev-secret-key-change-in-production-min-32-chars']:
            if self.environment == 'production':
                logger.critical("SECURITY ALERT: Default SECRET_KEY used in production!")
                raise ValueError("SECRET_KEY must be set to a secure value in production environment")
            else:
                self.secret_key = secrets.token_urlsafe(32)
                logger.warning(f"Generated secure SECRET_KEY for {self.environment} environment")
        
        # Validate Firebase configuration
        if self.firebase_project_id == 'your-firebase-project-id':
            logger.warning("Firebase project ID not configured - using default")
        
        # Validate Razorpay configuration
        if not self.razorpay_key_id or not self.razorpay_key_secret:
            logger.warning("⚠️ Razorpay credentials not configured - payment features will be disabled")
        else:
            logger.info("✅ Razorpay payment gateway configured")
            
        if not self.razorpay_webhook_secret and self.environment == 'production':
            logger.warning("⚠️ Razorpay webhook secret not set in production - webhook verification will fail")
        
        # Validate CORS origins
        if '*' in self.allowed_origins:
            logger.info("Wildcard CORS origin enabled for all environments")
        
        # Google OAuth optional
        if not self.google_client_id or not self.google_client_secret or not self.redirect_uri:
            logger.info("Google OAuth not fully configured; endpoints relying on Google OAuth will be inactive")

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


# Global settings instance
settings = Settings()
