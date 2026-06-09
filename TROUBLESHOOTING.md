# Troubleshooting Guide — Plataforma GeoTools

**Servidor:** `ubuntu@35.170.222.131` (EC2 t3.medium, Ubuntu)  
**Dominio:** `https://geotools.cl`  
**Acceso SSH:** `ssh -i apps-streamlit-keys.pem ubuntu@35.170.222.131`

---

## Índice

1. [Arquitectura general](#1-arquitectura-general)
2. [Mapa de apps: puertos y servicios](#2-mapa-de-apps-puertos-y-servicios)
3. [Archivos de configuración principales](#3-archivos-de-configuración-principales)
4. [Cómo ver los logs de cada app](#4-cómo-ver-los-logs-de-cada-app)
5. [Diagnóstico rápido — checklist](#5-diagnóstico-rápido--checklist)
6. [Problemas frecuentes y soluciones](#6-problemas-frecuentes-y-soluciones)
7. [Gestión de servicios (systemd)](#7-gestión-de-servicios-systemd)
8. [Nginx — verificar y recargar](#8-nginx--verificar-y-recargar)
9. [Base de datos SQLite](#9-base-de-datos-sqlite)
10. [Venvs compartidos](#10-venvs-compartidos)
11. [Seguridad](#11-seguridad)
12. [Espacio en disco y RAM](#12-espacio-en-disco-y-ram)

---

## 1. Arquitectura general

```
Internet (HTTPS :443)
        │
        ▼
   Nginx (SSL termination — Let's Encrypt)
        │
        ├── /                    → Portal FastAPI     (127.0.0.1:8000)
        ├── /sims/               → Streamlit sims     (127.0.0.1:8501)
        ├── /interpretacion-recursos-2d/ → Streamlit  (127.0.0.1:8502)
        ├── /mcs/                → Streamlit mcs      (127.0.0.1:8503)
        ├── /vol-var/            → Streamlit vol-var  (127.0.0.1:8504)
        ├── /dilucion/           → Streamlit dilucion (127.0.0.1:8505)
        ├── /pops/               → Streamlit pops     (127.0.0.1:8506)
        ├── /yacimientos-au/     → Dash               (127.0.0.1:8507)
        └── /yacimientos-cl/     → Dash               (127.0.0.1:8508)
```

**Todos los puertos de apps escuchan solo en `127.0.0.1`** — no son accesibles desde internet directamente. Solo nginx (80/443) está expuesto.

El portal (`/`) es una app FastAPI con autenticación Microsoft (Firebase). Solo usuarios con email `@geoinnova.cl` o `@pagina.cl` pueden desplegar o eliminar apps.

---

## 2. Mapa de apps: puertos y servicios

| Slug | URL | Puerto | Tipo | Servicio systemd |
|---|---|---|---|---|
| portal | `geotools.cl/` | 8000 | FastAPI | `streamlit-portal` |
| sims | `geotools.cl/sims/` | 8501 | Streamlit | `streamlit-app@sims` |
| interpretacion-recursos-2d | `geotools.cl/interpretacion-recursos-2d/` | 8502 | Streamlit | `streamlit-app@interpretacion-recursos-2d` |
| mcs | `geotools.cl/mcs/` | 8503 | Streamlit | `streamlit-app@mcs` |
| vol-var | `geotools.cl/vol-var/` | 8504 | Streamlit | `streamlit-app@vol-var` |
| dilucion | `geotools.cl/dilucion/` | 8505 | Streamlit | `streamlit-app@dilucion` |
| pops | `geotools.cl/pops/` | 8506 | Streamlit | `streamlit-app@pops` |
| yacimientos-au | `geotools.cl/yacimientos-au/` | 8507 | Dash | `dash-app@yacimientos-au` |
| yacimientos-cl | `geotools.cl/yacimientos-cl/` | 8508 | Dash | `dash-app@yacimientos-cl` |

> Los puertos 8509–8600 están reservados para apps desplegadas vía portal (ZIP upload).

---

## 3. Archivos de configuración principales

### Estructura de directorios en el servidor

```
/opt/streamlit-platform/
├── apps/                          # Una carpeta por app
│   ├── sims/
│   │   ├── app.py                 # Código fuente
│   │   ├── .env                   # PORT=8501, APP_NAME=sims, APP_TYPE=streamlit
│   │   └── venv/                  # Venv real (compartido por todas las apps Streamlit)
│   ├── yacimientos-au/
│   │   ├── app.py
│   │   ├── .env                   # PORT=8507, APP_NAME=yacimientos-au, APP_TYPE=dash
│   │   └── venv/                  # Venv real (compartido por todas las apps Dash)
│   ├── mcs/ → venv → symlink a sims/venv
│   ├── vol-var/ → venv → symlink a sims/venv
│   ├── dilucion/ → venv → symlink a sims/venv
│   ├── pops/ → venv → symlink a sims/venv
│   ├── interpretacion-recursos-2d/ → venv → symlink a sims/venv
│   └── yacimientos-cl/ → venv → symlink a yacimientos-au/venv
│
├── nginx/
│   ├── locations.d/               # Fragmento .conf por app
│   │   ├── sims.conf
│   │   ├── mcs.conf
│   │   ├── vol-var.conf
│   │   ├── dilucion.conf
│   │   ├── pops.conf
│   │   ├── interpretacion-recursos-2d.conf
│   │   ├── yacimientos-au.conf
│   │   └── yacimientos-cl.conf
│   └── (incluidos desde /etc/nginx/sites-available/geotools.cl.conf)
│
├── portal/
│   ├── main.py                    # FastAPI — rutas principales
│   ├── deployer.py                # Lógica de deploy ZIP
│   ├── auth.py                    # Verificación Firebase
│   ├── db.py                      # SQLAlchemy + SQLite
│   ├── security.py                # Validación ZIP
│   ├── .env                       # SECRET_KEY, FIREBASE_PROJECT_ID
│   ├── serviceAccountKey.json     # Credenciales Firebase (chmod 600)
│   ├── venv/                      # Venv exclusivo del portal
│   └── templates/index.html       # UI del portal
│
├── registry/
│   └── apps.db                    # SQLite — registro de apps desplegadas
│
└── scripts/
    ├── reload_nginx.sh            # Valida y recarga nginx (llamado por deployer)
    ├── delete_app.sh              # Elimina directorio de app (llamado por deployer)
    ├── migrate_existing.sh        # Migración inicial de apps
    └── setup_sudoers.sh           # Configura permisos sudo para usuario streamlit
```

### Nginx

| Archivo | Descripción |
|---|---|
| `/etc/nginx/sites-available/geotools.cl.conf` | Config principal: SSL, rate limiting, proxy al portal |
| `/opt/streamlit-platform/nginx/locations.d/*.conf` | Fragmento de cada app (incluido por el config principal) |
| `/etc/nginx/conf.d/rate_limit.conf` | Definición de zonas de rate limiting |

### systemd

| Archivo | Descripción |
|---|---|
| `/etc/systemd/system/streamlit-app@.service` | Template para apps Streamlit |
| `/etc/systemd/system/dash-app@.service` | Template para apps Dash |
| `/etc/systemd/system/streamlit-portal.service` | Portal FastAPI |

### SSL

| Archivo | Descripción |
|---|---|
| `/etc/letsencrypt/live/geotools.cl/fullchain.pem` | Certificado SSL |
| `/etc/letsencrypt/live/geotools.cl/privkey.pem` | Llave privada SSL |

> El certificado se renueva automáticamente con certbot. Expira cada 90 días.

---

## 4. Cómo ver los logs de cada app

### Portal FastAPI

```bash
journalctl -u streamlit-portal -f
journalctl -u streamlit-portal -n 50 --no-pager
```

### Apps Streamlit

```bash
# Ver logs en tiempo real
journalctl -u streamlit-app@sims -f
journalctl -u streamlit-app@mcs -f
journalctl -u streamlit-app@vol-var -f
journalctl -u streamlit-app@dilucion -f
journalctl -u streamlit-app@pops -f
journalctl -u streamlit-app@interpretacion-recursos-2d -f

# Ver últimas 50 líneas
journalctl -u streamlit-app@sims -n 50 --no-pager
```

### Apps Dash

```bash
journalctl -u dash-app@yacimientos-au -f
journalctl -u dash-app@yacimientos-cl -f
```

### Nginx

```bash
# Errores nginx
sudo tail -f /var/log/nginx/error.log

# Accesos nginx
sudo tail -f /var/log/nginx/access.log
```

### Ver logs de todas las apps a la vez

```bash
journalctl -f | grep -E 'streamlit|dash'
```

---

## 5. Diagnóstico rápido — checklist

Cuando una app no carga, seguir en orden:

### Paso 1 — Ver estado de todos los servicios

```bash
for s in streamlit-portal \
          streamlit-app@sims \
          streamlit-app@interpretacion-recursos-2d \
          streamlit-app@mcs \
          streamlit-app@vol-var \
          streamlit-app@dilucion \
          streamlit-app@pops \
          dash-app@yacimientos-au \
          dash-app@yacimientos-cl; do
  printf '%-45s %s\n' "$s" "$(systemctl is-active $s)"
done
```

### Paso 2 — Verificar que el puerto responde

```bash
# Reemplazar 8501 con el puerto de la app (ver tabla sección 2)
curl -s http://127.0.0.1:8501/sims/_stcore/health
# Debe responder: ok
```

### Paso 3 — Verificar que nginx enruta correctamente

```bash
curl -sk https://127.0.0.1/sims/ -o /dev/null -w '%{http_code}'
# Debe responder: 200
```

### Paso 4 — Ver logs del servicio caído

```bash
journalctl -u streamlit-app@sims -n 50 --no-pager
```

### Paso 5 — Verificar nginx

```bash
sudo nginx -t
sudo systemctl status nginx
```

---

## 6. Problemas frecuentes y soluciones

### App muestra "Connection error" o pantalla en blanco

**Causa:** El servicio de la app está caído.

```bash
# Ver estado
systemctl status streamlit-app@<nombre>

# Reiniciar
sudo systemctl restart streamlit-app@<nombre>

# Ver por qué cayó
journalctl -u streamlit-app@<nombre> -n 50 --no-pager
```

---

### App muestra `{"detail": "Not Found"}`

**Causa:** nginx está enrutando al portal FastAPI en vez de a la app. Puede ser que:
- El fragmento nginx de la app no existe o no fue recargado
- La app está en un puerto diferente al que nginx espera

```bash
# Verificar que el config existe
ls /opt/streamlit-platform/nginx/locations.d/

# Verificar el puerto en el config vs el .env
cat /opt/streamlit-platform/nginx/locations.d/<nombre>.conf
cat /opt/streamlit-platform/apps/<nombre>/.env

# Recargar nginx
sudo /opt/streamlit-platform/scripts/reload_nginx.sh
```

---

### App muestra `ModuleNotFoundError`

**Causa:** Falta un paquete Python en el venv compartido.

```bash
# Instalar el paquete faltante en el venv de Streamlit
sudo /opt/streamlit-platform/apps/sims/venv/bin/pip install <paquete>

# O en el venv de Dash
sudo /opt/streamlit-platform/apps/yacimientos-au/venv/bin/pip install <paquete>

# Reiniciar la app
sudo systemctl restart streamlit-app@<nombre>
```

---

### App queda cargando infinito (Dash)

**Causa:** Error en la inicialización de la app Dash (WebSocket no establecido).

```bash
journalctl -u dash-app@<nombre> -n 50 --no-pager
```

Verificar que `app.py` usa `url_base_pathname` (no `requests_pathname_prefix`):

```python
# Correcto (Dash 4.x)
app = Dash(__name__, url_base_pathname='/yacimientos-au/')

# Incorrecto (Dash 2/3 — no funciona en Dash 4)
app = Dash(__name__, requests_pathname_prefix='/yacimientos-au/')
```

---

### Portal muestra "Internal Server Error"

```bash
journalctl -u streamlit-portal -n 30 --no-pager
sudo systemctl restart streamlit-portal
```

Si el error es de Jinja2 (`unhashable type: 'dict'`):

```bash
sudo /opt/streamlit-platform/portal/venv/bin/pip install 'jinja2==3.1.4' 'fastapi==0.115.12' 'starlette==0.41.3'
sudo systemctl restart streamlit-portal
```

---

### nginx devuelve 502 Bad Gateway

**Causa:** La app no está corriendo en el puerto esperado.

```bash
# Ver qué puertos están activos
ss -tlnp | grep 127.0.0.1

# Comparar con lo esperado (sección 2)
# Si falta un puerto, reiniciar esa app:
sudo systemctl restart streamlit-app@<nombre>
```

---

### Certificado SSL expirado

```bash
sudo certbot renew --dry-run   # Simular renovación
sudo certbot renew             # Renovar
sudo systemctl reload nginx
```

---

### App fue matada por OOM (Out of Memory)

```bash
# Detectar en logs
journalctl -u streamlit-app@<nombre> | grep -i 'oom\|killed\|memory'

# Ver uso de RAM actual
free -h
ps aux --sort=-%mem | head -15
```

> Con t3.medium (4 GB RAM) esto es poco probable. Si ocurre, considerar reiniciar el proceso más pesado.

---

### Disco lleno

```bash
df -h /
# Si está > 90%:

# Ver qué ocupa más espacio
du -sh /opt/streamlit-platform/apps/*/  | sort -rh | head -10

# Las apps nuevas (ZIP upload) pueden tener venvs duplicados — verificar symlinks
ls -la /opt/streamlit-platform/apps/<nombre>/venv
# Debe apuntar a: /opt/streamlit-platform/apps/sims/venv (Streamlit)
#              o: /opt/streamlit-platform/apps/yacimientos-au/venv (Dash)

# Si no es symlink, convertirlo:
sudo rm -rf /opt/streamlit-platform/apps/<nombre>/venv
sudo ln -sfn /opt/streamlit-platform/apps/sims/venv /opt/streamlit-platform/apps/<nombre>/venv
```

---

## 7. Gestión de servicios (systemd)

```bash
# Ver estado
systemctl status streamlit-app@sims

# Iniciar / detener / reiniciar
sudo systemctl start   streamlit-app@sims
sudo systemctl stop    streamlit-app@sims
sudo systemctl restart streamlit-app@sims

# Habilitar/deshabilitar inicio automático
sudo systemctl enable  streamlit-app@sims
sudo systemctl disable streamlit-app@sims

# Recargar configuración de systemd (tras editar .service)
sudo systemctl daemon-reload

# Ver todos los servicios de la plataforma
systemctl list-units 'streamlit-*' 'dash-*'
```

---

## 8. Nginx — verificar y recargar

```bash
# Verificar sintaxis
sudo nginx -t

# Recargar sin downtime
sudo systemctl reload nginx

# Reinicio completo (evitar salvo necesario)
sudo systemctl restart nginx

# Ver estado
sudo systemctl status nginx

# Ver accesos en tiempo real
sudo tail -f /var/log/nginx/access.log

# Ver errores en tiempo real
sudo tail -f /var/log/nginx/error.log
```

---

## 9. Base de datos SQLite

El registro de apps desplegadas está en:

```
/opt/streamlit-platform/registry/apps.db
```

```bash
# Ver todas las apps registradas
sqlite3 /opt/streamlit-platform/registry/apps.db \
  'SELECT name, port, app_type, owner, status FROM apps ORDER BY port;'

# Marcar app como stopped manualmente
sqlite3 /opt/streamlit-platform/registry/apps.db \
  "UPDATE apps SET status='stopped' WHERE name='<nombre>';"

# Eliminar registro (usar con cuidado — el deployer también debe eliminar el servicio)
sqlite3 /opt/streamlit-platform/registry/apps.db \
  "DELETE FROM apps WHERE name='<nombre>';"
```

---

## 10. Venvs compartidos

Para ahorrar disco, **todas las apps comparten venv**:

| Apps | Venv compartido | Python |
|---|---|---|
| sims, mcs, vol-var, dilucion, pops, interpretacion-recursos-2d + ZIPs Streamlit | `/opt/streamlit-platform/apps/sims/venv` | 3.14.4 |
| yacimientos-au, yacimientos-cl + ZIPs Dash | `/opt/streamlit-platform/apps/yacimientos-au/venv` | 3.14.4 |
| portal (FastAPI) | `/opt/streamlit-platform/portal/venv` | 3.14.4 |

Las demás apps tienen `venv` como **symlink** al venv compartido:

```bash
# Verificar symlinks
ls -la /opt/streamlit-platform/apps/mcs/venv
# → lrwxrwxrwx ... venv -> /opt/streamlit-platform/apps/sims/venv

# Instalar paquete en venv Streamlit (afecta a todas las apps Streamlit)
sudo /opt/streamlit-platform/apps/sims/venv/bin/pip install <paquete>

# Instalar paquete en venv Dash
sudo /opt/streamlit-platform/apps/yacimientos-au/venv/bin/pip install <paquete>

# Ver paquetes instalados
/opt/streamlit-platform/apps/sims/venv/bin/pip list
```

> **Nota:** Instalar un paquete en el venv compartido afecta a **todas** las apps de ese tipo. Si una app necesita una versión específica incompatible con las demás, se debe crear un venv propio para esa app.

---

## 11. Seguridad

### Firewall (UFW)

```bash
sudo ufw status verbose
# Puertos abiertos: 22 (SSH), 80 (HTTP), 443 (HTTPS)
# Todo lo demás: bloqueado
```

### fail2ban

```bash
# Estado general
sudo fail2ban-client status

# Ver IPs baneadas en SSH
sudo fail2ban-client status sshd

# Desbanear una IP manualmente
sudo fail2ban-client set sshd unbanip <IP>
```

### AWS Security Group

El puerto 22 (SSH) está restringido a la IP de la oficina/casa. Si cambias de red y perdiste acceso SSH:
1. Ir a AWS Console → EC2 → Security Groups
2. Editar la regla del puerto 22
3. Agregar tu IP actual (`/32`)

### Renovación SSL

El certificado Let's Encrypt se renueva automáticamente cada 90 días vía certbot. Para verificar:

```bash
sudo certbot certificates
sudo systemctl status certbot.timer
```

---

## 12. Espacio en disco y RAM

### Ver estado actual

```bash
# Disco
df -h /

# RAM
free -h

# Procesos que más RAM usan
ps aux --sort=-%mem | head -15

# Espacio por app
du -sh /opt/streamlit-platform/apps/*/
```

### Valores de referencia (t3.medium)

| Recurso | Total | Uso típico | Alerta si supera |
|---|---|---|---|
| Disco | 6.7 GB | ~5 GB | 90% |
| RAM | 3.7 GB | ~1.5 GB | 85% |

### Si el disco supera 85%

```bash
# Eliminar apps de prueba que ya no se usen (desde el portal o manualmente)
# Verificar que no haya venvs duplicados (deben ser symlinks)
ls -la /opt/streamlit-platform/apps/*/venv | grep -v '\->'
# Si aparece una carpeta real (no symlink), convertirla a symlink
```
