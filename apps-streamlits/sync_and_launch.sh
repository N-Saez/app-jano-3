#!/bin/bash

# === CONFIGURACIÓN ===
REMOTE="storage-gnv2"
REMOTE_FOLDER="EC2-script"
LOCAL_FOLDER="/home/ubuntu/streamlit_apps"
PORT_FILE="/home/ubuntu/used_ports.txt"
LOG_FILE="/home/ubuntu/deploy_log.txt"

# === ASEGURAR RUTAS Y ARCHIVOS NECESARIOS ===
mkdir -p "$LOCAL_FOLDER"
echo "📁 Verificando existencia de archivos..."

[ ! -f "$PORT_FILE" ] && echo "🆕 Creando $PORT_FILE" && touch "$PORT_FILE"
[ ! -f "$LOG_FILE" ] && echo "🆕 Creando $LOG_FILE" && touch "$LOG_FILE"

echo "✅ Archivos de control verificados"

# Asegurar que .local/bin esté en PATH (para streamlit global si fuera necesario)
export PATH="$PATH:/home/ubuntu/.local/bin"

# === 1. Sincronizar contenido desde Drive (sin tocar venv) ===
rclone sync "$REMOTE:$REMOTE_FOLDER" "$LOCAL_FOLDER" --exclude "*/venv/**"

# === 2. Buscar y lanzar apps ===
for folder in "$LOCAL_FOLDER"/*/; do
  folder="${folder%/}"  # Elimina barra final si existe
  app_name=$(basename "$folder")
  app_file="$folder/app.py"
  venv_path="$folder/venv"
  log_file="/home/ubuntu/streamlit_logs/${app_name}.log"

  # Saltar si no hay app.py
  [[ ! -f "$app_file" ]] && continue

  # Saltar si ya hay un proceso corriendo para esta app
  if pgrep -f "streamlit run .*${app_name}" > /dev/null; then
    continue
  fi

  # Crear entorno virtual si no existe
  if [[ ! -f "$venv_path/bin/activate" ]]; then
    echo "🔧 Creando entorno virtual con virtualenv para $app_name"
    virtualenv "$venv_path"
  fi

  # Activar entorno virtual
  source "$venv_path/bin/activate"

  # Instalar dependencias si hay requirements.txt
  if [[ -f "$folder/requirements.txt" ]]; then
    echo "📦 Instalando dependencias para $app_name"
    pip install --upgrade pip >> "$log_file" 2>&1
    pip install -r "$folder/requirements.txt" >> "$log_file" 2>&1
  fi

  # Buscar un puerto libre entre 8505 y 8600
  for port in $(seq 8505 8600); do
    echo "🧐 Probando puerto $port"
    if [ -f "$PORT_FILE" ] && ! grep -q "$port" "$PORT_FILE" && ! lsof -i ":$port" > /dev/null; then
      echo "✅ Puerto libre encontrado: $port"
      echo "$port" >> "$PORT_FILE"
      echo "🚀 Lanzando $app_name en puerto $port"
      nohup "$venv_path/bin/streamlit" run "$app_file" --server.port="$port" > "$log_file" 2>&1 &
      echo "$(date) - Lanzada '$app_name' en puerto $port" >> "$LOG_FILE"
      break
    fi
  done

  deactivate
done

