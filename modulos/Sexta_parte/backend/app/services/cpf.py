import re


def only_digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def is_valid_cpf(value: str) -> bool:
    digits = only_digits(value)
    if len(digits) != 11 or digits == digits[0] * 11:
        return False
    for size in (9, 10):
        total = sum(int(d) * w for d, w in zip(digits[:size], range(size + 1, 1, -1)))
        check = (total * 10) % 11 % 10
        if check != int(digits[size]):
            return False
    return True


def format_cpf(value: str) -> str:
    d = only_digits(value)
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"


def mask_cpf(value: str) -> str:
    """Máscara para exibição/logs (LGPD): ***.456.789-**"""
    d = only_digits(value)
    if len(d) != 11:
        return "***"
    return f"***.{d[3:6]}.{d[6:9]}-**"
