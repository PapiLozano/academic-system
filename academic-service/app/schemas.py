from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


# ---------------------------------------------------------------------------
# Alumnos
# ---------------------------------------------------------------------------

class StudentCreate(BaseModel):
    dni: str = Field(min_length=8, max_length=15)
    nombres: str
    apellidos: str
    correo: EmailStr
    password: str = Field(min_length=8, description="Contrasena inicial para el acceso del alumno")


class StudentUpdate(BaseModel):
    nombres: Optional[str] = None
    apellidos: Optional[str] = None
    correo: Optional[EmailStr] = None


class StudentOut(BaseModel):
    id: int
    user_id: int
    dni: str
    nombres: str
    apellidos: str
    correo: EmailStr

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Docentes
# ---------------------------------------------------------------------------

class TeacherCreate(BaseModel):
    dni: str = Field(min_length=8, max_length=15)
    nombres: str
    apellidos: str
    correo: EmailStr
    password: str = Field(min_length=8, description="Contrasena inicial para el acceso del docente")
    especialidad: Optional[str] = None


class TeacherUpdate(BaseModel):
    nombres: Optional[str] = None
    apellidos: Optional[str] = None
    correo: Optional[EmailStr] = None
    especialidad: Optional[str] = None


class TeacherOut(BaseModel):
    id: int
    user_id: int
    dni: str
    nombres: str
    apellidos: str
    correo: EmailStr
    especialidad: Optional[str]

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Cursos
# ---------------------------------------------------------------------------

class CourseCreate(BaseModel):
    nombre: str
    codigo: str
    creditos: int = Field(gt=0, le=12)
    teacher_id: Optional[int] = None


class CourseUpdate(BaseModel):
    nombre: Optional[str] = None
    codigo: Optional[str] = None
    creditos: Optional[int] = Field(default=None, gt=0, le=12)


class AssignTeacherRequest(BaseModel):
    teacher_id: int


class CourseOut(BaseModel):
    id: int
    nombre: str
    codigo: str
    creditos: int
    teacher_id: Optional[int]

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Matriculas
# ---------------------------------------------------------------------------

class EnrollmentCreate(BaseModel):
    student_id: int
    course_id: int
    ciclo: str


class EnrollmentOut(BaseModel):
    id: int
    student_id: int
    course_id: int
    ciclo: str
    fecha: date

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Calificaciones (escala 0-20)
# ---------------------------------------------------------------------------

class GradeCreate(BaseModel):
    enrollment_id: int
    score: float = Field(ge=0, le=20)


class GradeUpdate(BaseModel):
    score: float = Field(ge=0, le=20)


class GradeOut(BaseModel):
    id: int
    enrollment_id: int
    student_id: int
    course_id: int
    score: float
    date: datetime
    teacher_id: int

    class Config:
        from_attributes = True
