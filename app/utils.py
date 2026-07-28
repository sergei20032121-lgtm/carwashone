import random
import string


def generate_code(length: int = 8) -> str:
    """Короткий случайный код из букв и цифр (для реферальных ссылок, сертификатов)."""
    alphabet = string.ascii_uppercase + string.digits
    return "".join(random.choice(alphabet) for _ in range(length))
