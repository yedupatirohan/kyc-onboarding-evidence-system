from pydantic import BaseModel

from app.schemas.customers import AlertOut, DocumentOut, VerificationOut


class DocumentListItem(DocumentOut):
    customer_name: str


class DocumentDetail(DocumentListItem):
    verifications: list[VerificationOut]
    alerts: list[AlertOut]
    duplicate_of: list[str]       # other document ids carrying the same file hash
