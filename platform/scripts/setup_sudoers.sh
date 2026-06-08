#!/bin/bash
# Configura permisos sudo mínimos para el usuario 'streamlit'.
# Ejecutar como root una sola vez durante la instalación inicial.

cat > /etc/sudoers.d/streamlit-platform <<'EOF'
streamlit ALL=(ALL) NOPASSWD: /opt/streamlit-platform/scripts/reload_nginx.sh
streamlit ALL=(ALL) NOPASSWD: /bin/systemctl daemon-reload
streamlit ALL=(ALL) NOPASSWD: /bin/systemctl enable streamlit-app@*
streamlit ALL=(ALL) NOPASSWD: /bin/systemctl start streamlit-app@*
streamlit ALL=(ALL) NOPASSWD: /bin/systemctl stop streamlit-app@*
streamlit ALL=(ALL) NOPASSWD: /bin/systemctl restart streamlit-app@*
streamlit ALL=(ALL) NOPASSWD: /bin/systemctl enable dash-app@*
streamlit ALL=(ALL) NOPASSWD: /bin/systemctl start dash-app@*
streamlit ALL=(ALL) NOPASSWD: /bin/systemctl stop dash-app@*
streamlit ALL=(ALL) NOPASSWD: /bin/systemctl restart dash-app@*
EOF

chmod 440 /etc/sudoers.d/streamlit-platform
echo "Sudoers configurado."
