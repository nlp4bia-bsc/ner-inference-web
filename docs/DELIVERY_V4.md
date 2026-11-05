# Entrega V4: autenticación y aislamiento

## 1. Implementación

Registro, verificación de email, login, recuperación/cambio de contraseña,
sesiones revocables, dashboard personal, cuotas y administración con MFA. La
plataforma de trabajo requiere autenticación desde el backend. Se conserva la
inferencia incremental, el visualizador y la retención de resultados de 72 horas.
Esta fase incorpora una interfaz funcional, sin el rediseño visual completo.

## 2. Arquitectura de autenticación

Argon2id con salts individuales; sesiones opacas con verificadores en SQLite;
cookies HttpOnly/Secure/SameSite y CSRF para escrituras; límites persistentes de
intentos; tokens de email de un uso y bandeja de salida cifrada. La política
central deniega por defecto. Detalles en [AUTHENTICATION_V4.md](AUTHENTICATION_V4.md).

## 3. Usuarios y permisos

Profesión, rol USER/ADMIN y cuota son independientes. Registro siempre USER y
STANDARD. STANDARD permite 100 documentos, EXTENDED 1.000 y UNLIMITED elimina el
límite administrativo de recuento, conservando los límites técnicos. Cada trabajo
pertenece exclusivamente al usuario de la sesión; ADMIN no permite leer trabajos
clínicos ajenos. Las modificaciones administrativas quedan auditadas.

## 4. Migraciones ejecutadas

Migración aditiva 3: cuentas, sesiones, verificaciones, recuperación, auditoría,
límites, MFA, correo y propietario nullable/indexado del trabajo. Probada sobre
una copia real del esquema anterior, con fallo DDL, rollback, reintento e
idempotencia. No reinicia FIFO ni cambia offsets o vencimientos. Los trabajos
históricos sin propietario quedan inaccesibles hasta su expiración. La base del
contenedor persistente también se migró; contenía cero trabajos antes del cambio.

## 5. Inventario de rutas

[ROUTE_SECURITY_V4.md](ROUTE_SECURITY_V4.md) documenta 75 pares método/ruta,
incluidos alias antiguos, documentos, exportaciones, catálogo y OpenAPI. HTML
privado anónimo redirige al login; APIs privadas devuelven 401 y recursos ajenos
404. Las mismas reglas se aplican bajo `/ner`.

## 6. Simulaciones A–H

Superadas: A registro/verificación; B login/logout; C dos propietarios y denegación
mutua; D barrido anónimo; E escalación/mass assignment; F cuotas reales TXT/ZIP;
G sesiones, CSRF, recuperación, suspensión y MFA; H repetición con prefijo `/ner`.
La [auditoría](SECURITY_AUDIT_V4.md) relaciona escenarios y evidencias. El correo
se capturó localmente; no se afirma entrega mediante un proveedor externo.

## 7. Pruebas

Regresión completa: **168 aprobadas, cero fallos**, con navegador y NLP CPU
sintético. Entorno HTTP limpio: **128 aprobadas, 40 omisiones explícitas**.
Ruff, formato, Bandit, auditoría HTTP, paquete y Docker pasan. Hay capturas de
login/registro/dashboard con datos sintéticos. Comandos, tiempos y limitaciones
en [VERIFICATION.md](VERIFICATION.md) y [PREVIEWS.md](PREVIEWS.md).

## 8. Revisión de seguridad

[SECURITY_REVIEW_V4.md](SECURITY_REVIEW_V4.md) contiene la revisión independiente,
sus pruebas y nueve hallazgos reproducidos. No se presenta como certificación
ni prueba de invulnerabilidad.

## 9. Correcciones

Se corrigieron elevación en bootstrap, trabajo criptográfico previo a validar
recuperaciones, resurrección de sesiones, escrituras con actores revocados,
visibilidad de códigos de recuperación, entradas criptográficas malformadas,
reutilización TOTP, exposición de entradas CLI y configuración HTTPS/secretos.
La integración corrigió además formularios Chromium, expiración por inactividad,
cookies con prefijo y limpieza de vistas al cambiar de cuenta entre pestañas.

## 10. Riesgos residuales

Los perfiles neuronales conservan dos avisos de Torch, impuesto en versión 2.10.0
por el upstream fijado de ner_lab: PYSEC-2026-139 y PYSEC-2025-194. Requieren
resolución upstream antes de considerar endurecido ese despliegue. El perfil HTTP
no instala Torch y su auditoría no encuentra avisos conocidos. Informes y alcance
en [SECURITY_AUDIT_V4.md](SECURITY_AUDIT_V4.md). SQLite continúa limitado a un host.

## 11. Despliegue

Configurar primero HTTPS, origen/prefijo, cookies seguras y SMTP STARTTLS mediante
secretos privados. Detener/drenar ambos servicios y proteger una copia consistente
de SQLite y su clave antes de actualizar. Tras configurar el entorno:

```sh
docker compose build web
docker compose up -d web worker
docker compose exec web python -m scripts.create_admin
```

El bootstrap requiere terminal interactivo, email nuevo, verificación y posterior
MFA; no acepta contraseña en argumentos. Véanse [DEPLOYMENT.md](DEPLOYMENT.md),
[README](../README.md) y [RECOVERY_V4.md](RECOVERY_V4.md). Sin SMTP configurado, el
registro de producción devuelve 503: nunca verifica automáticamente la cuenta.

## 12. Pendientes externos

Validar entrega SMTP real, TLS/HSTS/proxy de BSC, textos legales institucionales,
protección de claves/backups y procedimiento excepcional de recuperación MFA.
No se probaron checkpoints clínicos, GPU, imágenes neuronales completas ni carga
externa. Resolver los avisos de Torch. La fase de rediseño visual completo queda
para el siguiente prompt.
