import os

import httpx

AUDIT_SERVICE_URL = os.getenv("AUDIT_SERVICE_URL", "http://localhost:8002")
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "clave-interna-cambiar")


def emit_audit(user_id: int | None, accion: str, resultado: str = "OK", ip: str | None = None, details: str | None = None):
    """
    Envia un evento al Servicio de Auditoria. Es "best effort": si el
    servicio de auditoria no responde, la operacion principal (crear nota,
    matricular, etc.) NO debe fallar por eso, solo se registra en el log
    local del servicio academico.
    """
    try:
        httpx.post(
            f"{AUDIT_SERVICE_URL}/events",
            json={
                "usuario_id": user_id,
                "accion": accion,
                "resultado": resultado,
                "ip": ip,
                "detalles": details,
            },
            headers={"X-Internal-Key": INTERNAL_API_KEY},
            timeout=3.0,
        )
    except httpx.HTTPError as exc:  # noqa: BLE001
        print(f"[audit_client] No se pudo registrar evento de auditoria: {exc}")
