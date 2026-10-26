# historias-de-usuario.md — Historias de Usuario Críticas del MVP

| Campo | Valor |
|---|---|
| Base normativa | [spec.md](spec.md) v0.1.0 |
| Fecha | 2026-10-26 |
| Alcance | Flujo 1 (Reserva y confirmación, Cliente) · Flujo 2 (Agenda y cancelación, Administrador) |

**Convenciones**
- "Administrador" en este documento designa a `PROFESIONAL` (sobre su propia agenda) o `ADMIN` (sobre cualquier agenda), según la matriz RBAC del spec §2.2. Donde la regla difiere, se indica.
- Cada historia referencia las reglas del spec que la gobiernan (`RN-xx`, `RBAC-xx`, `F-xx`).
- Los casos borde (EC) y errores (ERR) se expresan también como escenarios Gherkin ejecutables, para derivar tests directamente.
- Los instantes se razonan en la zona horaria de operación; se almacenan en UTC (RN-04). Salvo indicación, "ahora" = `2026-11-02 09:00`.
- Códigos de error según spec §7.

---

## Mapa de historias

| ID | Flujo | Historia | Spec |
|---|---|---|---|
| HU-01 | 1 | Consultar disponibilidad | F-02, F-03, RN-04 |
| HU-02 | 1 | Reservar un turno | F-04, RN-02, RN-03, RN-04 |
| HU-03 | 1 | Recibir confirmación de la reserva | F-13, RN-08 |
| HU-04 | 1 | Cancelar mi propio turno (complementaria) | F-06, RN-01, RBAC-02 |
| HU-05 | 2 | Definir horario laboral y ver agenda | F-08, F-10 |
| HU-06 | 2 | Bloquear un rango horario | F-09, RN-05 |
| HU-07 | 2 | Cancelar el turno de un cliente | F-11, RN-01, RN-06 |

---

# FLUJO 1 — Reserva y confirmación de turno (Cliente)

## HU-01 — Consultar disponibilidad

> **Como** Cliente, **quiero** ver los horarios libres de un servicio en una fecha dada, **para** elegir un turno sin tener que probar a ciegas.

**Reglas aplicables:** F-03, RN-02 (slots libres excluyen turnos activos), RN-04 (grilla, antelación mínima, horizonte), RN-05 (bloqueos).

### Criterios de aceptación

```gherkin
Escenario: Mostrar solo slots realmente libres
  Dado que el servicio "Consulta general" dura 30 minutos
  Y el profesional Ana atiende el lunes de 09:00 a 13:00
  Y Ana tiene un turno CONFIRMADO el lunes de 10:00 a 10:30
  Y Ana tiene un bloqueo el lunes de 11:00 a 12:00
  Cuando el Cliente consulta la disponibilidad del lunes 2026-11-09
  Entonces el sistema muestra los slots 09:00, 09:30, 10:30, 12:00 y 12:30
  Y no muestra 10:00, 11:00 ni 11:30
```

```gherkin
Escenario: El slot aparece libre tras una cancelación
  Dado que existe un turno CONFIRMADO el lunes de 10:00 a 10:30
  Cuando ese turno pasa a estado CANCELADO
  Y el Cliente consulta la disponibilidad del lunes
  Entonces el slot 10:00 aparece como libre
```

```gherkin
Escenario: Un Anónimo puede consultar pero no reservar
  Dado que el visitante no inició sesión
  Cuando consulta la disponibilidad de un servicio
  Entonces ve los slots libres
  Y al intentar reservar el sistema le solicita iniciar sesión
```

### Casos borde y errores a prevenir

```gherkin
Escenario: EC-01.1 — No ofrecer slots dentro de la antelación mínima
  Dado que ahora es 2026-11-02 09:00 y la antelación mínima es 1 hora
  Cuando el Cliente consulta la disponibilidad del día de hoy
  Entonces no se muestran slots con inicio anterior a las 10:00
```

```gherkin
Escenario: EC-01.2 — No ofrecer slots que no entran antes del fin de jornada
  Dado que el profesional atiende hasta las 13:00
  Y el servicio dura 45 minutos
  Cuando el Cliente consulta la disponibilidad
  Entonces el último slot ofrecido inicia a las 12:15
  Y no se ofrece ningún slot cuyo fin supere las 13:00
```

```gherkin
Escenario: EC-01.3 — Fecha fuera del horizonte máximo
  Dado que el horizonte máximo de reserva es 60 días
  Cuando el Cliente consulta una fecha a 61 días
  Entonces el sistema responde INVALID_TIME_RANGE
  Y no devuelve slots
```

```gherkin
Escenario: EC-01.4 — Servicio desactivado
  Dado que el servicio fue desactivado por baja lógica
  Cuando el Cliente consulta su disponibilidad
  Entonces el sistema responde que el servicio no está disponible
  Y no devuelve slots
```

```gherkin
Escenario: EC-01.5 — Cambio de horario de verano (DST)
  Dado que la zona de operación tiene un cambio de hora ese día
  Cuando el Cliente consulta la disponibilidad
  Entonces los slots se calculan en UTC y se muestran sin duplicar ni omitir horas locales
```

---

## HU-02 — Reservar un turno

> **Como** Cliente, **quiero** reservar un turno en un horario libre de un servicio, **para** asegurar mi atención con el profesional sin coordinar por otros medios.

**Reglas aplicables:** F-04, RN-02, RN-03, RN-04, RN-06, RBAC-03, RBAC-04.

### Criterios de aceptación

```gherkin
Escenario: Reserva exitosa
  Dado que el Cliente tiene sesión iniciada
  Y su perfil tiene nombre completo, email verificado y teléfono válido
  Y el slot lunes 2026-11-09 10:00 del servicio "Consulta general" (30 min) está libre
  Cuando el Cliente confirma la reserva de ese slot
  Entonces se crea un Turno en estado CONFIRMADO
  Y su fin se calcula en servidor como 10:30
  Y el slot deja de aparecer como disponible
  Y se registra un evento de auditoría con actor, rol e instante UTC
```

```gherkin
Escenario: El cliente no puede enviar el fin del turno
  Dado que el Cliente envía una solicitud con "inicio" y un "fin" propio
  Cuando el servidor procesa la solicitud
  Entonces ignora o rechaza el valor de "fin"
  Y calcula "fin" como inicio + duración del servicio
```

```gherkin
Escenario: Turnos contiguos son válidos
  Dado que existe un turno CONFIRMADO del profesional de 10:00 a 10:30
  Cuando otro Cliente reserva el slot de 10:30 a 11:00
  Entonces la reserva se confirma
```

### Casos borde y errores a prevenir

```gherkin
Escenario: ERR-02.1 — Solapamiento parcial
  Dado que existe un turno CONFIRMADO del profesional de 10:00 a 10:30
  Cuando otro Cliente intenta reservar de 10:15 a 10:45
  Entonces el sistema responde SLOT_UNAVAILABLE (409)
  Y no persiste ningún turno
```

```gherkin
Escenario: EC-02.2 — Concurrencia sobre el mismo slot
  Dado que dos Clientes distintos envían simultáneamente la reserva del mismo slot libre
  Cuando ambas solicitudes llegan al servidor casi al mismo tiempo
  Entonces exactamente una se confirma
  Y la otra recibe SLOT_UNAVAILABLE
  Y la base de datos rechaza el solapamiento aunque falle la validación de aplicación
```

```gherkin
Escenario: ERR-02.3 — Doble envío del mismo cliente (doble clic / reintento)
  Dado que el Cliente ya tiene un turno CONFIRMADO en un slot
  Cuando reenvía la misma solicitud de reserva
  Entonces no se crea un segundo turno
  Y la respuesta es SLOT_UNAVAILABLE o el turno ya existente (idempotente)
```

```gherkin
Escenario: ERR-02.4 — Datos de contacto inválidos o faltantes
  Dado que el perfil del Cliente no tiene un teléfono válido
  Cuando intenta reservar un slot libre
  Entonces el sistema responde INVALID_CONTACT (422)
  Y no persiste el turno
  Y indica qué campo debe corregirse
```

```gherkin
Escenario: ERR-02.5 — Email sin verificar
  Dado que el Cliente aún no confirmó su email
  Cuando intenta reservar
  Entonces el sistema responde EMAIL_NOT_VERIFIED (403)
  Y ofrece reenviar el enlace de verificación
```

```gherkin
Escenario: ERR-02.6 — Cliente con turnos propios solapados
  Dado que el Cliente tiene un turno CONFIRMADO con el profesional A de 10:00 a 10:30
  Cuando intenta reservar de 10:15 a 10:45 con el profesional B
  Entonces el sistema responde SLOT_UNAVAILABLE
  Y no persiste el turno
```

```gherkin
Escenario: ERR-02.7 — Inicio en el pasado o dentro de la antelación mínima
  Dado que ahora es 2026-11-02 09:00 y la antelación mínima es 1 hora
  Cuando el Cliente intenta reservar para las 09:30 de hoy
  Entonces el sistema responde INVALID_TIME_RANGE (422)
```

```gherkin
Escenario: ERR-02.8 — Inicio fuera de la grilla de slots
  Dado que la grilla es de 15 minutos
  Cuando el Cliente intenta reservar con inicio a las 10:07
  Entonces el sistema responde INVALID_TIME_RANGE
```

```gherkin
Escenario: ERR-02.9 — Slot dentro de un bloqueo o fuera del horario laboral
  Dado que el profesional tiene un bloqueo de 11:00 a 12:00
  Cuando el Cliente intenta reservar a las 11:30 (por llamada directa a la API)
  Entonces el sistema responde SLOT_UNAVAILABLE
  Y lo mismo ocurre para un horario fuera de la jornada laboral
```

```gherkin
Escenario: ERR-02.10 — Servicio desactivado entre la consulta y la reserva
  Dado que el Cliente vio el slot cuando el servicio estaba activo
  Y el profesional lo desactivó antes de confirmar
  Cuando el Cliente confirma la reserva
  Entonces el sistema rechaza la operación con un error de servicio no disponible
  Y no persiste el turno
```

```gherkin
Escenario: ERR-02.11 — Un rol sin permiso de reserva
  Dado que un usuario con rol PROFESIONAL intenta crear un turno para sí mismo como cliente
  Cuando envía la solicitud
  Entonces el sistema responde FORBIDDEN
```

---

## HU-03 — Recibir confirmación de la reserva

> **Como** Cliente, **quiero** recibir una confirmación inmediata de mi turno, **para** tener certeza de fecha, hora, servicio y política de cancelación.

**Reglas aplicables:** F-13, F-05, RN-01 (se informa la ventana), RN-08.

### Criterios de aceptación

```gherkin
Escenario: Confirmación en pantalla y por email
  Dado que el Cliente acaba de reservar un turno CONFIRMADO
  Cuando el sistema persiste el turno
  Entonces muestra una pantalla de confirmación con servicio, profesional, fecha, hora de inicio y fin
  Y envía un email a la dirección verificada del Cliente con los mismos datos
  Y el email indica que la cancelación solo es posible hasta 2 horas antes del inicio
```

```gherkin
Escenario: El turno aparece en "Mis turnos"
  Dado que el Cliente reservó un turno futuro
  Cuando abre "Mis turnos"
  Entonces ve el turno en la lista de próximos con estado CONFIRMADO
  Y no ve turnos de otros clientes
```

### Casos borde y errores a prevenir

```gherkin
Escenario: ERR-03.1 — Falla el envío del email
  Dado que el servicio de email no está disponible
  Cuando el Cliente reserva un turno
  Entonces el turno queda igualmente CONFIRMADO
  Y el envío se reintenta de forma asíncrona
  Y la pantalla de confirmación sigue mostrándose
```

```gherkin
Escenario: EC-03.2 — La reserva fallida no genera confirmación
  Dado que la reserva termina en SLOT_UNAVAILABLE
  Cuando el sistema responde
  Entonces no se envía ningún email de confirmación
```

```gherkin
Escenario: EC-03.3 — Confirmación no duplicada ante reintentos
  Dado que el Cliente reenvía la misma reserva por doble clic
  Cuando el sistema detecta la solicitud repetida
  Entonces se envía a lo sumo un email de confirmación
```

```gherkin
Escenario: EC-03.4 — Hora mostrada en la zona horaria correcta
  Dado que el turno se almacenó en UTC
  Cuando se muestra la confirmación o se envía el email
  Entonces la hora se expresa en la zona horaria de operación
```

---

## HU-04 — Cancelar mi propio turno (complementaria al Flujo 1)

> **Como** Cliente, **quiero** cancelar un turno propio con anticipación suficiente, **para** liberar el horario si no puedo asistir.

**Reglas aplicables:** F-06, RN-01, RN-06, RBAC-02. Se incluye por ser el contraste directo de la excepción del Administrador (HU-07).

### Criterios de aceptación

```gherkin
Escenario: Cancelación dentro de la ventana permitida
  Dado que el Cliente tiene un turno CONFIRMADO que inicia en 3 horas
  Cuando lo cancela
  Entonces el turno pasa a CANCELADO
  Y el slot queda disponible para otros clientes
  Y se envía un email de cancelación al Cliente
  Y se registra la auditoría con actor y rol CLIENTE
```

### Casos borde y errores a prevenir

```gherkin
Escenario: ERR-04.1 — Cancelación fuera de la ventana
  Dado que el Cliente tiene un turno CONFIRMADO que inicia en 1 hora 59 minutos
  Cuando intenta cancelarlo
  Entonces el sistema responde CANCELLATION_WINDOW_EXPIRED (409)
  Y el turno permanece CONFIRMADO
```

```gherkin
Escenario: EC-04.2 — Límite exacto de la ventana
  Dado que el turno inicia exactamente en 2 horas
  Cuando el Cliente lo cancela
  Entonces la cancelación se acepta
  Y un segundo antes del límite deja de aceptarse
```

```gherkin
Escenario: ERR-04.3 — Turno en estado terminal
  Dado que el turno está CANCELADO, COMPLETADO o AUSENTE
  Cuando el Cliente intenta cancelarlo
  Entonces el sistema responde INVALID_STATE_TRANSITION (409)
```

```gherkin
Escenario: ERR-04.4 — Cancelar el turno de otro cliente
  Dado que el turno T pertenece al Cliente A
  Cuando el Cliente B intenta cancelar T
  Entonces el sistema responde 404
  Y no revela la existencia de T
```

```gherkin
Escenario: EC-04.5 — Doble cancelación simultánea
  Dado que el Cliente envía dos solicitudes de cancelación casi simultáneas
  Cuando ambas se procesan
  Entonces solo una efectúa la transición
  Y la otra recibe INVALID_STATE_TRANSITION sin duplicar emails ni eventos de auditoría
```

---

# FLUJO 2 — Gestión de agenda y cancelación de turno (Administrador)

## HU-05 — Definir horario laboral y ver la agenda

> **Como** Administrador, **quiero** definir mi horario laboral semanal y ver mi agenda diaria y semanal con los turnos, **para** que solo se reserve dentro de mi disponibilidad real y poder planificar mi trabajo.

**Reglas aplicables:** F-08, F-10, RBAC-01, RBAC-04, RN-02, RN-04.

### Criterios de aceptación

```gherkin
Escenario: Definir el horario laboral semanal
  Dado que el profesional Ana tiene sesión iniciada
  Cuando define lunes a viernes de 09:00 a 13:00
  Entonces el sistema guarda el horario recurrente
  Y la disponibilidad de los clientes solo ofrece slots dentro de ese horario
```

```gherkin
Escenario: Ver la agenda con datos de los clientes
  Dado que Ana tiene turnos CONFIRMADOS el lunes
  Cuando abre su agenda semanal
  Entonces ve cada turno con hora, servicio, estado y datos de contacto del cliente
  Y no ve turnos de otros profesionales
```

```gherkin
Escenario: El ADMIN ve todas las agendas
  Dado que un usuario con rol ADMIN tiene sesión iniciada
  Cuando filtra por cualquier profesional
  Entonces ve su agenda completa
```

### Casos borde y errores a prevenir

```gherkin
Escenario: ERR-05.1 — Reducir el horario deja turnos fuera de jornada
  Dado que Ana tiene un turno CONFIRMADO el lunes a las 12:30
  Cuando intenta cambiar su horario del lunes a 09:00–12:00
  Entonces el sistema lista los turnos en conflicto
  Y no aplica el cambio hasta que Ana los cancele o confirme hacerlo (aplicando HU-07)
  Y los turnos existentes no se eliminan silenciosamente
```

```gherkin
Escenario: ERR-05.2 — Rango horario inválido
  Cuando el Administrador define un horario con fin anterior o igual al inicio
  O con franjas solapadas para el mismo día
  Entonces el sistema responde INVALID_TIME_RANGE
  Y no guarda el horario
```

```gherkin
Escenario: ERR-05.3 — Un PROFESIONAL no puede editar la agenda de otro
  Dado que Ana intenta modificar el horario del profesional Bruno
  Cuando envía la solicitud
  Entonces el sistema responde 404 o FORBIDDEN según RBAC-02
```

```gherkin
Escenario: EC-05.4 — Un CLIENTE no accede a la agenda
  Dado que un usuario con rol CLIENTE intenta abrir una agenda
  Cuando envía la solicitud
  Entonces el sistema responde FORBIDDEN
```

```gherkin
Escenario: EC-05.5 — Agenda vacía
  Dado que no hay turnos en el período consultado
  Cuando el Administrador abre la agenda
  Entonces ve el calendario vacío sin errores
```

---

## HU-06 — Bloquear un rango horario

> **Como** Administrador, **quiero** bloquear rangos de tiempo (vacaciones, almuerzo, imprevistos), **para** que ningún cliente pueda reservar mientras no estoy disponible.

**Reglas aplicables:** F-09, RN-05, RN-02, RN-01 (excepción), RN-08.

### Criterios de aceptación

```gherkin
Escenario: Bloqueo de un rango libre
  Dado que Ana no tiene turnos el martes entre 12:00 y 14:00
  Cuando crea un bloqueo martes 12:00–14:00 con motivo "Almuerzo"
  Entonces el bloqueo se guarda
  Y los slots de ese rango dejan de aparecer en la disponibilidad
```

```gherkin
Escenario: Desbloquear un rango
  Dado que existe un bloqueo martes 12:00–14:00
  Cuando Ana lo elimina
  Entonces los slots vuelven a estar disponibles
```

### Casos borde y errores a prevenir

```gherkin
Escenario: ERR-06.1 — Bloqueo sobre turnos activos, sin confirmar
  Dado que Ana tiene un turno CONFIRMADO el martes de 12:30 a 13:00
  Cuando intenta bloquear martes 12:00–14:00 sin confirmar la cancelación
  Entonces el sistema lista el turno en conflicto
  Y no crea el bloqueo
```

```gherkin
Escenario: EC-06.2 — Bloqueo sobre turnos activos, con confirmación
  Dado que Ana tiene un turno CONFIRMADO dentro del rango a bloquear
  Cuando crea el bloqueo y confirma cancelar los turnos en conflicto indicando un motivo
  Entonces los turnos pasan a CANCELADO con ese motivo
  Y se crea el bloqueo
  Y los clientes afectados reciben un email de cancelación
  Y todo ocurre en una sola transacción (si algo falla, no se aplica nada)
```

```gherkin
Escenario: ERR-06.3 — Bloqueo con rango inválido
  Cuando el Administrador crea un bloqueo con fin menor o igual al inicio
  Entonces el sistema responde INVALID_TIME_RANGE
```

```gherkin
Escenario: EC-06.4 — Bloqueo en el pasado
  Cuando el Administrador intenta bloquear un rango que ya terminó
  Entonces el sistema lo rechaza con INVALID_TIME_RANGE
```

```gherkin
Escenario: EC-06.5 — Bloqueos que se solapan entre sí
  Dado que existe un bloqueo martes 12:00–14:00
  Cuando se crea otro de 13:00 a 15:00
  Entonces el sistema los fusiona o rechaza el solapamiento sin duplicar el efecto
```

```gherkin
Escenario: EC-06.6 — Carrera entre bloqueo y reserva
  Dado que un Cliente reserva un slot mientras el Administrador bloquea ese rango
  Cuando ambas operaciones llegan casi simultáneamente
  Entonces la integridad se preserva: o la reserva se confirma y el bloqueo reporta conflicto,
       o el bloqueo se crea y la reserva recibe SLOT_UNAVAILABLE
  Y nunca coexisten un turno CONFIRMADO y un bloqueo en el mismo rango
```

---

## HU-07 — Cancelar el turno de un cliente

> **Como** Administrador, **quiero** cancelar un turno de mi agenda indicando un motivo, **para** resolver imprevistos y que el cliente sea notificado de inmediato.

**Reglas aplicables:** F-11, RN-01 (excepción), RN-06, RN-08, RBAC-01, RBAC-02.

### Criterios de aceptación

```gherkin
Escenario: Cancelación por el Administrador dentro de la ventana normal
  Dado que Ana tiene un turno CONFIRMADO que inicia en 24 horas
  Cuando lo cancela indicando el motivo "Imprevisto médico"
  Entonces el turno pasa a CANCELADO
  Y se guarda el motivo y quién canceló
  Y el slot queda libre
  Y el Cliente recibe un email con el motivo
  Y se registra la auditoría con actor, rol, instante UTC y motivo
```

```gherkin
Escenario: Cancelación fuera de la ventana de 2 horas (excepción de RN-01)
  Dado que el turno inicia en 30 minutos
  Cuando el Administrador lo cancela con un motivo
  Entonces la cancelación se acepta, sin aplicar la ventana mínima
  Y el Cliente es notificado
```

### Casos borde y errores a prevenir

```gherkin
Escenario: ERR-07.1 — Motivo obligatorio
  Cuando el Administrador intenta cancelar sin motivo (vacío o solo espacios)
  Entonces el sistema responde con error de validación
  Y el turno permanece CONFIRMADO
```

```gherkin
Escenario: ERR-07.2 — Estados terminales no cancelables
  Dado que el turno está CANCELADO, COMPLETADO o AUSENTE
  Cuando el Administrador intenta cancelarlo
  Entonces el sistema responde INVALID_STATE_TRANSITION (409)
```

```gherkin
Escenario: ERR-07.3 — Turno ya iniciado
  Dado que el turno inició hace 10 minutos
  Cuando el Administrador intenta cancelarlo
  Entonces el sistema responde INVALID_STATE_TRANSITION
  Y sugiere marcarlo como COMPLETADO o AUSENTE según corresponda
```

```gherkin
Escenario: ERR-07.4 — Agenda ajena
  Dado que Ana (PROFESIONAL) intenta cancelar un turno de la agenda de Bruno
  Cuando envía la solicitud
  Entonces el sistema responde 404
  Y un ADMIN sí podría cancelarlo
```

```gherkin
Escenario: ERR-07.5 — Un Cliente intenta usar la acción de Administrador
  Dado que un Cliente envía directamente la llamada de cancelación con motivo omitiendo la ventana
  Cuando el servidor valida el rol
  Entonces aplica RN-01 y RBAC (sin la excepción)
  Y la UI nunca es la barrera de seguridad
```

```gherkin
Escenario: EC-07.6 — Email de cancelación falla
  Dado que el servicio de email no está disponible
  Cuando el Administrador cancela un turno
  Entonces el turno queda CANCELADO
  Y la notificación se reintenta de forma asíncrona
```

```gherkin
Escenario: EC-07.7 — Cancelación simultánea Cliente vs. Administrador
  Dado que el Cliente y el Administrador cancelan el mismo turno al mismo tiempo
  Cuando ambas solicitudes se procesan
  Entonces solo una efectúa la transición
  Y la otra recibe INVALID_STATE_TRANSITION
  Y el cliente recibe un único email de cancelación
```

```gherkin
Escenario: EC-07.8 — El historial es inmutable
  Dado que el turno fue cancelado
  Entonces permanece visible en el historial con motivo y quién canceló
  Y no puede eliminarse físicamente
```

---

# Matriz de trazabilidad (Historia → Regla → Escenarios)

| Regla del spec | Historias | Escenarios clave |
|---|---|---|
| RN-01 Ventana de cancelación | HU-04, HU-07 | ERR-04.1, EC-04.2, ERR-07.5 y excepción HU-07 |
| RN-02 Sin solapamiento | HU-01, HU-02, HU-06 | ERR-02.1, EC-02.2, ERR-02.6, EC-06.6 |
| RN-03 Contacto válido | HU-02 | ERR-02.4, ERR-02.5 |
| RN-04 Integridad temporal | HU-01, HU-02 | EC-01.1, EC-01.3, ERR-02.7, ERR-02.8 |
| RN-05 Bloqueos | HU-06 | ERR-06.1, EC-06.2, EC-06.5 |
| RN-06 Ciclo de vida | HU-04, HU-07 | ERR-04.3, ERR-07.2, ERR-07.3, EC-07.8 |
| RN-08 Auditoría | HU-02, HU-04, HU-07 | Escenarios principales |
| RBAC-01/02/04 | HU-04, HU-05, HU-07 | ERR-04.4, ERR-05.3, EC-05.4, ERR-07.4 |

# Preguntas abiertas detectadas al derivar las historias

| # | Pregunta | Impacto |
|---|---|---|
| Q-01 | ¿El spec debe definir qué ocurre al reducir el horario laboral con turnos ya reservados (ERR-05.1)? Aquí se asumió "listar conflictos y exigir confirmación", igual que RN-05. | Ampliar RN-05 al horario laboral |
| Q-02 | ¿Hay un tope de longitud/forma del motivo de cancelación? | Validación de ERR-07.1 |
| Q-03 | ¿La reserva debe ser idempotente por clave de solicitud o basta con rechazar el duplicado? | ERR-02.3, EC-03.3 |
| Q-04 | ¿Bloqueos solapados se fusionan o se rechazan? | EC-06.5 |
| Q-05 | ¿Un turno en curso puede cancelarse por el Administrador? El spec no lo permite (RN-06); se mantuvo así en ERR-07.3. | Revisar RN-06 |
