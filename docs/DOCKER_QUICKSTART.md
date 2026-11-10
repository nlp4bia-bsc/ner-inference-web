# Docker en temu.bsc.es:18443

La configuración principal reutiliza el certificado SSL del servidor, usa **CPU** y publica la plataforma en
**https://temu.bsc.es:18443**. El puerto es configurable. Se levantan tres
servicios: web, worker y proxy HTTPS (Caddy fijado por digest). El perfil NVIDIA queda preparado para
cuando la máquina tenga GPU. No hace falta activar Conda ni lanzar Python en el
host: Docker instala las dependencias y arranca los procesos.

## 1. Repositorio y configuración

Con Docker Engine y Compose **v2.24.4 o posterior** instalados, en la máquina final:

```bash
git clone --branch work https://github.com/nlp4bia-bsc/ner-inference-web.git
cd ner-inference-web
# Si ya tienes el checkout: git pull --ff-only.
mkdir -p gazetteers certificates
chmod 700 gazetteers certificates
ss -ltn '( sport = :18443 )'
```

El último comando comprueba el puerto elegido. Si está ocupado,
cambia `PUBLIC_HTTPS_PORT` en `.env`. El DNS de `temu.bsc.es` debe apuntar a esta
máquina y el puerto TCP elegido debe llegar a ella.

Crea una `.env` privada con estas claves, conservando otras que necesites si ya
existe:

```dotenv
COMPOSE_FILE=docker-compose.yml:docker-compose.public.yml
PUBLIC_DOMAIN=temu.bsc.es
PUBLIC_HTTPS_PORT=18443
APP_PREFIX=
INSTALL_NLP=true
NLP_PROFILE=cpu
MODEL_LOADING_MODE=on_demand
HF_HUB_OFFLINE=0
TRANSFORMERS_OFFLINE=0
REQUIRE_EMAIL_VERIFICATION=false
MAIL_BACKEND=none
```

`COMPOSE_FILE` hace que los comandos Compose carguen siempre el perfil público,
sin tener que repetir opciones `-f`. La superposición pública fija `APP_ENV=production`, `COOKIE_SECURE=true` y calcula
`PUBLIC_BASE_URL` con ese dominio, puerto y prefijo para **ambos procesos**. No
hacen falta los antiguos `export`, y una URL de localhost heredada en `.env` no
sustituye el origen público en este perfil. Las rutas internas son `/data` y
`/gazetteers`. `.env`, `gazetteers/` y `certificates/` están excluidos de Git y de
las imágenes. `HF_TOKEN`, si una descarga lo requiere, puede añadirse a `.env`;
se proporciona solo al worker.

## 2. Certificado HTTPS

Reutiliza el certificado SSL que ya utiliza la máquina, siempre que cubra
`temu.bsc.es`. Los puertos 80 y 443 del host quedan para sus servicios actuales.
Para identificar el servicio y las rutas, en la máquina final:

```bash
sudo ss -ltnp '( sport = :80 or sport = :443 )'
# Si es Nginx:
sudo nginx -T 2>/dev/null | grep -E 'server_name|ssl_certificate(_key)?'
# Si es Apache:
sudo grep -R -E 'ServerName|SSLCertificate(File|KeyFile|ChainFile)' /etc/apache2/sites-enabled/
```

Selecciona el certificado del dominio y su clave. Los comandos muestran rutas,
no el contenido de las claves. Si se gestiona con Certbot, `sudo certbot
certificates` también muestra las rutas. Copia los archivos a los nombres que
espera Docker, sustituyendo las dos rutas de ejemplo:

```bash
sudo install -m 600 -o "$(id -u)" -g "$(id -g)" /RUTA/fullchain.pem certificates/fullchain.pem
sudo install -m 600 -o "$(id -u)" -g "$(id -g)" /RUTA/privkey.pem certificates/privkey.pem
openssl x509 -in certificates/fullchain.pem -noout -checkhost temu.bsc.es
```

Deben quedar aquí:

```text
certificates/fullchain.pem
certificates/privkey.pem
```

`fullchain.pem` contiene el certificado del servidor y sus intermediarios.
Si el servidor los configura en archivos separados, concatena primero el
certificado y después la cadena para formar ese archivo. Un
certificado institucional válido o un wildcard que cubra el dominio sirve. Los
servicios y Caddy se configuran para HTTPS sin abrir 80 ni 443 en el host: el
puerto externo es 18443. El certificado debe estar emitido de antemano; este
perfil no intenta obtenerlo automáticamente mediante desafíos ACME en esos
puertos. No pegues claves en el chat ni las añadas al repositorio.

```bash
chmod 600 certificates/privkey.pem
git check-ignore certificates/privkey.pem gazetteers/dt4h_gazs.zip
```

El proxy Docker se conecta directamente a `web` en la red privada, también si
el host usa un proxy HTTP de salida.

## 3. Imágenes y diccionarios privados

Construye primero las imágenes CPU:

```bash
docker compose config --quiet
docker compose build web worker
```

Copia por tu canal privado `dt4h_gazs.zip` a `gazetteers/dt4h_gazs.zip`.
Si ya tienes `gazetteers/` importado, copia el directorio entero, incluidos
`manifest.json` y `.prepared/`, y omite la siguiente importación.

Solo si has copiado el ZIP sin importar:

```bash
docker compose run --rm --no-deps \
  --user "$(id -u):$(id -g)" \
  -v "$PWD/gazetteers:/gazetteers:rw" \
  worker python -m scripts.import_gazetteers \
  /gazetteers/dt4h_gazs.zip --language-source path
```

El importador se ejecuta con tu UID para crear los archivos con permisos privados.
No descarga un Transformer ni genera un índice del bi-encoder. El inventario
confirmado debe producir **28 recursos** en `cs, en, es, it, nl, ro, sv`.

Los servicios corren como UID **10001**. Después de importar o copiar los Parquet,
concede lectura a ese UID, manteniendo la privacidad para los demás usuarios:

```bash
# En Ubuntu/Debian, si no está disponible setfacl:
sudo apt-get install acl
setfacl -Rm u:10001:rX gazetteers
```

Repite la ACL tras una nueva importación, porque el importador aplica permisos
privados. En ejecución normal `gazetteers/` se monta **solo para lectura**. Las
terminologías no entran en las imágenes.

## 4. Arranque

Si conservas cuentas/documentos de Conda, realiza primero la migración del último
apartado. Después, con los certificados preparados:

```bash
docker compose run --rm --no-deps --entrypoint caddy proxy validate --config /etc/caddy/Caddyfile
docker compose up -d
docker compose ps
docker compose logs --tail=100 web worker proxy
```

Abre **https://temu.bsc.es:18443**. El registro solicita acceso: el administrador
debe aprobar cada cuenta nueva en `/admin`. No requiere correo de verificación.
El primer job descarga los modelos seleccionados; luego reutiliza la caché.
Fuzzy match no construye un índice neuronal.

Comprueba el origen configurado, los recursos y la conexión con el worker:

```bash
docker compose exec worker \
  python -m scripts.check_config --expect-origin https://temu.bsc.es:18443
docker compose logs -f worker
```

El worker debe registrar `worker_ready`. La aplicación publica resultados
progresivamente por modelo/categoría. Solo se publica el puerto **18443**: el
8000 del backend queda dentro de la red Docker, así que no colisiona con un
servicio que ya lo esté usando en el host. El proxy fija las cabeceras de cliente
y esquema; el backend las acepta únicamente desde su red privada sin puerto
público. Mantén esa separación al modificar el despliegue.

Si el administrador ya existe, conserva el volumen privado y su cuenta; **no lo
crees de nuevo**. Tras actualizar, accede a `/admin` para aprobar solicitudes,
modificar cuotas y eliminar cuentas, o a `/admin/projects` para todos los proyectos.
La migración es automática y conserva sus credenciales y MFA. Véase
[administración](ADMINISTRATION.md).

Solo para una instalación nueva, crea el primer administrador con un correo nuevo:

```bash
docker compose exec web \
  python -m scripts.create_admin
```

Introduce los datos interactivamente; después inicia sesión y configura MFA para
acceder a la administración.

## GPU NVIDIA en el futuro

Instala el driver compatible y
[NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
en el host. El perfil fijado en `requirements-nlp.lock` usa CUDA 13.2; el driver
debe ser compatible. Comprueba `nvidia-smi` y sustituye en `.env` la línea `COMPOSE_FILE` por:

```dotenv
COMPOSE_FILE=docker-compose.yml:docker-compose.public.yml:docker-compose.gpu.yml
```

Después reconstruye y arranca:

```bash
docker compose up -d --build
docker compose exec worker \
  python -c 'import torch; print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0))'
```

El perfil instala las dependencias GPU, pide una GPU y establece `DEVICE=cuda`.
Web, datos y proxy siguen igual. `COMPOSE_FILE` mantiene el perfil GPU activo también en la importación y los
comandos posteriores. El
índice FAISS permanece en CPU FlatIP. No se ha verificado aquí un arranque en
hardware NVIDIA.

## Persistencia y actualización

`ner-data` conserva cuentas, claves, documentos y cachés de Hugging Face y
normalización. El nombre físico lleva el prefijo del proyecto Compose: mantén el
mismo nombre de proyecto para reutilizarlo. `gazetteers/` y `certificates/` quedan
en el host. Para parar manteniendo los datos:

```bash
docker compose down
```

No añadas `-v` si quieres conservar los volúmenes. Para actualizar, deja terminar
el job activo o páralo de forma controlada y ejecuta:

```bash
git pull --ff-only
docker compose up -d --build
```

Si se renueva el certificado original del host, repite la copia de ambos archivos
y recarga el proxy:

```bash
docker compose exec proxy \
  caddy reload --config /etc/caddy/Caddyfile
```

El ejemplo limita el worker a 8 GiB de RAM y el job a 7200 segundos. La RAM se
ajusta con una superposición Compose y el límite de tiempo con
`JOB_TIMEOUT_SECONDS` en `.env`. Un solo worker consume la cola; el bloqueo evita
dos supervisores simultáneos.

### Conservar una instalación Conda

El volumen Docker nuevo no incorpora automáticamente `storage/` de Conda. Para
conservar cuentas y documentos, transfiere **todo** ese directorio, incluidas las
claves, con ambos procesos nativos parados. Con Docker parado y el volumen destino
nuevo, antes del primer arranque:

```bash
docker compose down
docker compose run --rm --no-deps --user 0 \
  -v "$PWD/storage:/native-storage:ro" --entrypoint sh web \
  -c 'cp -a /native-storage/. /data/ && chown -R 10001:10001 /data'
```

Después arranca como en el paso 4. Usa una copia coherente y un volumen destino
vacío; copiar solo SQLite perdería claves necesarias para algunas funciones. Los
plazos de retención iniciados se conservan.
