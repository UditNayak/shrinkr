import secrets
import string

ALPHABET = string.ascii_letters + string.digits  # 62 characters
CODE_LENGTH = 7  # 62^7 ≈ 3.5 trillion possible codes


def generate_code(length: int = CODE_LENGTH) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))
