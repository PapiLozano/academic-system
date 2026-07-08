import os
from datetime import datetime, timedelta

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import Base, engine, get_db, wait_for_database
from .models import RoleName, User
from .schemas import (
    ChangePasswordRequest,
    EstadoUpdate,
    LoginRequest,
    TokenResponse,
    UserOut,
    UserRegister,
)
from .security import (
    CurrentUser,
    create_access_token,
    get_current_user,
    hash_password,
    require_roles,
    verify_password,
)

INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "clave-interna-cambiar")
MAX_INTENTOS_FALLIDOS = int(os.getenv("MAX_INTENTOS_FALLIDOS", "5"))
BLOQUEO_MINUTOS = int(os.getenv("BLOQUEO_MINUTOS", "15"))
ADMIN_BOOTSTRAP_EMAIL = os.getenv("ADMIN_BOOTSTRAP_EMAIL", "admin@universidad.edu")
ADMIN_BOOTSTRAP_PASSWORD = os.getenv("ADMIN_BOOTSTRAP_PASSWORD", "Admin123!")

app = FastAPI(title="Servicio de Autenticacion", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def verify_internal_key(x_internal_key: str | None = Header(default=None)):
    """
    Los otros microservicios (por ejemplo el Servicio Academico) usan esta
    clave compartida para crear/eliminar usuarios (docentes/alumnos) sin
    exponer un registro publico sin control. Debe coincidir con INTERNAL_API_KEY.
    """
    if not x_internal_key or x_internal_key != INTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="Clave interna invalida o ausente")


def bootstrap_admin(db: Session):
    """Crea un administrador inicial si todavia no existe ninguno."""
    admin_exists = db.scalar(select(User).where(User.rol == RoleName.ADMIN))
    if admin_exists:
        return
    admin = User(
        dni="00000000",
        nombres="Administrador",
        apellidos="Sistema",
        correo=ADMIN_BOOTSTRAP_EMAIL,
        password_hash=hash_password(ADMIN_BOOTSTRAP_PASSWORD),
        rol=RoleName.ADMIN,
        estado=True,
    )
    db.add(admin)
    db.commit()
    print(f"[bootstrap] Administrador creado -> correo={ADMIN_BOOTSTRAP_EMAIL} password={ADMIN_BOOTSTRAP_PASSWORD}")
    print("[bootstrap] Cambie esta contrasena inmediatamente fuera de un entorno de pruebas.")


@app.on_event("startup")
def startup():
    wait_for_database()
    Base.metadata.create_all(bind=engine)
    db = next(get_db())
    try:
        bootstrap_admin(db)
    finally:
        db.close()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/auth/register", response_model=UserOut, status_code=201, dependencies=[Depends(verify_internal_key)])
def register(payload: UserRegister, db: Session = Depends(get_db)):
    """
    Endpoint protegido por clave interna (no es publico). Lo invoca el
    Servicio Academico cuando un Coordinador/Administrador crea un docente
    o un alumno, para que el nuevo perfil quede SIEMPRE vinculado a una
    cuenta de acceso valida (evita perfiles "huerfanos" sin usuario).
    """
    user = User(
        dni=payload.dni,
        nombres=payload.nombres,
        apellidos=payload.apellidos,
        correo=payload.correo,
        password_hash=hash_password(payload.password),
        rol=payload.rol,
        estado=True,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Ya existe un usuario con ese DNI o correo")
    db.refresh(user)
    return user


@app.delete("/auth/users/{user_id}", status_code=204, dependencies=[Depends(verify_internal_key)])
def delete_user_internal(user_id: int, db: Session = Depends(get_db)):
    """
    Accion de compensacion (patron Saga): si el Servicio Academico crea el
    usuario aqui pero luego falla al crear el perfil de Docente/Alumno en
    su propia base de datos, llama a este endpoint para deshacer el
    registro y no dejar una cuenta de acceso sin perfil asociado.
    """
    user = db.get(User, user_id)
    if user:
        db.delete(user)
        db.commit()


@app.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.correo == payload.correo))

    if not user:
        raise HTTPException(status_code=401, detail="Credenciales invalidas")

    if user.bloqueado_hasta and user.bloqueado_hasta > datetime.utcnow():
        raise HTTPException(
            status_code=423,
            detail=f"Cuenta bloqueada temporalmente hasta {user.bloqueado_hasta.isoformat()}",
        )

    if not user.estado:
        raise HTTPException(status_code=403, detail="Usuario deshabilitado")

    if not verify_password(payload.password, user.password_hash):
        user.intentos_fallidos += 1
        if user.intentos_fallidos >= MAX_INTENTOS_FALLIDOS:
            user.bloqueado_hasta = datetime.utcnow() + timedelta(minutes=BLOQUEO_MINUTOS)
            user.intentos_fallidos = 0
        db.commit()
        raise HTTPException(status_code=401, detail="Credenciales invalidas")

    user.intentos_fallidos = 0
    user.bloqueado_hasta = None
    db.commit()

    token, expires_in = create_access_token(user.id, user.rol.value, user.correo)
    return TokenResponse(access_token=token, expires_in=expires_in)


@app.post("/auth/logout", status_code=204)
def logout(_: CurrentUser = Depends(get_current_user)):
    # El JWT es "stateless": el cliente descarta el token.
    # Para invalidacion inmediata se requeriria una lista negra (ej. Redis)
    # consultada en get_current_user; fuera del alcance de este demo.
    return None


@app.get("/auth/profile", response_model=UserOut)
def profile(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    db_user = db.get(User, user.id)
    if not db_user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return db_user


@app.post("/auth/change-password", status_code=204)
def change_password(
    payload: ChangePasswordRequest,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db_user = db.get(User, user.id)
    if not db_user or not verify_password(payload.password_actual, db_user.password_hash):
        raise HTTPException(status_code=401, detail="Contrasena actual incorrecta")
    db_user.password_hash = hash_password(payload.password_nueva)
    db.commit()


@app.get("/auth/users", response_model=list[UserOut])
def list_users(
    _: CurrentUser = Depends(require_roles(RoleName.COORDINADOR.value, RoleName.ADMIN.value)),
    db: Session = Depends(get_db),
):
    return db.scalars(select(User)).all()


@app.patch("/auth/users/{user_id}/estado", response_model=UserOut)
def update_estado(
    user_id: int,
    payload: EstadoUpdate,
    _: CurrentUser = Depends(require_roles(RoleName.COORDINADOR.value, RoleName.ADMIN.value)),
    db: Session = Depends(get_db),
):
    db_user = db.get(User, user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    db_user.estado = payload.estado
    db.commit()
    db.refresh(db_user)
    return db_user
