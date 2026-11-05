"""OWASP minimum Argon2id profile; salts and progressive upgrades are library-managed."""

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError

hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1, type=Type.ID)
DUMMY_HASH = hasher.hash("Non-account constant used only to equalize password checks")


def hash_password(password):
    return hasher.hash(password)


def verify_password(encoded, password):
    try:
        return hasher.verify(encoded or DUMMY_HASH, password)
    except (VerificationError, InvalidHashError):
        return False
