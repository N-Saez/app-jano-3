import asyncio
import io
import os
import re
import zipfile
from pathlib import Path

from db import App, get_next_port

APPS_BASE = Path("/opt/streamlit-platform/apps")
NGINX_LOCS = Path("/opt/streamlit-platform/nginx/locations.d")
SCRIPTS = Path("/opt/streamlit-platform/scripts")
PORT_START = 8501
PORT_END = 8600


async def deploy_zip(app_name: str, zip_bytes: bytes, owner: str, db) -> App:
    app_dir = APPS_BASE / app_name

    # 1. Extraer ZIP
    app_dir.mkdir(parents=True, exist_ok=True)
    _extract_zip(zip_bytes, app_dir)

    # 2. Detectar tipo de app
    req_txt = (app_dir / "requirements.txt").read_text(errors="ignore").lower()
    app_type = "dash" if "dash" in req_txt else "streamlit"

    # 3. Patch para Dash: subpath + PORT desde env
    if app_type == "dash":
        _patch_dash_app(app_dir / "app.py", app_name)

    # 4. Crear venv e instalar dependencias
    python = "python3.12" if app_type == "dash" else "python3.11"
    venv = app_dir / "venv"
    await _run(f"{python} -m venv {venv}")
    pip = venv / "bin" / "pip"
    await _run(f"{pip} install --upgrade pip -q")
    await _run(f"{pip} install -r {app_dir / 'requirements.txt'} -q")

    # 5. Asignar puerto y registrar en DB
    port = get_next_port(db, PORT_START, PORT_END)
    record = App(name=app_name, port=port, app_type=app_type, owner=owner, status="starting")
    db.add(record)
    db.commit()
    db.refresh(record)

    # 6. Escribir .env
    (app_dir / ".env").write_text(f"PORT={port}\nAPP_NAME={app_name}\nAPP_TYPE={app_type}\n")

    # 7. Escribir fragmento Nginx
    (NGINX_LOCS / f"{app_name}.conf").write_text(_nginx_fragment(app_name, port, app_type))

    # 8. Habilitar y arrancar servicio systemd
    service = f"{app_type}-app@{app_name}"
    await _run("sudo systemctl daemon-reload")
    await _run(f"sudo systemctl enable {service}")
    await _run(f"sudo systemctl start {service}")

    # 9. Recargar Nginx
    await _run(f"sudo {SCRIPTS / 'reload_nginx.sh'}")

    record.status = "running"
    db.commit()
    return record


def _extract_zip(zip_bytes: bytes, dest: Path):
    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    members = zf.namelist()

    # Detectar carpeta raíz opcional
    prefix = ""
    if members and "/" in members[0]:
        candidate = members[0].split("/")[0] + "/"
        if all(m.startswith(candidate) for m in members if m):
            prefix = candidate

    for member in members:
        rel = member[len(prefix):]
        if not rel:
            continue
        target = dest / rel
        if member.endswith("/"):
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zf.read(member))


def _patch_dash_app(app_py: Path, slug: str):
    """Inyecta requests_pathname_prefix y lectura de PORT desde env en app.py."""
    code = app_py.read_text()

    if "requests_pathname_prefix" not in code:
        code = re.sub(
            r"(app\s*=\s*(?:dash\.)?Dash\s*\(\s*__name__)",
            rf"\1, requests_pathname_prefix='/{slug}/'",
            code,
        )

    if "import os" not in code:
        code = "import os\n" + code

    # Normalizar arranque del servidor para leer PORT del .env
    code = re.sub(
        r"app\.run_server\s*\([^)]*\)",
        "app.run(host='127.0.0.1', port=int(os.environ.get('PORT', 8050)), debug=False)",
        code,
    )
    code = re.sub(
        r"app\.run\s*\(\s*debug\s*=\s*(True|False)\s*\)",
        "app.run(host='127.0.0.1', port=int(os.environ.get('PORT', 8050)), debug=False)",
        code,
    )

    app_py.write_text(code)


def _nginx_fragment(name: str, port: int, app_type: str) -> str:
    if app_type == "streamlit":
        return f"""\
location /{name}/ {{
    proxy_pass         http://127.0.0.1:{port}/;
    proxy_http_version 1.1;
    proxy_set_header   Upgrade    $http_upgrade;
    proxy_set_header   Connection "upgrade";
    proxy_set_header   Host       $host;
    proxy_set_header   X-Real-IP  $remote_addr;
    proxy_set_header   X-Forwarded-Prefix /{name};
    proxy_read_timeout 86400s;
    proxy_send_timeout 86400s;
}}
location /{name}/_stcore/ {{
    proxy_pass         http://127.0.0.1:{port}/_stcore/;
    proxy_http_version 1.1;
    proxy_set_header   Upgrade    $http_upgrade;
    proxy_set_header   Connection "upgrade";
    proxy_set_header   Host       $host;
    proxy_buffering    off;
    proxy_cache        off;
}}
"""
    else:
        return f"""\
location /{name}/ {{
    proxy_pass         http://127.0.0.1:{port}/;
    proxy_set_header   Host             $host;
    proxy_set_header   X-Real-IP        $remote_addr;
    proxy_set_header   X-Forwarded-For  $proxy_add_x_forwarded_for;
    proxy_set_header   X-Forwarded-Proto $scheme;
    proxy_read_timeout 60s;
}}
"""


async def _run(cmd: str):
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"Comando fallido: {cmd}\n{stderr.decode()}")
