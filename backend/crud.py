"""
CRUD operations for phone_records table.
"""

from typing import List, Optional, Tuple, Dict
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func
from backend.models import PhoneRecord
from backend.schemas import PhoneCreateRequest


def create_phone_record(db: Session, data: PhoneCreateRequest) -> PhoneRecord:
    """Create and persist a validated phone record."""
    record = PhoneRecord(
        rawTranscript=data.rawTranscript,
        parsedNumber=data.parsedNumber,
        language=data.language,
        collectedAt=datetime.now(timezone.utc)
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_phone_records(
    db: Session,
    search: Optional[str] = None,
    language: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = 100,
    offset: int = 0
) -> Tuple[List[PhoneRecord], int]:
    """Retrieve phone records with filtering, search, and pagination."""
    query = db.query(PhoneRecord)

    if search:
        cleaned_search = search.strip()
        query = query.filter(PhoneRecord.parsedNumber.contains(cleaned_search))

    if language and language.lower() in {"en", "hi", "mixed"}:
        query = query.filter(PhoneRecord.language == language.lower())

    if start_date:
        query = query.filter(PhoneRecord.collectedAt >= start_date)

    if end_date:
        # If end_date is at midnight (pure date selection), expand to end of the full day
        if end_date.hour == 0 and end_date.minute == 0 and end_date.second == 0 and end_date.microsecond == 0:
            end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
        query = query.filter(PhoneRecord.collectedAt <= end_date)

    total = query.count()
    records = query.order_by(PhoneRecord.collectedAt.desc()).offset(offset).limit(limit).all()
    return records, total


def get_phone_record_by_id(db: Session, record_id: int) -> Optional[PhoneRecord]:
    """Retrieve a single phone record by its primary key ID."""
    return db.query(PhoneRecord).filter(PhoneRecord.id == record_id).first()


def delete_phone_record(db: Session, record_id: int) -> bool:
    """Delete a phone record by ID. Returns True if deleted, False if not found."""
    record = db.query(PhoneRecord).filter(PhoneRecord.id == record_id).first()
    if not record:
        return False
    db.delete(record)
    db.commit()
    return True


def get_phone_stats(db: Session) -> Dict[str, int]:
    """Aggregate statistics for dashboard metrics cards."""
    total = db.query(PhoneRecord).count()
    en_count = db.query(PhoneRecord).filter(PhoneRecord.language == "en").count()
    hi_count = db.query(PhoneRecord).filter(PhoneRecord.language == "hi").count()
    mixed_count = db.query(PhoneRecord).filter(PhoneRecord.language == "mixed").count()
    return {
        "total": total,
        "english": en_count,
        "hindi": hi_count,
        "mixed": mixed_count
    }
