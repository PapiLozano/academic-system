import os
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .audit_client import emit_audit
from .auth_client import delete_user_in_auth, register_user_in_auth
from .database import Base, engine, get_db, wait_for_database
from .models import Course, Enrollment, Grade, Student, Teacher
from .schemas import (
    AssignTeacherRequest,
    CourseCreate,
    CourseOut,
    CourseUpdate,
    EnrollmentCreate,
    EnrollmentOut,
    GradeCreate,
    GradeOut,
    GradeUpdate,
    StudentCreate,
    StudentOut,
    StudentUpdate,
    TeacherCreate,
    TeacherOut,
    TeacherUpdate,
)
from .security import CurrentUser, RoleName, get_current_user, require_roles

app = FastAPI(title="Servicio Academico", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    wait_for_database()
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health():
    return {"status": "ok", "instance": os.getenv("INSTANCE_NAME", "academic-service")}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def require_owner_or_staff(student: Student, user: CurrentUser):
    """Un alumno solo puede ver/editar su propio perfil."""
    if user.role == RoleName.ALUMNO and student.user_id != user.id:
        emit_audit(user.id, "ACCESO_DENEGADO", "FAIL", details="Alumno intento acceder a otro perfil")
        raise HTTPException(status_code=403, detail="No puede acceder a informacion de otro alumno")


def get_teacher_profile(db: Session, user: CurrentUser) -> Teacher:
    """
    Devuelve el registro Teacher vinculado al usuario docente autenticado.
    Lanza 403 explicito si no existe (en vez de dejar que el codigo truene
    mas abajo con AttributeError al usar `teacher.id` sobre None).
    """
    teacher = db.scalar(select(Teacher).where(Teacher.user_id == user.id))
    if not teacher:
        emit_audit(user.id, "ACCESO_DENEGADO", "FAIL", details="Docente sin perfil asociado")
        raise HTTPException(
            status_code=403,
            detail="El usuario docente no tiene un perfil de profesor asociado",
        )
    return teacher


def get_teacher_profile_optional(db: Session, user: CurrentUser) -> Teacher | None:
    return db.scalar(select(Teacher).where(Teacher.user_id == user.id))


def get_student_profile_optional(db: Session, user: CurrentUser) -> Student | None:
    return db.scalar(select(Student).where(Student.user_id == user.id))


def grade_out(grade: Grade) -> GradeOut:
    enrollment = grade.enrollment
    return GradeOut(
        id=grade.id,
        enrollment_id=grade.enrollment_id,
        student_id=enrollment.student_id,
        course_id=enrollment.course_id,
        score=grade.score,
        date=grade.date,
        teacher_id=grade.teacher_id,
    )


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


# ---------------------------------------------------------------------------
# Alumnos
# ---------------------------------------------------------------------------

@app.get("/students", response_model=list[StudentOut])
def list_students(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role == RoleName.ALUMNO:
        student = get_student_profile_optional(db, user)
        return [student] if student else []

    if user.role == RoleName.DOCENTE:
        teacher = get_teacher_profile_optional(db, user)
        if not teacher:
            return []
        stmt = (
            select(Student)
            .join(Enrollment)
            .join(Course)
            .where(Course.teacher_id == teacher.id)
            .distinct()
        )
        return db.scalars(stmt).all()

    return db.scalars(select(Student)).all()


@app.post("/students", response_model=StudentOut, status_code=201)
def create_student(
    payload: StudentCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles(RoleName.COORDINADOR, RoleName.ADMIN)),
):
    """
    Crea la cuenta de acceso del alumno en el Servicio de Autenticacion
    (rol ALUMNO) y luego su perfil academico aqui, vinculados por user_id.
    Si el segundo paso falla, se revierte el primero (saga simple).
    """
    auth_user_id = register_user_in_auth(
        dni=payload.dni,
        nombres=payload.nombres,
        apellidos=payload.apellidos,
        correo=payload.correo,
        password=payload.password,
        rol=RoleName.ALUMNO,
    )

    student = Student(
        user_id=auth_user_id,
        dni=payload.dni,
        nombres=payload.nombres,
        apellidos=payload.apellidos,
        correo=payload.correo,
    )
    db.add(student)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        delete_user_in_auth(auth_user_id)
        raise HTTPException(status_code=409, detail="Alumno duplicado")

    db.refresh(student)
    emit_audit(user.id, "CREACION_ALUMNO", "OK", client_ip(request), details=f"student_id={student.id}")
    return student


@app.patch("/students/{student_id}", response_model=StudentOut)
def update_student(
    student_id: int,
    payload: StudentUpdate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    student = db.get(Student, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    if user.role not in (RoleName.COORDINADOR, RoleName.ADMIN):
        require_owner_or_staff(student, user)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(student, field, value)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="El correo ya esta en uso por otro alumno")

    db.refresh(student)
    emit_audit(user.id, "MODIFICACION_ALUMNO", "OK", details=f"student_id={student.id}")
    return student


# ---------------------------------------------------------------------------
# Docentes
# ---------------------------------------------------------------------------

@app.get("/teachers", response_model=list[TeacherOut])
def list_teachers(
    _: CurrentUser = Depends(require_roles(RoleName.COORDINADOR, RoleName.ADMIN)),
    db: Session = Depends(get_db),
):
    return db.scalars(select(Teacher)).all()


@app.post("/teachers", response_model=TeacherOut, status_code=201)
def create_teacher(
    payload: TeacherCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles(RoleName.COORDINADOR, RoleName.ADMIN)),
):
    """
    Igual que create_student: primero la cuenta de acceso (rol DOCENTE) en
    el Servicio de Autenticacion, luego el perfil de docente aqui. Esto es
    justamente lo que faltaba antes y causaba que el docente no pudiera
    iniciar sesion / apareciera sin teacher_id al registrar notas.
    """
    auth_user_id = register_user_in_auth(
        dni=payload.dni,
        nombres=payload.nombres,
        apellidos=payload.apellidos,
        correo=payload.correo,
        password=payload.password,
        rol=RoleName.DOCENTE,
    )

    teacher = Teacher(
        user_id=auth_user_id,
        dni=payload.dni,
        nombres=payload.nombres,
        apellidos=payload.apellidos,
        correo=payload.correo,
        especialidad=payload.especialidad,
    )
    db.add(teacher)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        delete_user_in_auth(auth_user_id)
        raise HTTPException(status_code=409, detail="Docente duplicado")

    db.refresh(teacher)
    emit_audit(user.id, "CREACION_DOCENTE", "OK", client_ip(request), details=f"teacher_id={teacher.id}")
    return teacher


@app.patch("/teachers/{teacher_id}", response_model=TeacherOut)
def update_teacher(
    teacher_id: int,
    payload: TeacherUpdate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles(RoleName.COORDINADOR, RoleName.ADMIN)),
):
    teacher = db.get(Teacher, teacher_id)
    if not teacher:
        raise HTTPException(status_code=404, detail="Docente no encontrado")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(teacher, field, value)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="El correo ya esta en uso por otro docente")

    db.refresh(teacher)
    emit_audit(user.id, "MODIFICACION_DOCENTE", "OK", details=f"teacher_id={teacher.id}")
    return teacher


# ---------------------------------------------------------------------------
# Cursos
# ---------------------------------------------------------------------------

@app.get("/courses", response_model=list[CourseOut])
def list_courses(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role == RoleName.ALUMNO:
        stmt = select(Course).join(Enrollment).join(Student).where(Student.user_id == user.id)
        return db.scalars(stmt).all()

    if user.role == RoleName.DOCENTE:
        teacher = get_teacher_profile_optional(db, user)
        if not teacher:
            return []
        return db.scalars(select(Course).where(Course.teacher_id == teacher.id)).all()

    return db.scalars(select(Course)).all()


@app.post("/courses", response_model=CourseOut, status_code=201)
def create_course(
    payload: CourseCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles(RoleName.COORDINADOR, RoleName.ADMIN)),
):
    if payload.teacher_id and not db.get(Teacher, payload.teacher_id):
        raise HTTPException(status_code=404, detail="Docente no encontrado")

    course = Course(**payload.model_dump())
    db.add(course)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Curso duplicado (codigo ya existe)")

    db.refresh(course)
    emit_audit(user.id, "CREACION_CURSO", "OK", details=f"course_id={course.id}")
    return course


@app.put("/courses/{course_id}", response_model=CourseOut)
def update_course(
    course_id: int,
    payload: CourseUpdate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles(RoleName.COORDINADOR, RoleName.ADMIN)),
):
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Curso no encontrado")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(course, field, value)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="El codigo de curso ya esta en uso")

    db.refresh(course)
    emit_audit(user.id, "MODIFICACION_CURSO", "OK", details=f"course_id={course.id}")
    return course


@app.post("/courses/{course_id}/assign-teacher", response_model=CourseOut)
def assign_teacher(
    course_id: int,
    payload: AssignTeacherRequest,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles(RoleName.COORDINADOR, RoleName.ADMIN)),
):
    """Endpoint dedicado para asignar (o reasignar) el docente titular de un curso."""
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Curso no encontrado")

    teacher = db.get(Teacher, payload.teacher_id)
    if not teacher:
        raise HTTPException(status_code=404, detail="Docente no encontrado")

    course.teacher_id = teacher.id
    db.commit()
    db.refresh(course)
    emit_audit(
        user.id,
        "ASIGNACION_DOCENTE_CURSO",
        "OK",
        details=f"course_id={course.id};teacher_id={teacher.id}",
    )
    return course


@app.delete("/courses/{course_id}", status_code=204)
def delete_course(
    course_id: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles(RoleName.COORDINADOR, RoleName.ADMIN)),
):
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Curso no encontrado")

    db.delete(course)
    db.commit()
    emit_audit(user.id, "ELIMINACION_CURSO", "OK", details=f"course_id={course_id}")


# ---------------------------------------------------------------------------
# Matriculas
# ---------------------------------------------------------------------------

@app.get("/enrollments", response_model=list[EnrollmentOut])
def list_enrollments(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role == RoleName.ALUMNO:
        stmt = select(Enrollment).join(Student).where(Student.user_id == user.id)
        return db.scalars(stmt).all()

    if user.role == RoleName.DOCENTE:
        teacher = get_teacher_profile_optional(db, user)
        if not teacher:
            return []
        stmt = select(Enrollment).join(Course).where(Course.teacher_id == teacher.id)
        return db.scalars(stmt).all()

    return db.scalars(select(Enrollment)).all()


@app.post("/enrollments", response_model=EnrollmentOut, status_code=201)
def create_enrollment(
    payload: EnrollmentCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles(RoleName.COORDINADOR, RoleName.ADMIN)),
):
    if not db.get(Student, payload.student_id):
        raise HTTPException(status_code=404, detail="Alumno no encontrado")
    if not db.get(Course, payload.course_id):
        raise HTTPException(status_code=404, detail="Curso no encontrado")

    enrollment = Enrollment(**payload.model_dump())
    db.add(enrollment)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="El alumno ya esta matriculado en ese curso para ese ciclo")

    db.refresh(enrollment)
    emit_audit(user.id, "REGISTRO_MATRICULA", "OK", details=f"enrollment_id={enrollment.id}")
    return enrollment


@app.delete("/enrollments/{enrollment_id}", status_code=204)
def delete_enrollment(
    enrollment_id: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles(RoleName.COORDINADOR, RoleName.ADMIN)),
):
    enrollment = db.get(Enrollment, enrollment_id)
    if not enrollment:
        raise HTTPException(status_code=404, detail="Matricula no encontrada")

    db.delete(enrollment)
    db.commit()
    emit_audit(user.id, "ELIMINACION_MATRICULA", "OK", details=f"enrollment_id={enrollment_id}")


# ---------------------------------------------------------------------------
# Notas
# ---------------------------------------------------------------------------

@app.get("/grades", response_model=list[GradeOut])
def list_grades(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    stmt = select(Grade).join(Enrollment)

    if user.role == RoleName.ALUMNO:
        stmt = stmt.join(Student).where(Student.user_id == user.id)
    elif user.role == RoleName.DOCENTE:
        teacher = get_teacher_profile_optional(db, user)
        stmt = stmt.join(Course).where(Course.teacher_id == teacher.id) if teacher else stmt.where(False)

    return [grade_out(grade) for grade in db.scalars(stmt).all()]


@app.post("/grades", response_model=GradeOut, status_code=201)
def create_grade(
    payload: GradeCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles(RoleName.DOCENTE, RoleName.ADMIN)),
):
    enrollment = db.get(Enrollment, payload.enrollment_id)
    if not enrollment:
        raise HTTPException(status_code=404, detail="Matricula no encontrada")

    if user.role == RoleName.DOCENTE:
        # Lanza 403 claro si el docente no tiene perfil asociado, en vez de
        # crashear mas abajo -- esto es lo que causaba el "teacher_id vacio".
        teacher = get_teacher_profile(db, user)
        if enrollment.course.teacher_id != teacher.id:
            emit_audit(
                user.id,
                "ACCESO_DENEGADO",
                "FAIL",
                details="Docente intento registrar nota en curso no asignado",
            )
            raise HTTPException(status_code=403, detail="Curso no asignado al docente")
        teacher_id = teacher.id
    else:
        # ADMIN registrando la nota: se asigna el docente titular del curso.
        if not enrollment.course.teacher_id:
            raise HTTPException(status_code=409, detail="El curso todavia no tiene un docente asignado")
        teacher_id = enrollment.course.teacher_id

    grade = Grade(enrollment_id=payload.enrollment_id, score=payload.score, teacher_id=teacher_id)
    db.add(grade)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="La matricula ya tiene nota registrada")

    db.refresh(grade)
    emit_audit(user.id, "REGISTRO_NOTA", "OK", details=f"grade_id={grade.id}")
    return grade_out(grade)


@app.put("/grades/{grade_id}", response_model=GradeOut)
def update_grade(
    grade_id: int,
    payload: GradeUpdate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles(RoleName.DOCENTE, RoleName.ADMIN)),
):
    grade = db.get(Grade, grade_id)
    if not grade:
        raise HTTPException(status_code=404, detail="Nota no encontrada")

    if user.role == RoleName.DOCENTE:
        teacher = get_teacher_profile(db, user)
        if grade.enrollment.course.teacher_id != teacher.id:
            emit_audit(
                user.id,
                "ACCESO_DENEGADO",
                "FAIL",
                details="Docente intento modificar nota en curso no asignado",
            )
            raise HTTPException(status_code=403, detail="Curso no asignado al docente")

    old_score = grade.score
    grade.score = payload.score
    db.commit()
    db.refresh(grade)
    emit_audit(
        user.id,
        "MODIFICACION_NOTA",
        "OK",
        details=f"grade_id={grade.id};old={old_score};new={payload.score}",
    )
    return grade_out(grade)
