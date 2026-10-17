"""Long decimal integers (SPEC §3.1): one conversion each way, host-independent.

CPython 3.11+ refuses `int(s)` and `str(n)` beyond 4,300 decimal digits by
default (`sys.set_int_max_str_digits`), and that limit is the *host's*,
settable per process and absent on 3.10. §3.1 is explicit that **the host's
own limits must not change meaning**: a decimal within yapyon's ceiling loads
on every host, in every environment. So yapyon never hands a long decimal to
`int()` or `str()` whole. It converts in chunks that stay under any limit the
host could plausibly hold, and keeps its own two numbers instead — a warn
threshold the specification fixes, and a refusal ceiling this implementation
chooses, exactly the shape of §5.3's expansion limits.

Powers-of-two radixes (`0b 0q 0o 0x 0z`) convert in linear time and are not
limited, by Python or by §3.1.
"""

from __future__ import annotations

#: §3.1's warn threshold: more decimal digits than this is shiran.
WARN_DIGITS = 4300

#: This implementation's refusal ceiling — more is akan. `max_digits` on the
#: loading functions moves it; §3.1 requires it to be at or above the warn
#: threshold and documented, and this is the documentation.
REFUSE_DIGITS = 4 * WARN_DIGITS

_CHUNK = 1000          # digits per host conversion: far below any host limit


def int_from_decimal(digits: str) -> int:
    """`digits` — ASCII 0-9 only, no sign or separators — as an int."""
    if len(digits) <= _CHUNK:
        return int(digits)
    half = len(digits) // 2
    high, low = digits[:-half], digits[-half:]
    return int_from_decimal(high) * 10 ** half + int_from_decimal(low)


def decimal_text(n: int) -> str:
    """`n` in decimal, exactly as `str(n)` writes it where the host allows.

    `bool` is an `int` to Python but never reaches here as one: callers
    test for it first, as every writer in this package does."""
    if n < 0:
        return "-" + decimal_text(-n)
    if n < 10 ** _CHUNK:
        return str(n)
    half = max(_CHUNK, (n.bit_length() * 30103 // 100000) // 2)
    high, low = divmod(n, 10 ** half)
    return decimal_text(high) + decimal_text(low).rjust(half, "0")


def decimal_digits(n: int) -> int:
    """How many decimal digits `abs(n)` has, without writing it out."""
    n = abs(n)
    if n < 10 ** _CHUNK:
        return len(str(n))
    estimate = n.bit_length() * 30103 // 100000
    return estimate + (n >= 10 ** estimate)
