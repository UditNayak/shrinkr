import secrets
import string

ALPHABET = string.ascii_letters + string.digits
CODE_LENGTH = 7  # 62^7, about 3.5 trillion codes


def generate_code(length: int = CODE_LENGTH) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))
