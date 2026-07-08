import os
from datetime import datetime
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import Base, engine, get_db, wait_for_database
from .models import AuditLog
from .schemas import AuditEventIn, AuditLogOut
from .security import CurrentUser, RoleName, get_current_user, require_roles

INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "clave-interna-cambiar")

app = FastAPI(title="Servicio de Auditoria", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def verify_internal_key(x_internal_key: str | None = Header(default=None)):
    """Solo otros microservicios (con la clave compartida) pueden emitir eventos."""
    if not x_internal_key or x_internal_key != INTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="Clave interna invalida o ausente")


@app.on_event("startup")
def startup():
    wait_for_database()
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/events", status_code=201, dependencies=[Depends(verify_internal_key)])
def create_event(payload: AuditEventIn, db: Session = Depends(get_db)):
    log = AuditLog(
        usuario_id=payload.usuario_id,
        accion=payload.accion,
        resultado=payload.resultado,
        ip=payload.ip,
        detalles=payload.detalles,
    )
    db.add(log)
    db.commit()
    return {"status": "registrado"}


@app.get("/logs", response_model=list[AuditLogOut])
def list_logs(
    accion: Optional[str] = Query(default=None),
    resultado: Optional[str] = Query(default=None),
    desde: Optional[datetime] = Query(default=None),
    hasta: Optional[datetime] = Query(default=None),
    _: CurrentUser = Depends(require_roles(RoleName.COORDINADOR, RoleName.ADMIN)),
    db: Session = Depends(get_db),
):
    stmt = select(AuditLog)
    if accion:
        stmt = stmt.where(AuditLog.accion == accion)
    if resultado:
        stmt = stmt.where(AuditLog.resultado == resultado)
    if desde:
        stmt = stmt.where(AuditLog.fecha_hora >= desde)
    if hasta:
        stmt = stmt.where(AuditLog.fecha_hora <= hasta)
    stmt = stmt.order_by(AuditLog.fecha_hora.desc())
    return db.scalars(stmt).all()


@app.get("/logs/user/{user_id}", response_model=list[AuditLogOut])
def list_logs_by_user(
    user_id: int,
    _: CurrentUser = Depends(require_roles(RoleName.COORDINADOR, RoleName.ADMIN)),
    db: Session = Depends(get_db),
):
    stmt = select(AuditLog).where(AuditLog.usuario_id == user_id).order_by(AuditLog.fecha_hora.desc())
    return db.scalars(stmt).all()


@app.get("/logs/security", response_model=list[AuditLogOut])
def list_security_logs(
    _: CurrentUser = Depends(require_roles(RoleName.COORDINADOR, RoleName.ADMIN)),
    db: Session = Depends(get_db),
):
    stmt = (
        select(AuditLog)
        .where((AuditLog.resultado == "FAIL") | (AuditLog.accion == "ACCESO_DENEGADO"))
        .order_by(AuditLog.fecha_hora.desc())
    )
    return db.scalars(stmt).all()
