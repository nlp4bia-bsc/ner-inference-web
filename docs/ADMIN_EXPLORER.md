# Explorador jerárquico de administración (0.12)

En `/admin/projects`, **Todos los usuarios → Usuario → Proyectos → Proyecto →
Documentos → Documento → Anotaciones** es la navegación principal. El buscador
anterior se conserva en una sección secundaria plegada. Aprobación, cuentas,
cuotas y eliminación de proyectos siguen en sus vistas y servicios existentes.

## Carga y operaciones

Las listas se piden al desplegar sus nodos, con páginas de 25 elementos. Las
anotaciones usan el endpoint existente, en páginas de 100. `details/summary`
proporciona apertura/cierre mediante Tab, Enter y Espacio sin una navegación de
página. La interfaz adapta tarjetas/tablas al móvil y comparte el tema malva y
los dieciséis idiomas. Actualizar conserva los nodos abiertos y vuelve a consultar
sus datos; las cifras son instantáneas, no estimaciones de tiempo de proceso.

Cada documento abre **el mismo visor existente**, con `?document=<id>` para
seleccionar el original correcto aunque no sea el primero. Ese visor conserva
las torres/solapes, offsets Unicode, modelos, candidatos y referencias de
normalización. Los enlaces TXT/ANN, BRAT/TSV y estadísticas JSON reutilizan las
rutas de descarga existentes. No se crea otro visualizador/exportador.

Borrar documento/proyecto usa los endpoints existentes con confirmación, CSRF y
comprobación de rol/sesión en el servidor. Tras completarse se actualizan el árbol
y las cifras globales; la cuota liberada es la del propietario, no la del
administrador. El historial de subidas permanece. La auditoría de eliminación
individual registra IDs de proyecto/documentos y propietario, nunca el texto.

## Definiciones de estadísticas

- **Usuarios:** cuentas existentes, también pendientes o suspendidas. Los proyectos
  antiguos sin propietario tienen un nodo separado y no se reasignan por email.
- **Proyectos disponibles:** no eliminados ni caducados en el momento de lectura;
  los caducados se cuentan aparte, sin documentos, anotaciones ni normalizaciones.
- **Documentos:** registros conservados del proyecto, incluidos pendientes/en proceso/
  fallidos; los borrados no contribuyen. Se muestra su distribución de estados.
- **Anotaciones:** menciones canónicas realmente publicadas. Una mención apoyada por
  dos modelos cuenta una vez; sus dos apoyos aparecen en la distribución por modelo.
  No se suman predicciones duplicadas como si fueran menciones independientes.
- **Tipos de entidad:** número de etiquetas distintas presentes en esas menciones.
  La distribución por etiqueta cuenta menciones, incluidos sus solapes.
- **Modelos:** modelos de las publicaciones conservadas o sus fuentes. Se cuentan
  también modelos publicados sin entidades detectadas cuando existe su procedencia.
  Los seleccionados en la configuración no se presentan como resultados ejecutados.
  La tabla operativa por modelo usa el progreso real de la generación actual.
- **Normalizaciones:** menciones con un resultado de normalización, una por mención;
  candidatos/referencias adicionales no multiplican el contador. Las distribuciones
  separan etiquetas, métodos públicos e idioma de terminología (incluido fallback).
- **Texto:** caracteres/palabras/tokens/frases guardados por el cálculo nativo existente.
  No se recomputa la tokenización en el administrador ni se promedian sus ratios.
  Valores ausentes permanecen desconocidos. Se suman solo mediciones disponibles.

Las cifras de proyectos en curso incluyen las publicaciones parciales disponibles.
`Partial statistics` identifica trabajos no completos o documentos cuya publicación
no se puede leer. Una publicación ausente/corrupta no se sustituye por el contador
antiguo de la base de datos. Las anotaciones borradas/caducadas no se cuentan aunque
sus antiguos resúmenes o archivos permanezcan pendientes de limpieza física.

## Consistencia, caché y compatibilidad

Los resúmenes se leen bajo el mismo bloqueo por proyecto que publicación/eliminación.
Se revalida ADMIN y la sesión después de esperar el bloqueo, y se aplica el plazo de
retención antes de acceder a archivos. Con publicaciones actuales, la agregación global recorre metadatos de
proyectos, sin cargar todos los textos ni instanciar modelos/índices. La primera
reconstrucción de formatos antiguos reutiliza el lector legado y puede leer sus
originales para validar las superficies. Una caché LRU
acotada guarda solo contadores por generación de archivo (mtime, tamaño e inode),
no superficies, términos, códigos ni documentos. Antes de combinar se vuelve a
comprobar el conjunto de proyectos y su generación; si hubo un borrado, se descarta
el proyecto eliminado o se relee el conjunto de documentos restante. Normalizar nuevamente una mención
invalida ese resumen aunque no cambie el número de anotaciones.

Los proyectos antiguos reutilizan la reconstrucción del índice desde TSV. Si se
borra uno de sus documentos, se preparan publicaciones canónicas de los originales
conservados antes de invalidar exportaciones. Se preservan solapes, normalizaciones
y las entradas del historial (también las de migraciones con IDs provisionales).
No hay migración de esquema ni reinicio de cuentas/volúmenes.

## Endpoints nuevos

Todos requieren ADMIN activo/aprobado, sesión vigente y la política opcional de MFA
solo si se habilitó explícitamente. Los usuarios normales no acceden por URL ni API.

| GET | Respuesta |
|---|---|
| `/api/admin/explorer/statistics` | Resumen global y hora de cálculo |
| `/api/admin/explorer/users?offset=0&limit=25` | Usuarios/nodo sin propietario; total y paginación |
| `/api/admin/explorer/users/{id}/projects?offset=0&limit=25` | Proyectos, perfil seguro y agregado del usuario |
| `/api/admin/explorer/projects/{id}?offset=0&limit=25` | Documentos, agregado y ejecución por modelo |

Límite máximo de página: 100. Las métricas por proyecto/usuario abarcan todo su
ámbito, no únicamente la página de elementos mostrada. La lectura de anotaciones,
texto, descargas y eliminación sigue usando `/api/jobs/{id}/...`. APP_PREFIX se
antepone uniformemente; se verifica específicamente `/annotation-tool`.
