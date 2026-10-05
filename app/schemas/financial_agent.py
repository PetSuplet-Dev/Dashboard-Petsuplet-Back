from pydantic import BaseModel, ConfigDict
from uuid import UUID
from datetime import datetime
from typing import Optional, List, Dict, Any


# CANVAS ARTIFACTS SCHEMAS
class CanvasArtifactBase(BaseModel):
    type: str
    title: str
    data: Dict[str, Any]


class CanvasArtifactResponse(CanvasArtifactBase):
    id: UUID
    message_id: UUID
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# MESSAGES SCHEMAS
class MessageCreatePayload(BaseModel):
    prompt: str
    selected_db: Optional[str] = "invoice_reconciliations"


class MessageResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    role: str
    content: str
    has_artifact: bool
    created_at: datetime
    artifact: Optional[CanvasArtifactResponse] = None
    model_config = ConfigDict(from_attributes=True)


# CONVERSATIONS SCHEMAS
class ConversationCreate(BaseModel):
    title: Optional[str] = "Nueva Consulta Financiera"
    selected_db: Optional[str] = "invoice_reconciliations"


class ConversationMinimalResponse(BaseModel):
    id: UUID
    title: Optional[str] = None
    selected_db: Optional[str] = None
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ConversationDetailResponse(BaseModel):
    id: UUID
    title: Optional[str] = None
    selected_db: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    messages: List[MessageResponse] = []
    model_config = ConfigDict(from_attributes=True)
