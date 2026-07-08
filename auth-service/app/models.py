import enum
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, Integer, String

from .database import Base


class RoleName(str, enum.Enum):
    ALUMNO = "ALUMNO"
    DOCENTE = "DOCENTE"
    COORDINADOR = "COORDINADOR"
    ADMIN = "ADMIN"


class User(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    dni = Column(String(15), unique=True, nullable=False, index=True)
    nombres = Column(String(100), nullable=False)
    apellidos = Column(String(100), nullable=False)
    correo = Column(String(150), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    rol = Column(Enum(RoleName), nullable=False)
    estado = Column(Boolean, default=True, nullable=False)  # True = habilitado
    intentos_fallidos = Column(Integer, default=0, nullable=False)
    bloqueado_hasta = Column(DateTime, nullable=True)
    creado_en = Column(DateTime, default=datetime.utcnow, nullable=False)
