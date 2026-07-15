"""
Balanceador de carga (reverse proxy round-robin) para academic-service.

Reparte cada peticion entrante entre N instancias identicas de
academic-service (definidas en la variable de entorno BACKENDS,
separadas por coma). No guarda estado propio: se apoya en que
academic-service ya es stateless (autenticacion via JWT), asi que
cualquier instancia puede atender cualquier peticion sin coordinarse
con las demas.
"""

import itertools
import os

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Balanceador de carga - academic-service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BACKENDS = [b.strip().rstrip("/") for b in os.getenv("BACKENDS", "").split(",") if b.strip()]
if not BACKENDS:
    raise RuntimeError(
        "Configura la variable de entorno BACKENDS con las URLs de las "
        "instancias separadas por coma, ej: "
        "https://academic-service-a.onrender.com,https://academic-service-b.onrender.com"
    )

_round_robin = itertools.cycle(BACKENDS)

_HOP_BY_HOP_REQUEST_HEADERS = {"host", "content-length", "connection"}
_HOP_BY_HOP_RESPONSE_HEADERS = {"content-encoding", "transfer-encoding", "connection"}


@app.get("/lb-status")
def lb_status():
    """Util para verificar que backends conoce el balanceador."""
    return {"backends": BACKENDS, "total": len(BACKENDS)}


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy(path: str, request: Request):
    backend = next(_round_robin)
    url = f"{backend}/{path}"

    body = await request.body()
    forward_headers = {
        k: v for k, v in request.headers.items() if k.lower() not in _HOP_BY_HOP_REQUEST_HEADERS
    }

    async with httpx.AsyncClient(timeout=30) as client:
        upstream = await client.request(
            request.method,
            url,
            params=request.query_params,
            content=body,
            headers=forward_headers,
        )

    response_headers = {
        k: v for k, v in upstream.headers.items() if k.lower() not in _HOP_BY_HOP_RESPONSE_HEADERS
    }
    # Cabecera de evidencia: muestra que instancia atendio realmente la peticion.
    response_headers["X-Served-By"] = backend

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
        media_type=upstream.headers.get("content-type"),
    )