"""
Pydantic schemas for phone record validation and API serialization.
"""

from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel, Field, field_validator, ConfigDict


class PhoneCreateRequest(BaseModel):
    rawTranscript: str = Field(..., min_length=1, description="Raw speech or typed transcript")
    parsedNumber: str = Field(..., description="10-digit Indian mobile number")
    language: str = Field(..., description="Language classification: 'en', 'hi', or 'mixed'")

    @field_validator("parsedNumber")
    @classmethod
    def validate_indian_mobile(cls, v: str) -> str:
        cleaned = v.strip().replace(" ", "").replace("-", "")
        if not cleaned.isdigit():
            raise ValueError("Phone number must contain only numeric digits")
        if len(cleaned) != 10:
            raise ValueError(f"Indian mobile phone number must be exactly 10 digits (got {len(cleaned)})")
        if cleaned[0] not in {"6", "7", "8", "9"}:
            raise ValueError(f"Indian mobile phone number must start with 6, 7, 8, or 9 (got '{cleaned[0]}')")
        return cleaned

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        lang = v.strip().lower()
        if lang not in {"en", "hi", "mixed"}:
            raise ValueError("Language must be one of 'en', 'hi', or 'mixed'")
        return lang


class PhoneRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    rawTranscript: str
    parsedNumber: str
    language: str
    collectedAt: datetime


class StandardResponse(BaseModel):
    success: bool
    message: Optional[str] = None
    data: Optional[Any] = None


class PhoneListResponse(BaseModel):
    success: bool
    data: List[PhoneRecordResponse]
    total: int


class PhoneStatsResponse(BaseModel):
    total: int
    english: int
    hindi: int
    mixed: int
