# Education OS — M5 Automation Engine

Release: v0.6.0  
Base: M4 v0.5.2  
Status tras instalación: IMPLEMENTED — pendiente del gate local + GitHub CI.

## Loop cubierto

Dato → Evento → Contexto → Señal → Acción → Seguimiento → Escalamiento → Cierre

## Human-in-the-loop

El motor puede:
- detectar una señal existente;
- abrir un caso;
- crear una tarea;
- marcar vencimiento/escalamiento;
- registrar eventos.

El motor NO puede:
- sancionar;
- suspender;
- bloquear acceso;
- negar matrícula;
- decidir promoción;
- emitir diagnósticos.
