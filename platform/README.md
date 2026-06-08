# Plataforma Multi-App: Guía de Instalación

## Estructura del repositorio

```
platform/
├── nginx/                  → configs Nginx
├── systemd/                → units systemd
├── scripts/                → scripts de migración y recarga
├── portal/                 → aplicación FastAPI (portal principal)
│   └── templates/          → HTML del portal
└── registry/               → (se crea en la VM, no se versiona)
```

---

## 1. Preparar la VM (Ubuntu)

```bash
sudo apt update && sudo apt install -y \
  nginx certbot python3-certbot-nginx \
  python3.11 python3.11-venv \
  python3.12 python3.12-venv \
  sqlite3

# Crear usuario de servicio sin privilegios
sudo useradd --system --shell /bin/bash --create-home streamlit

# Crear estructura de directorios
sudo mkdir -p /opt/streamlit-platform/{apps,nginx/locations.d,portal,scripts,registry}
sudo chown -R streamlit:streamlit /opt/streamlit-platform
```

---

## 2. Obtener certificado SSL

```bash
sudo certbot certonly --nginx -d pagina.cl -d www.pagina.cl
```

---

## 3. Desplegar Nginx

```bash
sudo cp platform/nginx/pagina.cl.conf /etc/nginx/sites-available/
sudo ln -s /etc/nginx/sites-available/pagina.cl.conf /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## 4. Instalar units systemd

```bash
sudo cp platform/systemd/streamlit-app@.service /etc/systemd/system/
sudo cp platform/systemd/dash-app@.service       /etc/systemd/system/
sudo cp platform/systemd/streamlit-portal.service /etc/systemd/system/
sudo systemctl daemon-reload
```

---

## 5. Configurar sudoers

```bash
sudo bash platform/scripts/setup_sudoers.sh
```

---

## 6. Instalar el portal FastAPI

```bash
# Copiar archivos del portal
sudo cp -r platform/portal/. /opt/streamlit-platform/portal/
sudo chown -R streamlit:streamlit /opt/streamlit-platform/portal

# Crear venv e instalar dependencias
sudo -u streamlit python3.11 -m venv /opt/streamlit-platform/portal/venv
sudo -u streamlit /opt/streamlit-platform/portal/venv/bin/pip install \
  -r /opt/streamlit-platform/portal/requirements.txt -q
```

### Configurar secretos del portal

Crear `/opt/streamlit-platform/portal/.env` (chmod 600):
```
SECRET_KEY=<cadena aleatoria larga — generar con: python3 -c "import secrets; print(secrets.token_hex(32))">
FIREBASE_PROJECT_ID=<id-del-proyecto-firebase>
```

Copiar el archivo de credenciales de Firebase:
```bash
sudo cp serviceAccountKey.json /opt/streamlit-platform/portal/
sudo chmod 600 /opt/streamlit-platform/portal/serviceAccountKey.json
sudo chown streamlit:streamlit /opt/streamlit-platform/portal/serviceAccountKey.json
```

### Configurar Firebase en el frontend

Editar `/opt/streamlit-platform/portal/templates/index.html` y reemplazar los valores `REEMPLAZAR` en el objeto `firebaseConfig` con los datos reales del proyecto Firebase (se obtienen en Firebase Console → Project settings → General → Your apps).

También reemplazar `REEMPLAZAR_TENANT_ID` con el Tenant ID de Azure AD.

### Iniciar el portal

```bash
sudo systemctl enable --now streamlit-portal
sudo systemctl status streamlit-portal
```

---

## 7. Inicializar la base de datos SQLite

```bash
sudo -u streamlit python3 -c "
import sys; sys.path.insert(0, '/opt/streamlit-platform/portal')
from db import Base, engine; Base.metadata.create_all(engine)
print('DB inicializada.')
"
```

---

## 8. Migrar las apps existentes

```bash
sudo cp platform/scripts/migrate_existing.sh /opt/streamlit-platform/scripts/
sudo cp platform/scripts/reload_nginx.sh     /opt/streamlit-platform/scripts/
sudo chmod +x /opt/streamlit-platform/scripts/*.sh

# Ejecutar como streamlit (tiene los sudoers configurados)
cd /opt/streamlit-platform/scripts

# Apps Streamlit (un archivo)
sudo -u streamlit bash migrate_existing.sh sims           /home/ubuntu/app.py            streamlit 8501
sudo -u streamlit bash migrate_existing.sh mcs            /home/ubuntu/app2.py           streamlit 8502
sudo -u streamlit bash migrate_existing.sh vol-var        /home/ubuntu/app3.py           streamlit 8503
sudo -u streamlit bash migrate_existing.sh dilucion       /home/ubuntu/app6.py           streamlit 8504
sudo -u streamlit bash migrate_existing.sh pops           /home/ubuntu/popssimulator.py  streamlit 8505

# Apps Streamlit (multi-archivo)
sudo -u streamlit bash migrate_existing.sh jano3          /home/ubuntu/app-jano-3/       streamlit 8506

# Apps Dash
sudo -u streamlit bash migrate_existing.sh yacimientos-au  /home/ubuntu/appYacimientos.py     dash 8507
sudo -u streamlit bash migrate_existing.sh yacimientos-cl  /home/ubuntu/appYacimientosChile.py dash 8508
```

> **Nota:** app4.py y app5.py son versiones antiguas de Dilución Geológica — no se migran.

---

## 9. Verificar

```bash
# Estado de todos los servicios
systemctl status streamlit-portal
systemctl status streamlit-app@sims
systemctl status streamlit-app@jano3
systemctl status dash-app@yacimientos-au

# Logs de una app
journalctl -u streamlit-app@sims -f

# Test HTTP
curl -I https://pagina.cl/
curl -I https://pagina.cl/sims/
curl -I https://pagina.cl/yacimientos-au/
```

---

## Agregar una nueva app manualmente

```bash
sudo -u streamlit bash /opt/streamlit-platform/scripts/migrate_existing.sh \
  nueva-app /ruta/a/nueva-app/ streamlit 8509
```

O bien, subirla vía el portal web en `https://pagina.cl/` (requiere login Microsoft).

---

## Archivos importantes post-instalación

| Ruta | Descripción |
|---|---|
| `/opt/streamlit-platform/portal/.env` | Secretos del portal |
| `/opt/streamlit-platform/portal/serviceAccountKey.json` | Credenciales Firebase |
| `/opt/streamlit-platform/nginx/locations.d/` | Fragmentos Nginx por app |
| `/opt/streamlit-platform/registry/apps.db` | Registro SQLite |
| `/opt/streamlit-platform/apps/<nombre>/.env` | Puerto y tipo de cada app |
