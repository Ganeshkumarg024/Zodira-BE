from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class PaymentStatus(str, Enum):
    CREATED = "created"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    REFUNDED = "refunded"
    FAILED = "failed"


class TransactionType(str, Enum):
    ADD_MONEY = "add_money"
    PURCHASE = "purchase"
    REFUND = "refund"
    WITHDRAWAL = "withdrawal"


class WalletTransaction(BaseModel):
    """Wallet transaction model"""
    transactionId: str
    userId: str
    amount: float
    transactionType: TransactionType
    status: PaymentStatus
    razorpayOrderId: Optional[str] = None
    razorpayPaymentId: Optional[str] = None
    razorpaySignature: Optional[str] = None
    description: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    createdAt: datetime
    updatedAt: datetime

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class UserWallet(BaseModel):
    """User wallet model"""
    userId: str
    balance: float = 0.0
    currency: str = "INR"
    totalAdded: float = 0.0
    totalSpent: float = 0.0
    createdAt: datetime
    updatedAt: datetime
    isActive: bool = True

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# Enhanced User Model with wallet info
class UserWithWallet(BaseModel):
    userId: str
    email: Optional[str] = None
    displayName: Optional[str] = None
    walletBalance: float = 0.0
    subscriptionType: str = "free"
    profileComplete: bool = False
