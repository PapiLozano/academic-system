import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import Depends, Header, HTTPException, status
from jose import JWTError, jwt

JWT_SECRET = os.getenv("JWT_SECRET", "cambiar-este-secreto-en-produccion")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))


class RoleName:
    ALUMNO = "ALUMNO"
    DOCENTE = "DOCENTE"
    COORDINADOR = "COORDINADOR"
    ADMIN = "ADMIN"


def hash_password(password: str) -> str:
    if len(password.encode("utf-8")) > 72:
        raise HTTPException(status_code=400, detail="La contrasena no puede superar 72 bytes")
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: int, rol: str, correo: str) -> tuple[str, int]:
    expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    expire = datetime.now(timezone.utc) + expires_delta
    payload = {
        "sub": str(user_id),
        "rol": rol,
        "correo": correo,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token, int(expires_delta.total_seconds())


@dataclass
class CurrentUser:
    id: int
    rol: str
    correo: str

    @property
    def role(self) -> str:
        return self.rol


def get_current_user(authorization: Optional[str] = Header(default=None)) -> CurrentUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token no proporcionado")

    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalido o expirado")

    user_id = payload.get("sub")
    rol = payload.get("rol")
    correo = payload.get("correo")
    if user_id is None or rol is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalido")

    return CurrentUser(id=int(user_id), rol=rol, correo=correo)


def require_roles(*roles: str):
    def dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.rol not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tiene permisos para esta accion")
        return user

    return dependency
