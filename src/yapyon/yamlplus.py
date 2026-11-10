"""The opt-in YAML-readable record profile defined by docs/YAMLPLUS.md.

Yapyon's lexer/parser determines values and key provenance. YAML surface
recognition checks membership, not meaning. Source formatting uses located
edits so that comments, field intent, and unselected spellings survive.
"""

from __future__ import annotations

import argparse
import base64
from bisect import bisect_right
import re
import sys

from ._digits import REFUSE_DIGITS, decimal_digits, decimal_text
from ._values import PathAkan
from ._yaml_syntax import check_syntax
from .emitter import _emit_prepared, _record_view
from .export import (MAX_DEPTH, MAX_SIZE, _adapt, _Budget, _dump, _key,
                     _key_step, _options, _Path, _scalar)
from .lexer import AkanError, Lexer, Yakamashiwa
from .loader import _name_of, _refuse_deferred, build
from .parser import (Mapping, MultiMap, Node, Parser, ResolvedTemplate,
                     Scalar, Sequence, Slot, YString)
from .writers import _ydq, _yfloat


_INT11 = re.compile(r"[-+]?(?:0b[01_]+|0[0-7_]+|0|[1-9][0-9_]*|0x[0-9a-fA-F_]+|[1-9][0-9_]*(?::[0-5]?[0-9])+)")
_INT12 = re.compile(r"[-+]?[0-9]+|0o[0-7]+|0x[0-9a-fA-F]+")
_FLOAT11 = re.compile(r"[-+]?(?:[0-9][0-9_]*)?\.[0-9.]*(?:[eE][-+][0-9]+)?|[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+\.[0-9_]*|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN)")
_FLOAT12 = re.compile(r"[-+]?(?:\.[0-9]+|[0-9]+(?:\.[0-9]*)?)(?:[eE][-+]?[0-9]+)?|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN)")

# Schema recognizers must not convert keys: host numeric ranges are irrelevant.
_IMPLICIT = (
    ("boolean", re.compile(
        r"y|Y|yes|Yes|YES|n|N|no|No|NO|true|True|TRUE|false|False|FALSE|"
        r"on|On|ON|off|Off|OFF")),
    ("null", re.compile(r"~|null|Null|NULL|")),
    ("integer", re.compile(f"(?:{_INT11.pattern})|(?:{_INT12.pattern})")),
    ("float", re.compile(f"(?:{_FLOAT11.pattern})|(?:{_FLOAT12.pattern})")),
    ("timestamp", re.compile(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}|"
        r"[0-9]{4}-[0-9]{1,2}-[0-9]{1,2}(?:[Tt]|[ \t]+)[0-9]{1,2}:"
        r"[0-9]{2}:[0-9]{2}(?:\.[0-9]*)?"
        r"(?:(?:[ \t]*)Z|[-+][0-9]{1,2}(?::[0-9]{2})?)?")),
    ("merge", re.compile(r"<<")),
    ("special value", re.compile(r"=")),
)


def _implicit_type(text):
    return next((kind for kind, pattern in _IMPLICIT
                 if pattern.fullmatch(text)), None)


def _key_warning(key, kind, where, *, writing):
    shown = repr(key[:64]) + ("..." if len(key) > 64 else "")
    action = ("quoting it for yamlplus output (an exact non-name key)" if writing else
              "quote the key to prevent YAML conversion (quotation makes it a non-name)")
    return (f"shiran: {where}: YAML may automatically convert key {shown} "
            f"to {kind}; distinct keys can collide; {action}")


def _where(line, col, source):
    return f"{source}:{line}:{col}" if source is not None else f"line {line}, col {col}"


def _fail(message, token, source):
    raise AkanError(f"not yamlplus: {message}", token.line, token.col, source)


def _callback_option(callback, name):
    if callback is not None and not callable(callback):
        raise TypeError(f"{name} must be callable or None")


def _send(callback, messages):
    if callback is not None:
        for message in messages:
            callback(message)


class _Notices:
    def __init__(self):
        self.kinds = {}

    def add(self, kind, where):
        count, first = self.kinds.get(kind, (0, where))
        self.kinds[kind] = count + 1, first

    def messages(self):
        for kind, (count, first) in self.kinds.items():
            meaning = "bytes as literal text, not decoded bytes" if kind == "bytes" else "bare None as text, not null"
            yield (f"hora: {first}: {count} {kind} value(s); YAML reads {meaning}; "
                   "this accepted compatibility difference has no shared typed spelling")


def _zero_escapes(token):
    if token.prefix in ("r", "rb") or token.kind == "BYTES" and token.prefix not in ("b", "rb"):
        return []
    spelling, found = token.lexeme, []
    i = len(token.prefix) + (3 if token.lexeme[len(token.prefix):].startswith('"""') else 1)
    while i < len(spelling) - 1:
        if spelling[i] != "\\":
            i += 1
            continue
        if (spelling[i + 1:i + 2] == "0" and
                spelling[i + 2:i + 3] in tuple("0123456789")):
            end = i + 2
            while end < min(i + 4, len(spelling) - 1) and spelling[end] in "01234567":
                end += 1
            found.append((i, end, "\\x" + format(int(spelling[i + 1:end], 8), "02x")))
        i += 2
    return found


def _read(text, max_digits, source, *, writing=False):
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    _options(max_digits, MAX_DEPTH, MAX_SIZE, None)
    text = text.replace("\r\n", "\n")
    starts = [0] + [i + 1 for i, ch in enumerate(text) if ch == "\n"]

    def where(index):
        line = bisect_right(starts, index)
        return _where(line, index - starts[line - 1], source)

    for index, ch in enumerate(text):
        cp = ord(ch)
        if ((cp < 0x20 and ch not in "\n\t") or 0x7F <= cp <= 0x9F
                or cp in (0x2028, 0x2029, 0xFEFF, 0xFFFE, 0xFFFF)
                or 0xD800 <= cp <= 0xDFFF):
            line = bisect_right(starts, index)
            raise AkanError("not yamlplus: this raw source character is not shared by YAML; "
                            "remove it or escape it inside a double-quoted string",
                            line, index - starts[line - 1], source)
    lexer = Lexer(text, source=source, max_digits=max_digits)
    try:
        tokens = lexer.tokenize()
    except RecursionError:
        raise AkanError("not yamlplus: source nesting exceeds the shared lexer's stack capacity",
                        lexer.line, lexer.col, source) from None
    parser = Parser(tokens, lexer.warnings, source=source)
    try:
        root = parser.parse()
    except RecursionError:
        raise AkanError("not yamlplus: source nesting exceeds the shared parser's stack capacity",
                        tokens[0].line, tokens[0].col, source) from None
    _refuse_deferred(tokens, source)
    for token in tokens:
        if token.kind == "PLUS":
            _fail("multimaps are not YAML mappings; use an ordinary mapping or a sequence of mappings", token, source)
    check_syntax(text, source)
    warnings, edits, notices = list(parser.warnings), [], _Notices()
    literals, depth = {}, 0
    for index, token in enumerate(tokens):
        kind = token.kind
        start = starts[token.line - 1] + token.col
        location = _where(token.line, token.col, source)
        if kind in ("STRING", "QKEY", "BYTES"):
            literals[start] = len(token.lexeme)
            zeros = _zero_escapes(token)
            if kind != "BYTES":
                if token.prefix == "r":
                    warnings.append(f"shiran: {location}: YAML reads the raw literal as text including its prefix/quotes; "
                                    f"a shared string spelling is {_ydq(token.value)}")
                elif token.lexeme.startswith("'") and "\\" in token.lexeme:
                    warnings.append(f"shiran: {location}: YAML single quotes do not decode backslashes; "
                                    f"a shared string spelling is {_ydq(token.value)}")
            for begin, end, replacement in zeros:
                warnings.append(f"shiran: {where(start + begin)}: active \\0 followed by a decimal digit is ambiguous; "
                                f"write {replacement} instead of {token.lexeme[begin:end]}")
            if zeros and writing:
                if kind == "BYTES":
                    edits.extend((start + a, start + b, s) for a, b, s in zeros)
                elif token.lexeme.startswith("'"):
                    edits.append((start, start + len(token.lexeme), _ydq(token.value)))
                else:
                    edits.extend((start + a, start + b, s) for a, b, s in zeros)
            if kind == "BYTES":
                notices.add("bytes", location)
        elif kind == "KEYWORD" and token.value is None:
            notices.add("None", location)
        elif kind in ("INT", "FLOAT"):
            patterns = (_INT11, _INT12) if kind == "INT" else (_FLOAT11, _FLOAT12)
            if not all(pattern.fullmatch(token.lexeme) for pattern in patterns):
                if kind == "INT" and decimal_digits(token.value) > max_digits:
                    _fail("a shared decimal spelling exceeds max_digits; raise max_digits to accept it", token, source)
                alternative = decimal_text(token.value) if kind == "INT" else _yfloat(token.value)
                warnings.append(f"shiran: {location}: YAML 1.1/1.2 interpret this numeric spelling differently; "
                                f"write {alternative} for a shared {'integer' if kind == 'INT' else 'float'} spelling")
        elif kind == "NAME":
            converted = _implicit_type(token.lexeme)
            if converted:
                warnings.append(_key_warning(token.lexeme, converted, location, writing=writing))
                if writing:
                    edits.append((start, start + len(token.lexeme), _ydq(token.value)))
        if kind in ("LBRACKET", "LBRACE"):
            depth += 1
        elif kind in ("RBRACKET", "RBRACE"):
            depth -= 1
        elif kind == "COLON":
            key = tokens[index - 1]
            if key.line != token.line or token.col - key.col > 1024:
                _fail("a YAML implicit key and its colon must be on the same line within 1,024 source characters", key, source)
            after = text[start + 1:start + 2]
            shared = depth and (key.kind == "QKEY" or after in ("[", "{"))
            if after and after not in " \t\n" and not shared:
                warnings.append(f"shiran: {location}: YAML reads a different field boundary; separate ':' from its value with whitespace")
                if writing:
                    edits.append((start + 1, start + 1, " "))
    index = 0
    while index < len(text):
        if index in literals:
            index += literals[index]
        elif text[index] == "#":
            if index and text[index - 1] not in " \t\n":
                warnings.append(f"shiran: {where(index)}: YAML may consume the inline comment as scalar content; separate it with whitespace")
                if writing:
                    edits.append((index, index, " "))
            end = text.find("\n", index)
            index = len(text) if end < 0 else end + 1
        else:
            index += 1
    return root, warnings, list(notices.messages()), text, edits


def check(text, *, warn=None, info=None, max_digits=REFUSE_DIGITS, source=None):
    """Validate complete profile syntax/membership without resolving or loading."""
    _callback_option(warn, "warn")
    _callback_option(info, "info")
    _, warnings, notices, _, _ = _read(text, max_digits, source)
    _send(warn, warnings)
    _send(info, notices)


def is_yamlplus(text, *, warn=None, info=None, max_digits=REFUSE_DIGITS, source=None):
    """Whether text is valid yamlplus; shiran/hora do not make it false."""
    _callback_option(warn, "warn")
    _callback_option(info, "info")
    try:
        _, warnings, notices, _, _ = _read(text, max_digits, source)
    except AkanError:
        return False
    _send(warn, warnings)
    _send(info, notices)
    return True


def loads(text, *, warn=None, info=None, max_digits=REFUSE_DIGITS, source=None):
    """Load literal Yapyon meanings and key provenance, with separate diagnostics."""
    _callback_option(warn, "warn")
    _callback_option(info, "info")
    root, warnings, notices, _, _ = _read(text, max_digits, source)
    _send(warn, warnings)
    _send(info, notices)
    return build(root, source)


def load(fp, *, warn=None, info=None, max_digits=REFUSE_DIGITS, source=None):
    """Load an open UTF-8 text stream; its name supplies the diagnostic source."""
    return loads(fp.read(), warn=warn, info=info, max_digits=max_digits,
                 source=_name_of(fp, source))


def normalize(text, *, warn=None, info=None, max_digits=REFUSE_DIGITS,
              max_size=MAX_SIZE, source=None):
    """Format by selected source edits, preserving comments and field intent.

    Other admitted spellings and layout survive. Quoting a sensitive name
    preserves its text but explicitly changes it to an exact non-name key.
    """
    options = _options(max_digits, MAX_DEPTH, max_size, warn)
    _callback_option(info, "info")
    _, warnings, notices, text, edits = _read(text, options.max_digits, source, writing=True)
    parts, previous = [], 0
    budget = _Budget(options.max_size)
    for start, end, replacement in sorted(edits):
        if start < previous:
            raise Yakamashiwa("overlapping yamlplus source edits")
        for part in (text[previous:start], replacement):
            budget.text(part, "source")
            parts.append(part)
        previous = end
    tail = text[previous:]
    if not text.endswith("\n"):
        tail += "\n"
    budget.text(tail, "source")
    parts.append(tail)
    output = "".join(parts)
    # Quotation/spacing can change YAML token boundaries; never return invalid output.
    _read(output, options.max_digits, source)
    _send(warn, warnings)
    _send(info, notices)
    return output


def _prepare_output(root, *, warn=None, info=None, located=False):
    pending, notices = [(root, _Path())], _Notices()

    def fail(message, path, node):
        if located:
            raise AkanError(message, node.line, node.col,
                            node.source or root.source)
        raise PathAkan(message, str(path))
    while pending:
        node, path = pending.pop()
        if isinstance(node, Scalar):
            if node.type == "bytes":
                node.lexeme = 'b64"' + base64.b64encode(node.value).decode("ascii") + '"'
                notices.add("bytes", f"at {path}")
            else:
                node.lexeme = (_ydq(node.value) if node.type == "str" else
                               _yfloat(node.value) if node.type == "float" else
                               decimal_text(node.value) if node.type == "int" else repr(node.value))
                if node.value is None:
                    notices.add("None", f"at {path}")
            continue
        if isinstance(node, MultiMap):
            fail("multimaps are not yamlplus data", path, node)
        if isinstance(node, Sequence):
            pending.extend((item, path.child(f"[{i}]"))
                           for i, item in reversed(list(enumerate(node.items))))
            continue
        if not isinstance(node, Mapping):
            raise Yakamashiwa(f"unexpected yamlplus node {type(node).__name__}")
        for index, pair in enumerate(node.pairs):
            child_path = path.child(_key_step(pair.key, index))
            if len(pair.key) > 1024:
                fail("a yamlplus key's source spelling must fit within 1,024 characters", child_path, pair)
            converted = _implicit_type(pair.key)
            if converted:
                if warn is not None:
                    warn(_key_warning(pair.key, converted, f"at {child_path}", writing=True))
                pair.lexeme, pair.named = _ydq(pair.key), False
            elif not pair.named:
                pair.lexeme = _ydq(pair.key)
            if len(pair.lexeme or pair.key) > 1024:
                fail("a yamlplus key's source spelling must fit within 1,024 characters", child_path, pair)
        pending.extend((pair.value, path.child(_key_step(pair.key, index)))
                       for index, pair in reversed(list(enumerate(node.pairs))))
    return list(notices.messages())


def _prepare(value, options, info):
    root = _adapt(value, options)
    notices = _prepare_output(root, warn=options.warn)
    text = _emit_prepared(root, options.max_size)
    _read(text, options.max_digits, None)
    _send(info, notices)
    return text


def _from_node(node, *, warn=None, info=None, max_digits=REFUSE_DIGITS,
               max_size=MAX_SIZE):
    """Write resolved data through the same profile preparation/emission path."""
    if not isinstance(node, Node):
        raise TypeError("profile node output needs a resolved internal node")
    _callback_option(warn, "warn")
    _callback_option(info, "info")
    warnings = []
    options = _options(max_digits, MAX_DEPTH, max_size, warnings.append)
    source = node.source
    try:
        root = _record_view(node, source)
        budget, pending = _Budget(options.max_size), [(root, _Path())]
        while pending:
            current, path = pending.pop()
            if isinstance(current, ResolvedTemplate):
                from .serializers import YEETED_YT
                raise AkanError(YEETED_YT, current.line, current.col,
                                current.source or source)
            if isinstance(current, (YString, Slot)):
                raise AkanError("yamlplus output needs resolved literal data",
                                current.line, current.col, current.source or source)
            if isinstance(current, Scalar):
                try:
                    _scalar(current.value, current.type, path, options, budget)
                except (TypeError, ValueError) as error:
                    raise AkanError(str(error), current.line, current.col,
                                    current.source or source) from None
            elif isinstance(current, MultiMap):
                raise AkanError("multimaps are not yamlplus data", current.line,
                                current.col, current.source or source)
            elif isinstance(current, Mapping):
                budget.spend(1 if current.pairs else 2, path)
                for index, pair in enumerate(current.pairs):
                    child = path.child(_key_step(pair.key, index))
                    try:
                        pair.key, pair.named = _key(pair.key, pair.named, child, budget)
                    except (TypeError, ValueError) as error:
                        raise AkanError(str(error), pair.line, pair.col,
                                        pair.source or source) from None
                    pair.lexeme, pair.replace = "", False
                pending.extend((pair.value, path.child(_key_step(pair.key, index)))
                               for index, pair in reversed(list(enumerate(current.pairs))))
            elif isinstance(current, Sequence):
                budget.spend(1 if current.items else 2, path)
                pending.extend((item, path.child(f"[{index}]"))
                               for index, item in reversed(list(enumerate(current.items))))
            else:
                raise Yakamashiwa(f"unexpected resolved node {type(current).__name__}")
        notices = _prepare_output(root, warn=warnings.append, located=True)
        text = _emit_prepared(root, options.max_size)
        _read(text, options.max_digits, source)
    except (ValueError, TypeError, RecursionError) as error:
        raise AkanError(str(error), node.line, node.col, source) from None
    _send(warn, warnings)
    _send(info, notices)
    return text


def dumps(value, *, max_digits=REFUSE_DIGITS, max_depth=MAX_DEPTH,
          max_size=MAX_SIZE, warn=None, info=None):
    """Write host values without key coercion; bytes use an admitted b64 literal.

    Shared export graph, synchronization, resource, and exact-key constraints
    apply. Multimaps refuse; hora reports bytes/None without adapting their types.
    """
    _callback_option(info, "info")
    return _prepare(value, _options(max_digits, max_depth, max_size, warn), info)


def dump(value, fp, *, max_digits=REFUSE_DIGITS, max_depth=MAX_DEPTH,
         max_size=MAX_SIZE, warn=None, info=None):
    """Prepare profile text, then use the shared one-write text-stream contract."""
    options = _options(max_digits, max_depth, max_size, warn)
    _callback_option(info, "info")
    _dump(value, fp, options, prepare=lambda value, options: _prepare(value, options, info))


def main(argv):
    """Validate source, or format it with --write; diagnostics use stderr."""
    arguments = argparse.ArgumentParser(prog=argv[0], description=__doc__)
    arguments.add_argument("--write", action="store_true", help="format to stdout, preserving comments")
    arguments.add_argument("--info", action="store_true", help="show summarized hora compatibility notices on stderr")
    arguments.add_argument("file", nargs="?", help="UTF-8 input file (default: stdin)")
    args = arguments.parse_args(argv[1:])
    from ._cli import run

    def work(text, source):
        messages = []
        try:
            options = {"warn": messages.append, "info": messages.append if args.info else None, "source": source}
            if args.write:
                out = normalize(text, **options)
            else:
                check(text, **options)
                out = ""
        except ValueError as exc:
            raise AkanError(str(exc), 1, 0, source) from None
        return out, messages

    return run([argv[0], *([args.file] if args.file is not None else [])], work)


if __name__ == "__main__":
    from .yamlplus import main as _main
    sys.exit(_main(sys.argv))
