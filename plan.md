# plan.md — Prototipo interactivo del spec (Claude Artifact)

| Campo | Valor |
|---|---|
| Base normativa | [spec.md](spec.md) v0.1.0 · [historias-de-usuario.md](historias-de-usuario.md) |
| Fecha | 2026-10-26 |
| Estado | Pendiente de aprobación |

## 1. Formato de entrega

- Un único archivo HTML publicado como Artifact. Dentro va un solo componente React con Tailwind (`cdn.tailwindcss.com`) y Lucide Icons.
- React, Babel y Lucide se cargan desde CDN con versión fija. No hay build ni dependencias locales.
- Antes de escribirlo se carga la guía de diseño de Artifacts: tokens de color, modo oscuro y layout responsive.
- El componente es modular dentro del mismo archivo, con una sección lógica por responsabilidad:

| Módulo | Contenido |
|---|---|
| `domain/` | Funciones puras del spec: solapamiento, ventana de cancelación, validación de contacto, cálculo de slots, transiciones de estado |
| `store` | Estado único con `useReducer` y un `Context`; un reducer centralizado donde se aplican todas las reglas |
| `ClientView` | Servicio, grilla de slots, formulario, "Mis turnos" |
| `AdminView` | Agenda, métricas, bloqueos, acciones sobre turnos |
| `ui/` | Componentes compartidos: toasts, modales, badges de estado, barra superior |

## 2. Decisión de diseño clave

Toda regla vive en `domain/` y el reducer la ejecuta. La UI nunca decide si algo está permitido: solo muestra el error que devuelve el dominio, con los mismos códigos del spec (`SLOT_UNAVAILABLE`, `CANCELLATION_WINDOW_EXPIRED`, etc.). Esto simula el principio RBAC-01 de que la UI no es la barrera de seguridad.

## 3. Reglas que se implementan

- **RN-01:** cancelación del cliente bloqueada a menos de 2 h del inicio. El Administrador la salta, pero con motivo obligatorio.
- **RN-02:** sin solapamiento con intervalos `[inicio, fin)`, contigüidad válida, y sin solapar con bloqueos ni con turnos propios del cliente.
- **RN-03:** nombre, email y teléfono válidos y email verificado antes de reservar.
- **RN-04:** grilla de 15 min, antelación mínima de 1 h, horizonte de 60 días, y `fin` calculado por el sistema.
- **RN-05:** bloquear un rango con turnos activos lista los conflictos y exige confirmar la cancelación.
- **RN-06:** estados terminales, sin borrado físico.
- **RN-08:** panel de auditoría visible para el Administrador.
- **RBAC:** el cliente solo ve sus turnos. Con el cambio de rol se ve en vivo qué aparece y qué desaparece.

## 4. Datos mock en memoria

- 3 profesionales, 5 a 6 servicios con duraciones distintas (30, 45, 60 min).
- 2 clientes. Uno de ellos tiene el email sin verificar, para poder probar `EMAIL_NOT_VERIFIED`.
- Unos 12 turnos distribuidos en los próximos días: confirmados, cancelados, completados y ausentes. Incluye uno que empieza dentro de 1 h 59 min y otro a las 3 h, para probar RN-01 sin esperar.
- 1 o 2 bloqueos y horario laboral de lunes a viernes.
- Las fechas son relativas a "hoy" real, así que el prototipo no envejece.
- Una sola fuente de datos alimenta ambas vistas, así que cualquier acción en una se refleja de inmediato en la otra.

## 5. Vistas

- **Barra superior:** el selector Cliente/Administrador, el usuario activo (con selector entre los 2 clientes mock) y un reloj simulado con botones para avanzar tiempo (+1 h, +1 día). El reloj sirve para auditar RN-01 y los estados `COMPLETADO`/`AUSENTE`.
- **Cliente:**
  - Elige servicio, profesional y fecha.
  - Ve la grilla de slots y un modal de confirmación con los datos de contacto.
  - Ve "Mis turnos", con el botón de cancelar deshabilitado y con tooltip explicativo dentro de las 2 h.
- **Administrador:**
  - Vista de agenda día/semana y vista de lista.
  - Métricas: turnos por período, tasas de cancelación y ausentismo, ocupación y top servicios.
  - Acciones sobre turnos: cancelar con motivo, completar y marcar ausente.
  - Gestión de bloqueos.
  - Un filtro de profesional para el rol `ADMIN`.

## 6. Verificación

- Probar en el navegador integrado los 8 escenarios de aceptación del spec §8, incluyendo el doble clic y la reserva del mismo slot desde dos clientes (concurrencia simulada en el reducer).
- Revisar la consola, el ancho móvil y el modo oscuro antes de publicar.
- Entregar el link del Artifact y una tabla que cruza cada escenario con el resultado observado.

## 7. Decisiones tomadas (por defecto, salvo indicación contraria)

| # | Tema | Decisión |
|---|---|---|
| 1 | Reloj simulado con botones para avanzar tiempo | **Sí** |
| 2 | Selector "Profesional / ADMIN" en la vista Administrador | **Sí** |
| 3 | Emails como "bandeja simulada" (F-13) | **Sí**, panel lateral colapsable |
| 4 | Reducir el horario laboral con turnos reservados (Q-01) | **Fuera** del prototipo; solo se implementa el bloqueo (RN-05) |
| 5 | Persistencia entre recargas | **No**: todo en memoria, con botón "Reiniciar datos" |
