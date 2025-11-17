# from fastapi import APIRouter, HTTPException, Depends, Header, Request
# from pydantic import BaseModel, validator
# from typing import Optional, Dict, Any
# import logging
# from datetime import datetime

# from app.services.razorpay_service import razorpay_service
# from app.core.dependencies import get_current_user
# from app.models.payment import PaymentStatus, TransactionType
# from app.config.settings import settings

# logger = logging.getLogger(__name__)

# router = APIRouter()


# # Request Models
# class CreateOrderRequest(BaseModel):
#     """Request to create a payment order"""
#     amount: float
#     currency: Optional[str] = None
#     notes: Optional[Dict[str, Any]] = None

#     @validator('amount')
#     def validate_amount(cls, v):
#         if v <= 0:
#             raise ValueError('Amount must be greater than 0')
#         if v < settings.payment_min_amount:
#             raise ValueError(f'Minimum amount is ₹{settings.payment_min_amount}')
#         if v > settings.payment_max_amount:
#             raise ValueError(f'Maximum amount is ₹{settings.payment_max_amount}')
#         return v


# class VerifyPaymentRequest(BaseModel):
#     """Request to verify payment"""
#     transaction_id: str
#     razorpay_payment_id: str
#     razorpay_order_id: str
#     razorpay_signature: str

#     @validator('transaction_id', 'razorpay_payment_id', 'razorpay_order_id', 'razorpay_signature')
#     def validate_not_empty(cls, v):
#         if not v or not v.strip():
#             raise ValueError('Field cannot be empty')
#         return v.strip()


# # API Endpoints

# @router.get("/config")
# async def get_payment_config():
#     """
#     Get payment configuration for frontend
#     Returns payment limits and currency settings
#     """
#     return {
#         "enabled": settings.wallet_enabled and razorpay_service.is_enabled,
#         "currency": settings.payment_currency,
#         "limits": {
#             "min": settings.payment_min_amount,
#             "max": settings.payment_max_amount
#         },
#         "features": {
#             "wallet": settings.wallet_enabled,
#             "first_add_bonus": settings.wallet_bonus_on_first_add
#         }
#     }


# @router.post("/create-order")
# async def create_payment_order(
#     request: CreateOrderRequest,
#     current_user: str = Depends(get_current_user)
# ):
#     """
#     Create a Razorpay order for adding money to wallet
    
#     Security: Requires authentication
#     Validates amount against configured limits
#     """
#     try:
#         if not razorpay_service.is_enabled:
#             raise HTTPException(
#                 status_code=503, 
#                 detail="Payment service is currently unavailable"
#             )
        
#         logger.info(f"💳 Creating payment order for user: {current_user}, amount: ₹{request.amount}")
        
#         order_data = await razorpay_service.create_order(
#             amount=request.amount,
#             user_id=current_user,
#             currency=request.currency,
#             notes=request.notes
#         )
        
#         return {
#             "success": True,
#             "order": order_data,
#             "message": "Order created successfully"
#         }
        
#     except ValueError as ve:
#         raise HTTPException(status_code=400, detail=str(ve))
#     except Exception as e:
#         logger.error(f"❌ Order creation failed: {e}")
#         raise HTTPException(status_code=500, detail=str(e))


# @router.post("/verify-payment")
# async def verify_payment(
#     request: VerifyPaymentRequest,
#     current_user: str = Depends(get_current_user)
# ):
#     """
#     Verify and capture payment after successful transaction
    
#     Security: 
#     - Verifies payment signature using HMAC SHA256
#     - Validates user ownership of transaction
#     - Prevents duplicate processing
#     """
#     try:
#         if not razorpay_service.is_enabled:
#             raise HTTPException(
#                 status_code=503,
#                 detail="Payment service is currently unavailable"
#             )
        
#         logger.info(f"🔐 Verifying payment for user: {current_user}")
        
#         result = await razorpay_service.capture_payment(
#             transaction_id=request.transaction_id,
#             razorpay_payment_id=request.razorpay_payment_id,
#             razorpay_order_id=request.razorpay_order_id,
#             razorpay_signature=request.razorpay_signature,
#             user_id=current_user
#         )
        
#         response_message = "Payment verified and wallet updated"
#         if result.get("bonus", 0) > 0:
#             response_message += f" 🎁 Bonus: ₹{result['bonus']}"
        
#         return {
#             "success": True,
#             "message": response_message,
#             **result
#         }
        
#     except Exception as e:
#         logger.error(f"❌ Payment verification failed: {e}")
#         raise HTTPException(status_code=400, detail=str(e))


# @router.get("/wallet/balance")
# async def get_wallet_balance(current_user: str = Depends(get_current_user)):
#     """Get current wallet balance for the authenticated user"""
#     try:
#         balance = await razorpay_service.get_wallet_balance(current_user)
        
#         return {
#             "user_id": current_user,
#             "balance": balance,
#             "currency": settings.payment_currency,
#             "formatted": f"₹{balance:.2f}"
#         }
        
#     except Exception as e:
#         logger.error(f"❌ Failed to get wallet balance: {e}")
#         raise HTTPException(status_code=500, detail="Failed to fetch wallet balance")


# @router.get("/wallet/transactions")
# async def get_transaction_history(
#     limit: int = 50,
#     current_user: str = Depends(get_current_user)
# ):
#     """
#     Get transaction history for the authenticated user
    
#     Query params:
#     - limit: Number of transactions (default: 50, max: 100)
#     """
#     try:
#         if limit > 100:
#             limit = 100
            
#         transactions = await razorpay_service.get_transaction_history(
#             user_id=current_user,
#             limit=limit
#         )
        
#         return {
#             "user_id": current_user,
#             "transactions": transactions,
#             "count": len(transactions),
#             "currency": settings.payment_currency
#         }
        
#     except Exception as e:
#         logger.error(f"❌ Failed to get transaction history: {e}")
#         raise HTTPException(status_code=500, detail="Failed to fetch transactions")


# @router.post("/webhook")
# async def handle_razorpay_webhook(
#     request: Request,
#     x_razorpay_signature: str = Header(None)
# ):
#     """
#     Handle Razorpay webhook events securely
    
#     Security: Validates webhook signature before processing
#     Events: payment.captured, payment.failed, refund.created
#     """
#     try:
#         if not razorpay_service.is_enabled:
#             raise HTTPException(status_code=503, detail="Payment service unavailable")
        
#         body = await request.json()
        
#         if not x_razorpay_signature:
#             raise HTTPException(status_code=400, detail="Missing signature")
        
#         await razorpay_service.process_webhook(body, x_razorpay_signature)
        
#         return {"status": "success"}
        
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"❌ Webhook processing failed: {e}")
#         raise HTTPException(status_code=500, detail="Webhook processing failed")


# @router.get("/health")
# async def payment_health_check():
#     """Health check for payment service"""
#     return {
#         "status": "healthy" if razorpay_service.is_enabled else "disabled",
#         "service": "payment",
#         "provider": "razorpay",
#         "app": settings.app_name,
#         "version": settings.app_version,
#         "environment": settings.environment,
#         "timestamp": datetime.utcnow().isoformat()
#     }
