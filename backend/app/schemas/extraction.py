import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.ai.schemas import Confidence, ReceiptExtraction


class ExtractReceiptRequest(BaseModel):
    """What the app sends after on-device OCR and masking (the P04 CapturePayload).

    `masked_text` is limited to 20 KB by the service (413 TEXT_TOO_LARGE); max_length here only
    keeps absurd bodies from being processed at all.
    """

    masked_text: str = Field(min_length=1, max_length=200_000)
    capture_date: date
    source: Literal["CAMERA", "GALLERY", "SHARE"]


class ExtractReceiptResponse(BaseModel):
    observation_id: uuid.UUID
    extraction: ReceiptExtraction
    confidence: dict[str, Confidence]
