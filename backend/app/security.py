"""Utilidades de credenciales de sala.

No hay cuentas de usuario: la contraseña sólo protege la entrada a una sala
privada y el token identifica al jugador para poder reconectar.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

# La contraseña sólo protege la entrada a una sala que se comparte de viva
# voz entre amigos; 40k iteraciones bastan de sobra y dejan el coste (~20 ms)
# lo bastante bajo como para hashear en el propio bucle de eventos.
_ITERATIONS = 40_000
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin I/O/0/1 para dictar el código en voz


def new_token() -> str:
    return secrets.token_urlsafe(24)


def new_room_code() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(6))


def hash_password(password: str) -> tuple[str, str]:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _ITERATIONS)
    return salt, digest.hex()


def verify_password(password: str, salt: str, expected: str) -> bool:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _ITERATIONS)
    return hmac.compare_digest(digest.hex(), expected)
