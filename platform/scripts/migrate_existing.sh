#!/bin/bash
# Migra una app existente al nuevo esquema de la plataforma.
#
# Uso:
#   ./migrate_existing.sh <slug> <origen> <tipo> <puerto>
#
# Parámetros:
#   slug    Nombre-slug de la app (ej: sims, dilucion, yacimientos-au)
#   origen  Ruta al archivo .py o directorio de la app
#   tipo    "streamlit" o "dash"
#   puerto  Puerto interno asignado (ej: 8501)
#
# Ejemplos:
#   ./migrate_existing.sh sims /home/ubuntu/app.py streamlit 8501
#   ./migrate_existing.sh yacimientos-au /home/ubuntu/appYacimientos.py dash 8507
#   ./migrate_existing.sh jano3 /home/ubuntu/app-jano-3/ streamlit 8504

set -e

SLUG="$1"
ORIGEN="$2"
TIPO="$3"
PUERTO="$4"

APPS_BASE="/opt/streamlit-platform/apps"
NGINX_LOCS="/opt/streamlit-platform/nginx/locations.d"
REGISTRY="/opt/streamlit-platform/registry/apps.db"
DEST="$APPS_BASE/$SLUG"

# Validaciones básicas
if [[ -z "$SLUG" || -z "$ORIGEN" || -z "$TIPO" || -z "$PUERTO" ]]; then
    echo "Uso: $0 <slug> <origen> <tipo> <puerto>"
    exit 1
fi
if [[ "$TIPO" != "streamlit" && "$TIPO" != "dash" ]]; then
    echo "Tipo debe ser 'streamlit' o 'dash'"
    exit 1
fi

echo "=== Migrando '$SLUG' (tipo: $TIPO, puerto: $PUERTO) ==="

# 1. Crear directorio destino
mkdir -p "$DEST"

# 2. Copiar archivos
if [[ -d "$ORIGEN" ]]; then
    echo "  Copiando directorio $ORIGEN → $DEST/"
    cp -r "$ORIGEN"/. "$DEST/"
else
    echo "  Copiando archivo $ORIGEN → $DEST/app.py"
    cp "$ORIGEN" "$DEST/app.py"
fi

# 3. Patch para apps Dash: inyectar requests_pathname_prefix y lectura de PORT
if [[ "$TIPO" == "dash" ]]; then
    echo "  Aplicando patch de subpath para Dash..."
    PATCH_LINE="import os; _slug='$SLUG'"
    # Insertar al inicio del app.py si no está ya parcheado
    if ! grep -q "requests_pathname_prefix" "$DEST/app.py"; then
        # Reemplazar "app = Dash(__name__)" por la versión con subpath
        sed -i "s|app = Dash(__name__)|app = Dash(__name__, requests_pathname_prefix='/$SLUG/')|g" "$DEST/app.py"
        # Reemplazar "app = dash.Dash(__name__)" también
        sed -i "s|app = dash.Dash(__name__)|app = dash.Dash(__name__, requests_pathname_prefix='/$SLUG/')|g" "$DEST/app.py"
        # Si el __main__ usa port hardcodeado, reemplazarlo por PORT del .env
        sed -i "s|app.run_server(debug=False)|app.run(host='127.0.0.1', port=int(os.environ.get('PORT', 8050)), debug=False)|g" "$DEST/app.py"
        sed -i "s|app.run_server(debug=True)|app.run(host='127.0.0.1', port=int(os.environ.get('PORT', 8050)), debug=False)|g" "$DEST/app.py"
        # Asegurar que os esté importado
        if ! grep -q "^import os" "$DEST/app.py"; then
            sed -i "1s|^|import os\n|" "$DEST/app.py"
        fi
    fi
fi

# 4. Seleccionar versión de Python
if [[ "$TIPO" == "dash" ]]; then
    PYTHON="python3.12"
else
    PYTHON="python3.11"
fi

# 5. Crear virtualenv e instalar dependencias
echo "  Creando venv con $PYTHON..."
$PYTHON -m venv "$DEST/venv"
"$DEST/venv/bin/pip" install --upgrade pip -q

if [[ -f "$DEST/requirements.txt" ]]; then
    echo "  Instalando requirements.txt..."
    "$DEST/venv/bin/pip" install -r "$DEST/requirements.txt" -q
else
    echo "  ⚠️  No se encontró requirements.txt — instalando solo streamlit/dash base"
    if [[ "$TIPO" == "streamlit" ]]; then
        "$DEST/venv/bin/pip" install streamlit -q
    else
        "$DEST/venv/bin/pip" install dash -q
    fi
fi

# 6. Crear .env
cat > "$DEST/.env" <<EOF
PORT=$PUERTO
APP_NAME=$SLUG
APP_TYPE=$TIPO
EOF

# 7. Escribir fragmento Nginx
if [[ "$TIPO" == "streamlit" ]]; then
    cat > "$NGINX_LOCS/$SLUG.conf" <<EOF
location /$SLUG/ {
    proxy_pass         http://127.0.0.1:$PUERTO/;
    proxy_http_version 1.1;
    proxy_set_header   Upgrade    \$http_upgrade;
    proxy_set_header   Connection "upgrade";
    proxy_set_header   Host       \$host;
    proxy_set_header   X-Real-IP  \$remote_addr;
    proxy_set_header   X-Forwarded-Prefix /$SLUG;
    proxy_read_timeout 86400s;
    proxy_send_timeout 86400s;
}
location /$SLUG/_stcore/ {
    proxy_pass         http://127.0.0.1:$PUERTO/_stcore/;
    proxy_http_version 1.1;
    proxy_set_header   Upgrade    \$http_upgrade;
    proxy_set_header   Connection "upgrade";
    proxy_set_header   Host       \$host;
    proxy_buffering    off;
    proxy_cache        off;
}
EOF
else
    cat > "$NGINX_LOCS/$SLUG.conf" <<EOF
location /$SLUG/ {
    proxy_pass         http://127.0.0.1:$PUERTO/;
    proxy_set_header   Host             \$host;
    proxy_set_header   X-Real-IP        \$remote_addr;
    proxy_set_header   X-Forwarded-For  \$proxy_add_x_forwarded_for;
    proxy_set_header   X-Forwarded-Proto \$scheme;
    proxy_read_timeout 60s;
}
EOF
fi

# 8. Registrar en SQLite
sqlite3 "$REGISTRY" <<SQL
INSERT OR REPLACE INTO apps (name, port, app_type, owner, status, created, updated)
VALUES ('$SLUG', $PUERTO, '$TIPO', 'admin', 'starting', datetime('now'), datetime('now'));
SQL

# 9. Habilitar y arrancar servicio systemd
SERVICE="${TIPO}-app@${SLUG}"
echo "  Habilitando servicio $SERVICE..."
systemctl daemon-reload
systemctl enable "$SERVICE"
systemctl start  "$SERVICE"

# 10. Recargar Nginx
echo "  Recargando Nginx..."
/opt/streamlit-platform/scripts/reload_nginx.sh

# 11. Marcar como running en DB
sqlite3 "$REGISTRY" \
    "UPDATE apps SET status='running', updated=datetime('now') WHERE name='$SLUG';"

echo "=== ✅ $SLUG disponible en https://pagina.cl/$SLUG/ ==="
