from datetime import date, datetime

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base


class Student(Base):
    __tablename__ = "alumnos"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, unique=True, nullable=False, index=True)  # id en el Servicio de Autenticacion
    dni = Column(String(15), unique=True, nullable=False)
    nombres = Column(String(100), nullable=False)
    apellidos = Column(String(100), nullable=False)
    correo = Column(String(150), unique=True, nullable=False)
    creado_en = Column(DateTime, default=datetime.utcnow, nullable=False)

    enrollments = relationship("Enrollment", back_populates="student")


class Teacher(Base):
    __tablename__ = "docentes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, unique=True, nullable=False, index=True)  # id en el Servicio de Autenticacion
    dni = Column(String(15), unique=True, nullable=False)
    nombres = Column(String(100), nullable=False)
    apellidos = Column(String(100), nullable=False)
    correo = Column(String(150), unique=True, nullable=False)
    especialidad = Column(String(150), nullable=True)
    creado_en = Column(DateTime, default=datetime.utcnow, nullable=False)

    courses = relationship("Course", back_populates="teacher")


class Course(Base):
    __tablename__ = "cursos"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(150), nullable=False)
    codigo = Column(String(30), unique=True, nullable=False)
    creditos = Column(Integer, nullable=False)
    teacher_id = Column(Integer, ForeignKey("docentes.id"), nullable=True)

    teacher = relationship("Teacher", back_populates="courses")
    enrollments = relationship("Enrollment", back_populates="course")


class Enrollment(Base):
    __tablename__ = "matriculas"
    __table_args__ = (UniqueConstraint("student_id", "course_id", "ciclo", name="uq_matricula_unica"),)

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("alumnos.id"), nullable=False)
    course_id = Column(Integer, ForeignKey("cursos.id"), nullable=False)
    ciclo = Column(String(20), nullable=False)
    fecha = Column(Date, default=date.today, nullable=False)

    student = relationship("Student", back_populates="enrollments")
    course = relationship("Course", back_populates="enrollments")
    grade = relationship("Grade", back_populates="enrollment", uselist=False)


class Grade(Base):
    __tablename__ = "calificaciones"

    id = Column(Integer, primary_key=True, index=True)
    enrollment_id = Column(Integer, ForeignKey("matriculas.id"), unique=True, nullable=False)
    score = Column(Float, nullable=False)
    date = Column(DateTime, default=datetime.utcnow, nullable=False)
    teacher_id = Column(Integer, ForeignKey("docentes.id"), nullable=False)

    enrollment = relationship("Enrollment", back_populates="grade")
