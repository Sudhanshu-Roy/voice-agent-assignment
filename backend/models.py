"""
SQLAlchemy ORM models for phone number persistence.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime, Index
from backend.database import Base


def _utc_now():
    return datetime.now(timezone.utc)


class PhoneRecord(Base):
    __tablename__ = "phone_records"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    rawTranscript = Column(Text, nullable=False)
    parsedNumber = Column(String(15), nullable=False, index=True)
    language = Column(String(10), nullable=False, index=True)
    collectedAt = Column(DateTime, default=_utc_now, nullable=False, index=True)

    __table_args__ = (
        Index("ix_phone_records_number_date", "parsedNumber", "collectedAt"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "rawTranscript": self.rawTranscript,
            "parsedNumber": self.parsedNumber,
            "language": self.language,
            "collectedAt": self.collectedAt.isoformat() if self.collectedAt else None,
        }
