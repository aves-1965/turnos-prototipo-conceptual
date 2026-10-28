# plan.md — Arquitectura desacoplada del Sistema de Turnos

| Campo | Valor |
|---|---|
| Versión | 0.3.0 (Fase 2) |
| Base normativa | [spec.md](spec.md) v0.3.0, en particular las secciones 2–4 y 6 |
| Fecha | 2026-10-28 |
| Estado | Plan técnico de Fase 2 |

## 1. Objetivo

Evolucionar el prototipo hacia una aplicación de tres capas con responsabilidades separadas. El frontend consume el contrato REST de turnos definido en `spec.md`; el backend aplica las reglas de negocio y persiste los cambios en una base relacional local.

## 2. Arquitectura de tres capas

| Capa | Tecnología y ubicación | Responsabilidad |
|---|---|---|
| **1. Frontend** | Prototipo `prototipo-turnos.html` | Presentar las vistas y consumir y enviar JSON por HTTP. No conserva el estado autoritativo de los turnos ni aplica por sí solo las reglas de negocio. |
| **2. Backend** | Python con FastAPI, puerto `8000`, CORS habilitado | Exponer el login y los endpoints REST de las secciones 2.4 y 3 de `spec.md`, validar permisos y reglas del dominio, calcular `fin` según RN-04 y coordinar las transacciones de persistencia. |
| **3. Persistencia** | SQLite local en `turnos.db` | Almacenar de forma duradera las entidades y los atributos ya definidos en la sección 4 de `spec.md`. Las operaciones que cambian turnos se ejecutan atómicamente. |

### Flujo de una operación

1. El usuario inicia sesión y obtiene un token Bearer conforme a la sección 2.4 de `spec.md`.
2. El frontend envía solicitudes HTTP con el token al backend y recibe respuestas JSON del contrato REST.
3. FastAPI valida la identidad y carga el rol vigente desde SQLite; luego verifica permisos y reglas aplicables.
4. El backend abre una transacción SQLite, consulta y modifica los datos existentes del modelo y confirma la transacción solo si la operación completa es válida.
5. El backend devuelve el resultado persistido o el error de dominio establecido en `spec.md`.

## 3. Desacoplamiento e integridad

Mantener los turnos en memoria JavaScript hace que el estado desaparezca al recargar la página o reiniciar el proceso que lo contiene. También deja la validación y la decisión de confirmar una reserva bajo el control de cada cliente: solicitudes simultáneas desde dos navegadores podrían observar el mismo slot como libre y ambas aceptar la reserva. Eso rompe la integridad de RN-02 y no satisface INV-03, que exige persistencia atómica y conservación de los turnos después de un reinicio.

Con el backend como autoridad, las reglas se aplican en un único punto y SQLite conserva los cambios. Las operaciones de reserva deben validar disponibilidad y escribir dentro de una transacción de escritura serializada (`BEGIN IMMEDIATE`), para que dos solicitudes concurrentes no confirmen el mismo slot. Una cancelación también debe actualizarse dentro de una transacción, incluyendo las validaciones de autorización, estado y ventana de RN-01 antes de confirmar el cambio.

## 4. Restricción de modelo (grounding)

- La única fuente para entidades y atributos persistidos es `spec.md`, sección 4.
- No crear tablas, entidades, columnas, propiedades JSON ni campos de auditoría adicionales.
- Las solicitudes y respuestas de turnos se limitan a los atributos existentes y al contrato definido en `spec.md`; `{id}` en la ruta de cancelación identifica el atributo `Turno.id`.
- Los valores derivados, como `fin`, se calculan conforme al contrato y no agregan campos al modelo.
- Si una implementación requiere una entidad o atributo no especificado, detener ese cambio y actualizar primero el contrato formal; no inferir ni inventar el esquema.

## 5. Alcance de implementación de esta fase

El backend y la base SQLite implementan las operaciones de turnos cubiertas por el contrato de `spec.md` v0.3.0. El prototipo frontend queda fuera de esta entrega; las pruebas cubren autenticación, permisos, reservas, cancelaciones, auditoría y persistencia. Las notificaciones por email y el rate limiting definidos entre los requisitos del MVP quedan pendientes de integrar con infraestructura externa.
