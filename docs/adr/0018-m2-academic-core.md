# ADR 0018 — Academic Core

Status: Accepted for Education OS v0.3.0.

## Decision

El Academic Core se modela con entidades configurables:

AcademicLevel → GradeLevel → Section  
Subject → CurriculumPlan/CurriculumSubject  
Section + Subject → CourseOffering  
CourseOffering + StaffProfile → TeachingAssignment  
Enrollment + Section → StudentSectionAssignment  
CourseOffering → ScheduleSlot

`AcademicPeriod` y `Enrollment` permanecen bajo M1.

## Why

La estructura evita hardcodear nombres como EGB/BGU o paralelos A/B. Una institución
puede representar su propia estructura académica manteniendo un modelo común para
asistencia, calificaciones, analítica y automatización.
