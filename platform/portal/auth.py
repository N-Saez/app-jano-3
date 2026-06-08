import os

import firebase_admin
import firebase_admin.auth as fa
from fastapi import HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

# Inicializar Firebase Admin SDK una sola vez
_cred_path = os.path.join(os.path.dirname(__file__), "serviceAccountKey.json")
if not firebase_admin._apps:
    firebase_admin.initialize_app(firebase_admin.credentials.Certificate(_cred_path))

_SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production")
_signer = URLSafeTimedSerializer(_SECRET_KEY)
_COOKIE_NAME = "session"
_SESSION_MAX_AGE = 8 * 3600  # 8 horas


def verify_firebase_token(id_token: str) -> dict:
    """Verifica el ID token de Firebase y devuelve los claims del usuario."""
    try:
        decoded = fa.verify_id_token(id_token)
        return decoded
    except fa.InvalidIdTokenError:
        raise HTTPException(401, "Token de Firebase inválido.")
    except fa.ExpiredIdTokenError:
        raise HTTPException(401, "Token de Firebase expirado.")
    except Exception as e:
        raise HTTPException(401, f"Error de autenticación: {e}")


def create_session_cookie(email: str) -> str:
    return _signer.dumps({"email": email})


def get_session_user(request: Request) -> str | None:
    """Lee el email del usuario desde la cookie de sesión firmada. Devuelve None si no hay sesión válida."""
    token = request.cookies.get(_COOKIE_NAME)
    if not token:
        return None
    try:
        data = _signer.loads(token, max_age=_SESSION_MAX_AGE)
        return data.get("email")
    except (SignatureExpired, BadSignature):
        return None
