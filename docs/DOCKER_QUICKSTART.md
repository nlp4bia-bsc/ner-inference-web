# Docker en bscdspace: Apache y /annotation-tool

La configuración genérica está en `docker-compose.yml`; la de producción en
`docker-compose.apache.yml`. Se levantan **web y worker**, sin Caddy ni otro proxy.
Apache sigue atendiendo HTTPS y las instalaciones WordPress de las demás rutas.
El backend solo publica **127.0.0.1:8000**. El worker utiliza CPU.

## Actualizar la instalación existente

Trabaja en el **mismo directorio del repositorio y proyecto Compose existentes**,
en la rama `work`. Conserva el mismo `COMPOSE_PROJECT_NAME` si ya lo usáis: cambiar
el nombre/directorio del proyecto puede seleccionar otro volumen.

El `.env` privado del servidor ya contiene:

```dotenv
APP_PREFIX=/annotation-tool
COMPOSE_FILE=docker-compose.yml:docker-compose.apache.yml
```

**No copies `.env.example` encima de ese archivo.** Conserva todas sus demás
variables, credenciales y ajustes privados. El perfil Apache fija producción,
cookies Secure y `PUBLIC_BASE_URL=https://temu.bsc.es/annotation-tool` en ambos
servicios; no cambia APP_PREFIX. MFA y verificación por correo siguen desactivados
por defecto. La cuenta de administrador existente se conserva.

Prepara una copia consistente y privada del almacenamiento/SQLite/claves conforme
a vuestra política. Deja terminar los trabajos activos antes de la parada prevista.
Los siguientes comandos no eliminan ni recrean volúmenes:

```bash
git switch work
git pull --ff-only

# Deben aparecer web y worker, y el volumen declarado ner-data.
docker compose config --services
docker compose config --volumes

# Construye antes de parar: si falla el build, la versión anterior sigue en marcha.
docker compose build web worker
docker compose stop web worker
docker compose up -d --no-deps web worker

docker compose ps
docker compose logs --tail=100 web worker
```

**No ejecutes `down -v`, `volume rm`, `volume prune` ni cambies el nombre del
volumen/proyecto.** `up` puede sustituir los contenedores para aplicar las imágenes;
el volumen `ner-data:/data` y los directorios privados montados se conservan.
No se utiliza `--remove-orphans`, que podría afectar a otros servicios del proyecto.

Se mantienen estos montajes:

| Recurso | Uso |
|---|---|
| `ner-data:/data` | Base de datos, documentos, resultados, claves y cachés persistentes |
| `./catalog:/service/catalog:ro` | Catálogo configurado por la institución |
| `./models:/models:ro` | Recursos locales opcionales |
| `./gazetteers:/gazetteers:ro` | Parquet e inventario privado, fuera de Git e imágenes |

El primer uso de un modelo descarga sus pesos y reutiliza después la caché; no hay
compilación ni descarga de modelos durante el build. El perfil CPU conserva
**`numpy==2.3.5`** en `requirements-cpu.lock` para evitar la incompatibilidad X86_V2
señalada en este servidor. No lo actualices separadamente dentro del contenedor.
Las dependencias GPU mantienen su perfil opcional independiente; no se activa aquí.

## Comprobar el arranque y Apache

```bash
curl --fail http://127.0.0.1:8000/annotation-tool/health
curl --fail https://temu.bsc.es/annotation-tool/health
curl --fail https://temu.bsc.es/annotation-tool/ready

docker compose exec worker python -m scripts.check_config --expect-origin https://temu.bsc.es
docker compose logs -f worker
```

`/ready` exige un heartbeat reciente del worker. La comprobación de origen recibe
solo esquema/dominio/puerto; APP_PREFIX se comprueba por separado en la configuración.
Abre **https://temu.bsc.es/annotation-tool/** y entra con tu administrador. En
**Administración → Todos los proyectos** encontrarás el árbol por usuario,
proyecto, documento y anotaciones, con estadísticas y acciones sobre otros propietarios.

Si Apache ya sirve esta ruta correctamente, **no cambies su configuración**.
La correspondencia debe conservar el prefijo hacia el backend. Como referencia,
estas directivas se limitan a la ruta de la aplicación dentro del vhost HTTPS
existente; no sustituyen el vhost, certificados ni reglas WordPress:

```apache
ProxyPass        "/annotation-tool/" "http://127.0.0.1:8000/annotation-tool/"
ProxyPassReverse "/annotation-tool/" "http://127.0.0.1:8000/annotation-tool/"
<Location "/annotation-tool/">
    RequestHeader set X-Forwarded-Proto "https"
</Location>
```

El perfil solicitado habilita `--proxy-headers --forwarded-allow-ips=*`; depende de
que el puerto del backend siga ligado a loopback y Apache fije la cabecera de esquema.
No expongas el 8000 en una interfaz pública. El TLS sigue siendo responsabilidad del
Apache ya instalado. No hace falta abrir otro puerto ni instalar otro proxy.

## Operaciones de aplicación

Conserva el administrador existente: no vuelvas a ejecutar `create_admin` al
actualizar. Solo una instalación nueva sin administrador necesita:

```bash
docker compose exec web python -m scripts.create_admin
```

Las nuevas solicitudes de acceso requieren aprobación administrativa. Las cuotas
numéricas, eliminación de cuentas y proyectos, expiración y registro de auditoría
siguen disponibles. Los originales conservados pueden descargarse mientras se
procesa el trabajo; BRAT/TSV/estadísticas finales se ofrecen cuando su publicación
ha terminado. Borrar un documento invalida los paquetes antiguos y el worker
reconstruye las exportaciones restantes, sin volver a ejecutar NER.

Los gazetteers confidenciales siguen en `gazetteers/`; para importarlos utiliza
[las instrucciones de normalización](NORMALIZATION.md), sin subirlos al repositorio.
Para copias/restauración y retención, consulta [despliegue](DEPLOYMENT.md) y
[retención](RETENTION_POLICY.md). Los resultados de verificación están en
[VERIFICATION.md](VERIFICATION.md); las pruebas locales no sustituyen la
comprobación del Apache/certificado real en bscdspace.
