# import razorpay
# import hmac
# import hashlib
# import logging
# from typing import Dict, Optional
# from datetime import datetime
# from app.config.settings import settings
# from app.config.firebase import get_firestore_client
# from app.models.payment import WalletTransaction, UserWallet, PaymentStatus, TransactionType
# import uuid

# logger = logging.getLogger(__name__)


# class RazorpayService:
#     """Service for handling Razorpay payments and wallet management"""

#     def __init__(self):
#         # Check if Razorpay is configured
#         if not settings.razorpay_key_id or not settings.razorpay_key_secret:
#             logger.warning("⚠️ Razorpay not configured - payment features disabled")
#             self.client = None
#             self.is_enabled = False
#         else:
#             try:
#                 self.client = razorpay.Client(
#                     auth=(settings.razorpay_key_id, settings.razorpay_key_secret)
#                 )
#                 self.client.set_app_details({"title": settings.app_name, "version": settings.app_version})
#                 self.is_enabled = True
#                 logger.info(f"✅ Razorpay client initialized for {settings.app_name}")
#             except Exception as e:
#                 logger.error(f"❌ Failed to initialize Razorpay client: {e}")
#                 self.client = None
#                 self.is_enabled = False

#     def _check_enabled(self):
#         """Check if Razorpay is enabled"""
#         if not self.is_enabled or not self.client:
#             raise Exception("Payment service is not configured. Please contact support.")

#     async def create_order(
#         self, 
#         amount: float, 
#         user_id: str, 
#         currency: str = None,
#         receipt: Optional[str] = None,
#         notes: Optional[Dict] = None
#     ) -> Dict:
#         """Create a Razorpay order for payment"""
#         self._check_enabled()
        
#         try:
#             # Use settings for currency
#             currency = currency or settings.payment_currency
            
#             # Validate amount limits
#             if amount < settings.payment_min_amount:
#                 raise ValueError(f"Minimum amount is ₹{settings.payment_min_amount}")
#             if amount > settings.payment_max_amount:
#                 raise ValueError(f"Maximum amount is ₹{settings.payment_max_amount}")
            
#             # Convert amount to paise
#             amount_in_paise = int(amount * 100)
            
#             if not receipt:
#                 receipt = f"rcpt_{user_id}_{uuid.uuid4().hex[:8]}"
            
#             order_data = {
#                 "amount": amount_in_paise,
#                 "currency": currency,
#                 "receipt": receipt,
#                 "notes": notes or {"user_id": user_id, "app": settings.app_name}
#             }
            
#             order = self.client.order.create(data=order_data)
#             logger.info(f"✅ Razorpay order created: {order['id']} for user: {user_id}")
            
#             # Store order in Firestore
#             db = get_firestore_client()
#             transaction_id = str(uuid.uuid4())
            
#             transaction_data = {
#                 "transactionId": transaction_id,
#                 "userId": user_id,
#                 "amount": amount,
#                 "transactionType": TransactionType.ADD_MONEY.value,
#                 "status": PaymentStatus.CREATED.value,
#                 "razorpayOrderId": order['id'],
#                 "description": f"Add money to wallet",
#                 "metadata": {
#                     **order_data,
#                     "environment": settings.environment
#                 },
#                 "createdAt": datetime.utcnow(),
#                 "updatedAt": datetime.utcnow()
#             }
            
#             db.collection("wallet_transactions").document(transaction_id).set(transaction_data)
            
#             return {
#                 "order_id": order['id'],
#                 "amount": amount,
#                 "currency": currency,
#                 "key_id": settings.razorpay_key_id,
#                 "transaction_id": transaction_id
#             }
            
#         except ValueError as ve:
#             raise ve
#         except Exception as e:
#             logger.error(f"❌ Failed to create Razorpay order: {e}")
#             raise Exception(f"Order creation failed: {str(e)}")

#     async def verify_payment_signature(
#         self, 
#         razorpay_order_id: str,
#         razorpay_payment_id: str,
#         razorpay_signature: str
#     ) -> bool:
#         """Verify Razorpay payment signature for security"""
#         self._check_enabled()
        
#         try:
#             message = f"{razorpay_order_id}|{razorpay_payment_id}"
            
#             generated_signature = hmac.new(
#                 settings.razorpay_key_secret.encode(),
#                 message.encode(),
#                 hashlib.sha256
#             ).hexdigest()
            
#             is_valid = hmac.compare_digest(generated_signature, razorpay_signature)
            
#             if is_valid:
#                 logger.info(f"✅ Payment signature verified for order: {razorpay_order_id}")
#             else:
#                 logger.warning(f"⚠️ Invalid payment signature for order: {razorpay_order_id}")
            
#             return is_valid
            
#         except Exception as e:
#             logger.error(f"❌ Signature verification failed: {e}")
#             return False

#     async def capture_payment(
#         self,
#         transaction_id: str,
#         razorpay_payment_id: str,
#         razorpay_order_id: str,
#         razorpay_signature: str,
#         user_id: str
#     ) -> Dict:
#         """Capture and process successful payment"""
#         self._check_enabled()
        
#         try:
#             db = get_firestore_client()
            
#             # Verify signature
#             is_valid = await self.verify_payment_signature(
#                 razorpay_order_id,
#                 razorpay_payment_id,
#                 razorpay_signature
#             )
            
#             if not is_valid:
#                 raise Exception("Invalid payment signature")
            
#             # Get transaction
#             transaction_ref = db.collection("wallet_transactions").document(transaction_id)
#             transaction_doc = transaction_ref.get()
            
#             if not transaction_doc.exists:
#                 raise Exception("Transaction not found")
            
#             transaction_data = transaction_doc.to_dict()
            
#             # Verify user ownership
#             if transaction_data.get("userId") != user_id:
#                 raise Exception("Unauthorized access to transaction")
            
#             # Check if already processed
#             if transaction_data.get("status") == PaymentStatus.CAPTURED.value:
#                 logger.warning(f"⚠️ Transaction {transaction_id} already captured")
#                 return {
#                     "success": True,
#                     "transaction_id": transaction_id,
#                     "amount": transaction_data.get("amount"),
#                     "new_balance": await self.get_wallet_balance(user_id),
#                     "message": "Already processed"
#                 }
            
#             # Fetch payment details from Razorpay
#             payment = self.client.payment.fetch(razorpay_payment_id)
            
#             # Update transaction status
#             transaction_ref.update({
#                 "status": PaymentStatus.CAPTURED.value,
#                 "razorpayPaymentId": razorpay_payment_id,
#                 "razorpaySignature": razorpay_signature,
#                 "updatedAt": datetime.utcnow(),
#                 "metadata": {
#                     **transaction_data.get("metadata", {}),
#                     "payment_details": payment
#                 }
#             })
            
#             # Check if first transaction for bonus
#             is_first_transaction = await self._is_first_wallet_transaction(user_id)
#             bonus_amount = 0.0
            
#             if is_first_transaction and settings.wallet_bonus_on_first_add > 0:
#                 bonus_amount = settings.wallet_bonus_on_first_add
#                 logger.info(f"🎁 First transaction bonus: ₹{bonus_amount} for user {user_id}")
            
#             # Update user wallet
#             total_amount = transaction_data.get("amount") + bonus_amount
#             await self._update_user_wallet(
#                 user_id,
#                 total_amount,
#                 TransactionType.ADD_MONEY
#             )
            
#             # Create bonus transaction if applicable
#             if bonus_amount > 0:
#                 await self._create_bonus_transaction(user_id, bonus_amount)
            
#             logger.info(f"✅ Payment captured successfully for user: {user_id}")
            
#             return {
#                 "success": True,
#                 "transaction_id": transaction_id,
#                 "amount": transaction_data.get("amount"),
#                 "bonus": bonus_amount,
#                 "total_credited": total_amount,
#                 "new_balance": await self.get_wallet_balance(user_id)
#             }
            
#         except Exception as e:
#             logger.error(f"❌ Payment capture failed: {e}")
            
#             # Update transaction as failed
#             try:
#                 transaction_ref.update({
#                     "status": PaymentStatus.FAILED.value,
#                     "updatedAt": datetime.utcnow(),
#                     "error": str(e)
#                 })
#             except:
#                 pass
            
#             raise Exception(f"Payment capture failed: {str(e)}")

#     async def _is_first_wallet_transaction(self, user_id: str) -> bool:
#         """Check if this is user's first wallet transaction"""
#         try:
#             db = get_firestore_client()
#             from google.cloud.firestore import FieldFilter
            
#             transactions = db.collection("wallet_transactions")\
#                 .where(filter=FieldFilter("userId", "==", user_id))\
#                 .where(filter=FieldFilter("status", "==", PaymentStatus.CAPTURED.value))\
#                 .limit(1)\
#                 .stream()
            
#             return len(list(transactions)) == 0
            
#         except Exception as e:
#             logger.error(f"Error checking first transaction: {e}")
#             return False

#     async def _create_bonus_transaction(self, user_id: str, bonus_amount: float):
#         """Create a bonus transaction record"""
#         try:
#             db = get_firestore_client()
#             transaction_id = str(uuid.uuid4())
            
#             bonus_data = {
#                 "transactionId": transaction_id,
#                 "userId": user_id,
#                 "amount": bonus_amount,
#                 "transactionType": "bonus",
#                 "status": PaymentStatus.CAPTURED.value,
#                 "description": "First transaction bonus",
#                 "createdAt": datetime.utcnow(),
#                 "updatedAt": datetime.utcnow()
#             }
            
#             db.collection("wallet_transactions").document(transaction_id).set(bonus_data)
#             logger.info(f"🎁 Bonus transaction created: {transaction_id}")
            
#         except Exception as e:
#             logger.error(f"Failed to create bonus transaction: {e}")

#     async def _update_user_wallet(
#         self,
#         user_id: str,
#         amount: float,
#         transaction_type: TransactionType
#     ):
#         """Update user wallet balance"""
#         try:
#             db = get_firestore_client()
#             user_ref = db.collection("users").document(user_id)
#             user_doc = user_ref.get()
            
#             if not user_doc.exists:
#                 raise Exception("User not found")
            
#             user_data = user_doc.to_dict()
#             current_balance = user_data.get("walletBalance", 0.0)
            
#             if transaction_type == TransactionType.ADD_MONEY:
#                 new_balance = current_balance + amount
#             elif transaction_type == TransactionType.PURCHASE:
#                 if current_balance < amount:
#                     raise Exception("Insufficient wallet balance")
#                 new_balance = current_balance - amount
#             else:
#                 new_balance = current_balance
            
#             user_ref.update({
#                 "walletBalance": new_balance,
#                 "walletCurrency": settings.payment_currency,
#                 "updatedAt": datetime.utcnow()
#             })
            
#             logger.info(f"💰 Wallet updated for user {user_id}: ₹{current_balance} → ₹{new_balance}")
            
#         except Exception as e:
#             logger.error(f"❌ Wallet update failed: {e}")
#             raise

#     async def get_wallet_balance(self, user_id: str) -> float:
#         """Get current wallet balance for user"""
#         try:
#             db = get_firestore_client()
#             user_doc = db.collection("users").document(user_id).get()
            
#             if not user_doc.exists:
#                 return 0.0
            
#             return user_doc.to_dict().get("walletBalance", 0.0)
            
#         except Exception as e:
#             logger.error(f"❌ Failed to get wallet balance: {e}")
#             return 0.0

#     async def get_transaction_history(
#         self,
#         user_id: str,
#         limit: int = 50
#     ) -> list:
#         """Get transaction history for user"""
#         try:
#             db = get_firestore_client()
#             from google.cloud.firestore import FieldFilter
            
#             transactions = db.collection("wallet_transactions")\
#                 .where(filter=FieldFilter("userId", "==", user_id))\
#                 .order_by("createdAt", direction="DESCENDING")\
#                 .limit(limit)\
#                 .stream()
            
#             history = []
#             for doc in transactions:
#                 data = doc.to_dict()
#                 history.append(data)
            
#             return history
            
#         except Exception as e:
#             logger.error(f"❌ Failed to get transaction history: {e}")
#             return []

#     async def process_webhook(self, payload: Dict, signature: str) -> Dict:
#         """Process Razorpay webhook events securely"""
#         self._check_enabled()
        
#         try:
#             # Verify webhook signature
#             if not self._verify_webhook_signature(payload, signature):
#                 raise Exception("Invalid webhook signature")
            
#             event = payload.get("event")
#             logger.info(f"📥 Processing webhook event: {event}")
            
#             # Handle different webhook events
#             if event == "payment.captured":
#                 await self._handle_payment_captured(payload)
#             elif event == "payment.failed":
#                 await self._handle_payment_failed(payload)
#             elif event == "refund.created":
#                 await self._handle_refund_created(payload)
            
#             return {"status": "processed"}
            
#         except Exception as e:
#             logger.error(f"❌ Webhook processing failed: {e}")
#             raise

#     def _verify_webhook_signature(self, payload: Dict, signature: str) -> bool:
#         """Verify webhook signature"""
#         if not settings.razorpay_webhook_secret:
#             logger.warning("⚠️ Webhook secret not configured - skipping verification")
#             return True  # Allow in development
        
#         try:
#             import json
            
#             expected_signature = hmac.new(
#                 settings.razorpay_webhook_secret.encode(),
#                 json.dumps(payload).encode(),
#                 hashlib.sha256
#             ).hexdigest()
            
#             return hmac.compare_digest(expected_signature, signature)
            
#         except Exception as e:
#             logger.error(f"❌ Webhook signature verification failed: {e}")
#             return False

#     async def _handle_payment_captured(self, payload: Dict):
#         """Handle payment.captured webhook"""
#         try:
#             payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
#             order_id = payment_entity.get("order_id")
            
#             db = get_firestore_client()
#             from google.cloud.firestore import FieldFilter
            
#             transactions = db.collection("wallet_transactions")\
#                 .where(filter=FieldFilter("razorpayOrderId", "==", order_id))\
#                 .limit(1)\
#                 .stream()
            
#             for doc in transactions:
#                 transaction_ref = doc.reference
#                 transaction_data = doc.to_dict()
                
#                 # Skip if already captured
#                 if transaction_data.get("status") == PaymentStatus.CAPTURED.value:
#                     logger.info(f"Transaction already captured: {order_id}")
#                     return
                
#                 transaction_ref.update({
#                     "status": PaymentStatus.CAPTURED.value,
#                     "razorpayPaymentId": payment_entity.get("id"),
#                     "updatedAt": datetime.utcnow()
#                 })
                
#                 # Update wallet
#                 await self._update_user_wallet(
#                     transaction_data.get("userId"),
#                     transaction_data.get("amount"),
#                     TransactionType.ADD_MONEY
#                 )
                
#                 logger.info(f"✅ Webhook: Payment captured for order {order_id}")
                
#         except Exception as e:
#             logger.error(f"❌ Failed to handle payment.captured webhook: {e}")

#     async def _handle_payment_failed(self, payload: Dict):
#         """Handle payment.failed webhook"""
#         try:
#             payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
#             order_id = payment_entity.get("order_id")
            
#             db = get_firestore_client()
#             from google.cloud.firestore import FieldFilter
            
#             transactions = db.collection("wallet_transactions")\
#                 .where(filter=FieldFilter("razorpayOrderId", "==", order_id))\
#                 .limit(1)\
#                 .stream()
            
#             for doc in transactions:
#                 doc.reference.update({
#                     "status": PaymentStatus.FAILED.value,
#                     "updatedAt": datetime.utcnow(),
#                     "error": payment_entity.get("error_description", "Payment failed")
#                 })
                
#                 logger.warning(f"⚠️ Webhook: Payment failed for order {order_id}")
                
#         except Exception as e:
#             logger.error(f"❌ Failed to handle payment.failed webhook: {e}")

#     async def _handle_refund_created(self, payload: Dict):
#         """Handle refund.created webhook"""
#         logger.info("📥 Refund webhook received")
#         # Implement refund logic as needed


# # Create singleton instance
# razorpay_service = RazorpayService()
