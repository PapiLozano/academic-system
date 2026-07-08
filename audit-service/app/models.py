from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from .database import Base


class AuditLog(Base):
    __tablename__ = "auditoria"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, nullable=True, index=True)
    accion = Column(String(100), nullable=False, index=True)
    resultado = Column(String(20), nullable=False, index=True)  # OK / FAIL
    ip = Column(String(64), nullable=True)
    detalles = Column(Text, nullable=True)
    fecha_hora = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
