import io
import os
import re
import zipfile

from fastapi import HTTPException

MAX_ZIP_MB = 100
MAX_UNCOMPRESSED_MB = 500

REQUIRED_FILES = {"app.py", "requirements.txt"}

ALLOWED_EXTENSIONS = {
    ".py", ".txt", ".csv", ".json", ".toml",
    ".png", ".jpg", ".jpeg", ".svg", ".gif",
    ".md", ".yaml", ".yml", ".xlsx", ".xls",
    ".html", ".css", ".js",
}

DANGEROUS_PATTERNS = [
    r"\.\./",   # path traversal
    r"^/",      # rutas absolutas
    r"\.sh$",
    r"\.so$",
    r"\.exe$",
    r"\.dll$",
    r"\.bat$",
]

# Emails o dominios autorizados para subir apps.
# Ajustar según la organización.
AUTHORIZED_DOMAINS = {"pagina.cl", "geoinnova.cl"}
AUTHORIZED_EMAILS: set[str] = set()


def is_authorized_uploader(email: str | None) -> bool:
    if not email:
        return False
    if email in AUTHORIZED_EMAILS:
        return True
    domain = email.split("@")[-1].lower()
    return domain in AUTHORIZED_DOMAINS


SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{1,30}$")


def validate_slug(name: str):
    if not SLUG_RE.match(name):
        raise HTTPException(
            400,
            "Nombre inválido. Usa solo minúsculas, números y guiones (ej: mi-app).",
        )


def validate_zip(zip_bytes: bytes) -> list[str]:
    """Valida el ZIP y devuelve la lista de nombres de archivos normalizados (sin carpeta raíz)."""
    if len(zip_bytes) > MAX_ZIP_MB * 1024 * 1024:
        raise HTTPException(400, f"El ZIP supera {MAX_ZIP_MB} MB.")

    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile:
        raise HTTPException(400, "Archivo ZIP inválido o corrupto.")

    members = [m for m in zf.infolist() if not m.filename.endswith("/")]

    total_size = sum(m.file_size for m in zf.infolist())
    if total_size > MAX_UNCOMPRESSED_MB * 1024 * 1024:
        raise HTTPException(400, f"Contenido descomprimido supera {MAX_UNCOMPRESSED_MB} MB.")

    all_names = [m.filename for m in zf.infolist()]

    # Detectar carpeta raíz opcional
    prefix = ""
    if all_names and "/" in all_names[0]:
        candidate = all_names[0].split("/")[0] + "/"
        if all(n.startswith(candidate) for n in all_names if n):
            prefix = candidate

    normalized = [n[len(prefix):] for n in all_names if n[len(prefix):]]

    for name in all_names:
        for pattern in DANGEROUS_PATTERNS:
            if re.search(pattern, name):
                raise HTTPException(400, f"Ruta insegura en ZIP: {name}")
        ext = os.path.splitext(name)[1].lower()
        if ext and ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(400, f"Extensión no permitida: {ext} (archivo: {name})")

    for required in REQUIRED_FILES:
        if required not in normalized:
            raise HTTPException(400, f"Falta el archivo requerido: {required}")

    return normalized
