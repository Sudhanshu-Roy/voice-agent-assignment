"""
FastAPI route handlers for phone records API.
"""

import logging
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.schemas import (
    PhoneCreateRequest,
    PhoneRecordResponse,
    StandardResponse,
    PhoneListResponse,
    PhoneStatsResponse
)
from backend import crud

logger = logging.getLogger("vaiu.backend.routes.phones")

router = APIRouter(prefix="/api/phone", tags=["Phones"])


def mask_phone_number(num: str) -> str:
    """Mask phone number for privacy logging: e.g. 9876543210 -> ******3210"""
    if len(num) >= 4:
        return f"******{num[-4:]}"
    return "****"


@router.post("", response_model=StandardResponse, status_code=status.HTTP_201_CREATED)
def create_phone(payload: PhoneCreateRequest, db: Session = Depends(get_db)):
    """
    Save a validated 10-digit phone number with its transcript and language.
    Only accepts validated Indian mobile numbers (validated via Pydantic).
    """
    masked = mask_phone_number(payload.parsedNumber)
    logger.info(f"POST /api/phone - saving number {masked} (lang: {payload.language})")

    try:
        record = crud.create_phone_record(db, payload)
        logger.info(f"Successfully saved phone record id={record.id} ({masked})")
        return {
            "success": True,
            "message": "Phone number saved successfully",
            "data": {
                "id": record.id,
                "rawTranscript": record.rawTranscript,
                "parsedNumber": record.parsedNumber,
                "language": record.language,
                "collectedAt": record.collectedAt.isoformat()
            }
        }
    except Exception as e:
        logger.error(f"Error persisting phone record: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"success": False, "message": "Failed to save phone number"}
        )


@router.get("", response_model=PhoneListResponse)
def list_phones(
    search: Optional[str] = Query(None, description="Search by phone number digits"),
    language: Optional[str] = Query(None, description="Filter by language: en, hi, mixed"),
    start_date: Optional[datetime] = Query(None, description="Filter records collected on or after"),
    end_date: Optional[datetime] = Query(None, description="Filter records collected on or before"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """
    Retrieve phone records with optional search, filtering, and pagination.
    """
    records, total = crud.get_phone_records(
        db, search=search, language=language,
        start_date=start_date, end_date=end_date,
        limit=limit, offset=offset
    )
    return {
        "success": True,
        "data": [
            PhoneRecordResponse(
                id=r.id,
                rawTranscript=r.rawTranscript,
                parsedNumber=r.parsedNumber,
                language=r.language,
                collectedAt=r.collectedAt
            )
            for r in records
        ],
        "total": total
    }


@router.get("/stats", response_model=PhoneStatsResponse)
def phone_stats(db: Session = Depends(get_db)):
    """
    Get aggregated counts for dashboard metrics.
    """
    stats = crud.get_phone_stats(db)
    return stats


@router.delete("/{record_id}", response_model=StandardResponse)
def delete_phone(record_id: int, db: Session = Depends(get_db)):
    """
    Delete a phone record by ID.
    """
    logger.info(f"DELETE /api/phone/{record_id}")
    deleted = crud.delete_phone_record(db, record_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"success": False, "message": "Phone record not found"}
        )
    return {
        "success": True,
        "message": "Phone record deleted"
    }
