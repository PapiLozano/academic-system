import os

import httpx
from fastapi import HTTPException

AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://localhost:8001")
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "clave-interna-cambiar")


def register_user_in_auth(dni: str, nombres: str, apellidos: str, correo: str, password: str, rol: str) -> int:
    """
    Crea la cuenta de acceso (usuario + contrasena) en el Servicio de
    Autenticacion. Devuelve el user_id creado. Esto es lo que garantiza que
    un docente/alumno creado desde el Servicio Academico SIEMPRE pueda
    iniciar sesion (evita el bug de perfiles sin usuario vinculado).
    """
    try:
        response = httpx.post(
            f"{AUTH_SERVICE_URL}/auth/register",
            json={
                "dni": dni,
                "nombres": nombres,
                "apellidos": apellidos,
                "correo": correo,
                "password": password,
                "rol": rol,
            },
            headers={"X-Internal-Key": INTERNAL_API_KEY},
            timeout=5.0,
        )
    except httpx.HTTPError as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Servicio de autenticacion no disponible: {exc}")

    if response.status_code == 409:
        raise HTTPException(status_code=409, detail="Ya existe un usuario con ese DNI o correo")
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Error creando usuario en autenticacion: {response.text}")

    return response.json()["id"]


def delete_user_in_auth(user_id: int) -> None:
    """
    Accion de compensacion (patron Saga): revierte la creacion del usuario
    en el Servicio de Autenticacion si el paso siguiente (crear el perfil
    de Docente/Alumno en este servicio) falla. Es "best effort".
    """
    try:
        httpx.delete(
            f"{AUTH_SERVICE_URL}/auth/users/{user_id}",
            headers={"X-Internal-Key": INTERNAL_API_KEY},
            timeout=5.0,
        )
    except httpx.HTTPError as exc:  # noqa: BLE001
        print(f"[auth_client] No se pudo revertir la creacion del usuario {user_id}: {exc}")
