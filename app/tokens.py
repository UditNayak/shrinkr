"""Management tokens: a secret handed to a link's creator, proving ownership later.

Only a SHA-256 hash of each token is stored. A fast hash is right here (unlike passwords,
which need slow hashes such as bcrypt) because the token is 256 random bits: it cannot be
guessed, so there is nothing for an attacker to brute-force.
"""

import hashlib
import hmac
import secrets


def new_token() -> str:
    return secrets.token_urlsafe(32)  # 32 random bytes → 43 URL-safe characters


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()  # 64 hex characters


def token_matches(token: str, token_hash: str) -> bool:
    # compare_digest takes the same time whether the first or last character differs,
    # so response timing reveals nothing about the stored hash.
    return hmac.compare_digest(hash_token(token), token_hash)
