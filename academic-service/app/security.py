import os
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from jose import JWTError, jwt

JWT_SECRET = os.getenv("JWT_SECRET", "cambiar-este-secreto-en-produccion")
JWT_ALGORITHM = "HS256"


class RoleName:
    ALUMNO = "ALUMNO"
    DOCENTE = "DOCENTE"
    COORDINADOR = "COORDINADOR"
    ADMIN = "ADMIN"


@dataclass
class CurrentUser:
    id: int
    rol: str
    correo: str

    @property
    def role(self) -> str:
        return self.rol


def get_current_user(authorization: Optional[str] = Header(default=None)) -> CurrentUser:
    """
    Valida el JWT emitido por el Servicio de Autenticacion. Ambos servicios
    comparten JWT_SECRET, asi que este servicio valida el token de forma
    independiente (arquitectura distribuida) sin llamar al servicio de auth
    en cada peticion.
    """
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
