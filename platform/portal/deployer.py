import asyncio
import io
import os
import re
import zipfile
from pathlib import Path

import urllib.request

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

    # 4. Reutilizar venv compartido e instalar dependencias faltantes
    venv = app_dir / "venv"
    shared = APPS_BASE / ("sims" if app_type == "streamlit" else "yacimientos-au") / "venv"
    await _run(f"ln -sfn {shared} {venv}")
    pip = shared / "bin" / "pip"
    await _run(f"sudo {pip} install -r {app_dir / 'requirements.txt'} -q")

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

    # 9. Esperar que la app esté realmente arriba (health check)
    await _wait_for_app(port, app_name, app_type)

    # 10. Recargar Nginx una vez que la app ya responde
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
    """Inyecta url_base_pathname y lectura de PORT desde env en app.py."""
    code = app_py.read_text()

    # url_base_pathname works in Dash 4.x; requests_pathname_prefix is Dash 2/3
    if "url_base_pathname" not in code and "requests_pathname_prefix" not in code:
        code = re.sub(
            r"(app\s*=\s*(?:dash\.)?Dash\s*\(\s*__name__)",
            rf"\1, url_base_pathname='/{slug}/'",
            code,
        )
    elif "requests_pathname_prefix" in code:
        code = code.replace("requests_pathname_prefix=", "url_base_pathname=")

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
    proxy_pass         http://127.0.0.1:{port};
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
    proxy_pass         http://127.0.0.1:{port};
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
    proxy_pass         http://127.0.0.1:{port};
    proxy_http_version 1.1;
    proxy_set_header   Upgrade    $http_upgrade;
    proxy_set_header   Connection "upgrade";
    proxy_set_header   Host             $host;
    proxy_set_header   X-Real-IP        $remote_addr;
    proxy_set_header   X-Forwarded-For  $proxy_add_x_forwarded_for;
    proxy_set_header   X-Forwarded-Proto $scheme;
    proxy_read_timeout 86400s;
    proxy_send_timeout 86400s;
}}
"""


async def delete_app(app_name: str, app_type: str, db) -> None:
    from db import App
    service = f"{app_type}-app@{app_name}"
    for cmd in [
        f"sudo systemctl stop {service}",
        f"sudo systemctl disable {service}",
    ]:
        try:
            await _run(cmd)
        except RuntimeError:
            pass

    nginx_conf = NGINX_LOCS / f"{app_name}.conf"
    if nginx_conf.exists():
        nginx_conf.unlink()

    app_dir = APPS_BASE / app_name
    if app_dir.exists():
        await _run(f"sudo {SCRIPTS / 'delete_app.sh'} {app_name}")

    await _run(f"sudo {SCRIPTS / 'reload_nginx.sh'}")

    record = db.query(App).filter(App.name == app_name).first()
    if record:
        db.delete(record)
        db.commit()


async def _wait_for_app(port: int, app_name: str, app_type: str, timeout: int = 90):
    """Espera que la app esté respondiendo y estable (no sólo que arrancó)."""
    if app_type == "streamlit":
        url = f"http://127.0.0.1:{port}/{app_name}/_stcore/health"
    else:
        url = f"http://127.0.0.1:{port}/{app_name}/"

    # Fase 1: esperar primer OK
    for _ in range(timeout):
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status < 500:
                    break
        except Exception:
            pass
        await asyncio.sleep(1)
    else:
        raise RuntimeError(f"La app '{app_name}' no respondió en {timeout}s. Revisa los logs: journalctl -u {app_type}-app@{app_name} -n 50")

    # Fase 2: verificar que sigue viva 5s después (detecta crashes al cargar módulos)
    await asyncio.sleep(5)
    service = f"{app_type}-app@{app_name}"
    proc = await asyncio.create_subprocess_shell(
        f"systemctl is-active {service}",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    out, _ = await proc.communicate()
    if out.decode().strip() != "active":
        # Capturar últimas líneas del log para el mensaje de error
        log_proc = await asyncio.create_subprocess_shell(
            f"journalctl -u {service} -n 20 --no-pager",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        log_out, _ = await log_proc.communicate()
        raise RuntimeError(
            f"La app '{app_name}' cayó tras arrancar. Últimos logs:\n{log_out.decode()[-1500:]}"
        )


async def _run(cmd: str):
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"Comando fallido: {cmd}\n{stderr.decode()}")
