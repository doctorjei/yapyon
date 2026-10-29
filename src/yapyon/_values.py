"""Primitive host kinds and diagnostics for values without source positions."""

from .lexer import AkanError


def scalar_kind(value, *, allow_bytearray=False):
    if value is None:
        return "none"
    if isinstance(value, bool):
        return "bool"
    for py, kind in ((int, "int"), (float, "float"), (str, "str"),
                     (bytes, "bytes")):
        if isinstance(value, py):
            return kind
    if allow_bytearray and isinstance(value, bytearray):
        return "bytes"
    return None


class PathAkan(AkanError):
    """An akan in host data, located by a path rather than invented coordinates."""

    def __init__(self, msg: str, where: str):
        Exception.__init__(self, f"akan: at {where}: {msg}")
        self.msg, self.line, self.col, self.source = msg, None, None, None
        self.where = where
