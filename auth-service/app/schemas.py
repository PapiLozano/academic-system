from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field

from .models import RoleName


class UserRegister(BaseModel):
    dni: str = Field(min_length=8, max_length=15)
    nombres: str
    apellidos: str
    correo: EmailStr
    password: str = Field(min_length=8)
    rol: RoleName


class UserOut(BaseModel):
    id: int
    dni: str
    nombres: str
    apellidos: str
    correo: EmailStr
    rol: RoleName
    estado: bool
    creado_en: datetime

    class Config:
        from_attributes = True


class LoginRequest(BaseModel):
    correo: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class ChangePasswordRequest(BaseModel):
    password_actual: str
    password_nueva: str = Field(min_length=8)


class EstadoUpdate(BaseModel):
    estado: bool
