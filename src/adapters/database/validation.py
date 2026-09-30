import re
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, x25519

ARGON2_PATTERN = re.compile(
    r'^\$argon2id\$v=(?:16|19)\$m=\d{1,10},t=\d{1,10},p=\d{1,3}(?:,keyid=[A-Za-z0-9+/]{0,11}(?:,data=[A-Za-z0-9+/]{0,43})?)?\$[A-Za-z0-9+/]{11,64}\$[A-Za-z0-9+/]{16,86}$'
)
BCRYPT_PATTERN = re.compile(r'^\$2[aby]?\$\d{1,2}\$[./A-Za-z0-9]{53}$')


def is_valid_ed_public_key(v: Any) -> bool:
    if v is None:
        return True
    if not isinstance(v, str):
        return False
    v = v.strip()
    if not v:
        return False
    try:
        key = serialization.load_pem_public_key(v.encode())
    except Exception:
        return False
    if not isinstance(key, (ec.EllipticCurvePublicKey, ed25519.Ed25519PublicKey)):
        return False
    return True


def is_valid_ecdh_public_key(v: Any) -> bool:
    if v is None:
        return True
    if not isinstance(v, str):
        return False
    v = v.strip()
    if not v:
        return False
    try:
        key = serialization.load_pem_public_key(v.encode())
    except Exception:
        return False
    if not isinstance(key, x25519.X25519PublicKey):
        return False
    return True


def is_valid_hashed_password(v: Any) -> bool:
    if v is None:
        return True
    if not isinstance(v, str):
        return False
    v = v.strip()
    if not v:
        return False
    if ARGON2_PATTERN.match(v) or BCRYPT_PATTERN.match(v):
        return True
    return False


def is_valid_file_name(v: Any) -> bool:
    return (
        isinstance(v, str)
        and bool(v)
        and "/" not in v
        and "\\" not in v
        and v not in {".", ".."}
        and "." not in v
    )


def is_valid_file_mime_type(v: Any) -> bool:
    return (
        isinstance(v, str)
        and bool(v)
        and v.startswith(".")
        and v != "."
        and "/" not in v
        and "\\" not in v
    )
