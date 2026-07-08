from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AuditEventIn(BaseModel):
    usuario_id: Optional[int] = None
    accion: str
    resultado: str = "OK"
    ip: Optional[str] = None
    detalles: Optional[str] = None


class AuditLogOut(BaseModel):
    id: int
    usuario_id: Optional[int]
    accion: str
    resultado: str
    ip: Optional[str]
    detalles: Optional[str]
    fecha_hora: datetime

    class Config:
        from_attributes = True
