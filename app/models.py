from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class SimpleFINOrg(BaseModel):
    name: Optional[str] = None
    domain: Optional[str] = None

class SimpleFINTransaction(BaseModel):
    id: str
    posted: int
    amount: str
    description: str
    payee: Optional[str] = None
    memo: Optional[str] = None
    pending: Optional[bool] = False

class SimpleFINAccount(BaseModel):
    id: str
    name: str
    currency: str = "USD"
    balance: str
    available_balance: Optional[str] = Field(default=None, alias="available-balance")
    balance_date: Optional[int] = Field(default=None, alias="balance-date")
    org: Optional[SimpleFINOrg] = None
    transactions: List[SimpleFINTransaction] = []

class SimpleFINResponse(BaseModel):
    errors: List[str] = []
    accounts: List[SimpleFINAccount] = []

class AccountModel(BaseModel):
    id: str
    name: str
    currency: str = "USD"
    balance_cents: int
    available_balance_cents: Optional[int] = None
    org_name: Optional[str] = None
    org_domain: Optional[str] = None
    updated_at: str

class TransactionModel(BaseModel):
    id: str
    account_id: str
    posted_at: str
    posted_timestamp: int
    amount_cents: int
    description: str
    payee: Optional[str] = None
    memo: Optional[str] = None
    pending: bool = False
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    is_transfer: bool = False
    user_notes: Optional[str] = None
    created_at: str
    updated_at: str
