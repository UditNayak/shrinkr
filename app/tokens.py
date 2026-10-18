import hashlib
import hmac
import secrets


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    # The token is random, so a fast hash is enough (no need for bcrypt).
    return hashlib.sha256(token.encode()).hexdigest()


def token_matches(token: str, token_hash: str) -> bool:
    return hmac.compare_digest(hash_token(token), token_hash)
