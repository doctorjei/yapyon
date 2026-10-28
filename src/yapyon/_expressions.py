"""Deferred expressions and collection construction on the resolver's one paths."""

import copy
import operator

from .lexer import Ref, Yakamashiwa, parse_ref
from .parser import (Comprehension, Copy, Expression, Mapping, Merge, MultiMap,
                     Node, Pair, Scalar, Sequence, Slot, YString, children)


class _Waiting(Exception):
    pass


def source(node):
    """Expression source, never evaluation; ordinary nested maps keep key kinds."""
    from .assembly import MergedMapping

    if isinstance(node, MergedMapping) and node.layers:
        return "(" + " | ".join(map(source, node.layers)) + ")"
    if isinstance(node, Merge):
        return "(" + " | ".join(map(source, node.args)) + ")"
    if isinstance(node, Comprehension):
        iterable, body, predicate, key = node.args
        separator = ":= " if getattr(node, "replace", False) else ": "
        head = source(body) if node.kind == "list" else source(key) + separator + source(body)
        tail = " for " + ", ".join(getattr(node, "binding_lexemes", node.names)) + " in " + source(iterable)
        if predicate is not None:
            tail += " if " + source(predicate)
        left, right = ("[", "]") if node.kind == "list" else ("{", "}")
        return left + ("+ " if node.kind == "multimap" else "") + head + tail + right
    if isinstance(node, Expression):
        if node.op == "subscript":
            return source(node.args[0]) + "[" + source(node.args[1]) + "]"
        if node.op == "suffix":
            text, safe = node.value
            return source(node.args[0]) + ("?." if safe else ".") + text
        if node.op == "group":
            text = source(node.args[0])
            return text if isinstance(node.args[0], Merge) else "(" + text + ")"
        if node.op == "not":
            return "(not " + source(node.args[0]) + ")"
        if node.op in ("and", "or"):
            return "(" + (" " + node.op + " ").join(map(source, node.args)) + ")"
        if node.op == "compare":
            text = source(node.args[0])
            for op, arg in zip(node.value, node.args[1:]):
                text += " " + op + " " + source(arg)
            return "(" + text + ")"
    if isinstance(node, Copy):
        return node.lexeme or "(" + node.ref + ")"
    if isinstance(node, YString):
        return node.lexeme
    if isinstance(node, Scalar):
        from .emitter import _scalar
        return node.lexeme or _scalar(node)
    if isinstance(node, Sequence):
        return "[" + ", ".join(map(source, node.items)) + "]"
    if isinstance(node, (Mapping, MultiMap)):
        pairs = node.pairs if isinstance(node, Mapping) else node.entries
        out = []
        for pair in pairs:
            key = (source(pair.key) if isinstance(pair.key, Node) else
                   pair.lexeme or (pair.key if pair.named else
                                   source(Scalar(pair.line, pair.col, "str", pair.key))))
            value = pair.value
            if isinstance(value, Slot):
                key += value.lexeme
                value = value.layers[0]
            out.append(key + (":= " if pair.replace else ": ") + source(value))
        return "{" + ("+ " if isinstance(node, MultiMap) and pairs else
                      "+" if isinstance(node, MultiMap) else "") + ", ".join(out) + "}"
    raise Yakamashiwa(f"cannot write expression node {type(node).__name__}")


def _ready(resolver, owner, index, site):
    """Resolve an operand locally, retaining successful work across fixpoint passes."""
    from .resolver import _Site, _collect, _unfilled, unfilled_message

    holder = [owner.args[index]]
    while True:
        sites = []
        replace = lambda new: holder.__setitem__(0, new)
        if isinstance(holder[0], YString):
            sites.append(_Site(holder[0], site.chain, replace, key=site.key,
                               bindings=getattr(holder[0], "_bindings", site.bindings)))
        else:
            _collect(holder[0], site.chain, sites, replace, site.bindings)
        slot = _unfilled(holder[0])
        if slot is not None:
            resolver._akan(unfilled_message(slot), slot)
        if not sites:
            owner.args[index] = holder[0]
            return holder[0]
        progress = False
        for local in sites:
            if site.key:
                local.key = True
            value = resolver._try(local)
            if value is not None:
                local.replace(value)
                if local.key and local.reads:
                    resolver._key_reads.append(local)
                progress = True
        owner.args[index] = holder[0]
        if not progress:
            raise _Waiting


def _condition(resolver, node, at):
    if isinstance(node, Scalar):
        if node.type == "bool":
            return node.value
        if node.type == "none":
            return False
    resolver._akan("a condition takes True, False, or None, not "
                   + (node.type if isinstance(node, Scalar) else type(node).__name__), at)


def _result(resolver, node, value):
    depth = 1 + max((resolver._deep_depth(arg) for arg in node.args
                     if isinstance(arg, Node)), default=0)
    if depth > resolver.max_depth:
        resolver._akan(f"resolution exceeded the depth ceiling ({resolver.max_depth})", node)
    resolver._note_depth(depth, node)
    resolver._depth[id(value)] = depth
    resolver._facts.pop(id(value), None)
    value.source = node.source
    value.fill_checks += node.fill_checks
    return value


def _suffix(resolver, node, receiver, site):
    text, safe = node.value
    parsed = parse_ref(text)
    if parsed.call is None:
        current = receiver
        for step in parsed.steps:
            current = resolver._step(current, step, text, site)
            if isinstance(current, YString):
                raise _Waiting
        return current
    call = parsed.call
    inner = call
    while inner.receiver and isinstance(inner.args[0], Ref) and inner.args[0].call is not None:
        inner = inner.args[0].call
    if inner.receiver:
        current = receiver
        for step in inner.args[0].steps:
            current = resolver._step(current, step, text, site)
            if isinstance(current, YString):
                raise _Waiting
        inner.args[0] = current
    else:
        inner.args.insert(0, receiver)
        inner.receiver = True
    inner.safe = inner.safe or safe
    value = resolver._link(call, text, site)
    if isinstance(value, YString):
        raise _Waiting
    return value


def _compare(resolver, op, left, right, at):
    if op in ("is", "is not"):
        answer = isinstance(left, Scalar) and left.type == "none"
        return answer if op == "is" else not answer
    from .loader import build

    a, b = build(left), build(right)
    try:
        if op in ("in", "not in"):
            if isinstance(right, (Mapping, MultiMap)):
                pairs = right.pairs if isinstance(right, Mapping) else right.entries
                answer = any(a == pair.key for pair in pairs)
            elif isinstance(right, Sequence) or isinstance(right, Scalar) and right.type in ("str", "bytes"):
                answer = a in b
            else:
                resolver._akan("membership needs a list, mapping, multimap, text, or bytes", at)
            return answer if op == "in" else not answer
        functions = {"==": operator.eq, "!=": operator.ne, "<": operator.lt,
                     "<=": operator.le, ">": operator.gt, ">=": operator.ge}
        return functions[op](a, b)
    except (TypeError, ValueError) as exc:
        resolver._akan(f"cannot compare these values with {op}: {exc}", at)


def _charge(resolver, node, at):
    size, pending = 0, [node]
    while pending:
        child = pending.pop()
        size += (len(child.value) if isinstance(child, Scalar)
                 and child.type in ("str", "bytes") else 1)
        pending.extend(children(child))
        if resolver.rendered + size > resolver.max_size:
            resolver._akan(f"document exceeds the rendered-size ceiling ({resolver.max_size})", at)
    resolver.rendered += size


def _bind(node, bindings):
    node._bindings = bindings
    for child in children(node):
        _bind(child, bindings)


def _comprehend(resolver, node, site):
    if not hasattr(node, "_input"):
        iterable = _ready(resolver, node, 0, site)
        if isinstance(iterable, Sequence):
            wanted, items = 1, iterable.items
        elif isinstance(iterable, (Mapping, MultiMap)):
            wanted = 2
            items = iterable.pairs if isinstance(iterable, Mapping) else iterable.entries
        else:
            resolver._akan("a comprehension iterates a list, dictionary, or multimap", node)
        if len(node.names) != wanted:
            resolver._akan(f"this collection needs {wanted} iteration binding"
                           f"{'' if wanted == 1 else 's'}, not {len(node.names)}", node)
        node._input, node._index, node._predicate = items, 0, None
        cls = {"list": Sequence, "dict": Mapping, "multimap": MultiMap}[node.kind]
        node._output = cls(node.line, node.col, [])
    from .resolver import _Site, _key_slot

    while node._index < len(node._input):
        item = node._input[node._index]
        bindings = dict(site.bindings)
        if isinstance(item, Pair):
            key = Scalar(item.line, item.col, "str", item.key)
            key.source = item.source
            bindings.update(zip(node.names, (key, item.value)))
        else:
            bindings[node.names[0]] = item
        if not hasattr(node, "_current"):
            if node.args[2] is not None:
                if node._predicate is None:
                    node._predicate = Expression(node.line, node.col, "predicate",
                                                 [copy.deepcopy(node.args[2])])
                    _bind(node._predicate.args[0], bindings)
                local = _Site(node, site.chain, None, key=site.key, bindings=bindings)
                tested = _ready(resolver, node._predicate, 0, local)
                if local.reads:
                    resolver._key_reads.append(local)
                include = _condition(resolver, tested, node.args[2])
            else:
                include = True
            if not include:
                node._index += 1
                node._predicate = None
                continue
            _charge(resolver, node.args[1], node)
            body = copy.deepcopy(node.args[1])
            _bind(body, bindings)
            current = Expression(node.line, node.col, "item", [body])
            if node.kind == "list":
                node._output.items.append(body)
                current.pair = None
            else:
                _charge(resolver, node.args[3], node)
                key = copy.deepcopy(node.args[3])
                _bind(key, bindings)
                pair = Pair(key.line, key.col, key, body, source(node.args[3]),
                            named=False, replace=getattr(node, "replace", False))
                pair.source = key.source
                target = node._output.pairs if node.kind == "dict" else node._output.entries
                target.append(pair)
                current.args.append(key)
                current.pair = pair
                current.key_done = False
            node._current = current
        current = node._current
        key_scope = site.key_scope if site.key_scope is not None else node._output
        chain = ([(key_scope, current.pair)] + site.chain
                 if node.kind == "dict" else site.chain)
        local = _Site(node, chain, None, bindings=bindings)
        if current.pair is not None and not current.key_done:
            local.key = True
            key = _ready(resolver, current, 1, local)
            _key_slot(node._output, current.pair)(key)
            if local.reads:
                resolver._key_reads.append(local)
            current.key_done = True
            local.key = False
        if site.key and not site.contribution:
            local.key = True
        body = (current.args[0] if site.contribution
                else _ready(resolver, current, 0, local))
        if current.pair is None:
            node._output.items[-1] = body
        else:
            current.pair.value = body
            if isinstance(node._output, Mapping):
                node._output.reindex()
        node._index += 1
        node._predicate = None
        del node._current
    if isinstance(node._output, Mapping):
        node._output.reindex()
        # Completed fills may retain this contribution for deferred checks.
        # Keep its pair view live even after the site is replaced by output.
        node.pairs = node._output.pairs
        node.reindex()
        node._expanded = True
    return _result(resolver, node, node._output)


def _receiver(resolver, owner, site):
    """Receiver links share a short-circuit boundary; grouped operands do not."""
    from .resolver import _Site

    node = owner.args[0]
    local = _Site(node, site.chain, None, key=site.key, bindings=site.bindings)
    if isinstance(node, Expression) and node.op in ("subscript", "suffix"):
        value = _evaluate(resolver, local)
    elif isinstance(node, Copy) and not node.lexeme.lstrip().startswith("("):
        parsed = parse_ref(node.ref)
        if parsed.call is None:
            return _ready(resolver, owner, 0, site)
        target = resolver._link(parsed.call, node.ref, local)
        value = resolver._copy_value(target, local)
        if value is None:
            raise _Waiting
    else:
        return _ready(resolver, owner, 0, site)
    owner.args[0] = value
    site.reads.extend(local.reads)
    return value


def _merge(resolver, node, site):
    from .assembly import _PENDING, _combine, kind
    from .resolver import _Site

    earlier, later = node.args
    resolver._merge_budget(node, depth=1)
    out = _combine(earlier, later, charge=resolver._merge_budget)
    if out is not _PENDING:
        return _result(resolver, node, out)
    for index in (1, 0):
        operand = node.args[index]
        if kind(operand) is not None:
            continue
        if not isinstance(operand, YString):
            raise _Waiting
        local = _Site(operand, site.chain,
                      lambda new, i=index: node.args.__setitem__(i, new),
                      key=site.key, bindings=getattr(operand, "_bindings", site.bindings))
        value = resolver._try(local)
        site.reads.extend(local.reads)
        if value is None:
            raise _Waiting
        node.args[index] = value
        out = _combine(*node.args, charge=resolver._merge_budget)
        if out is not _PENDING:
            return _result(resolver, node, out)
    earlier = _ready(resolver, node, 0, site)
    later = _ready(resolver, node, 1, site)
    _charge(resolver, earlier, node)
    _charge(resolver, later, node)

    out = _combine(earlier, later, collections=True, charge=resolver._merge_budget)
    if out is _PENDING:
        raise _Waiting
    return _result(resolver, node, out)


def _evaluate(resolver, site):
    node = site.node
    if isinstance(node, Merge):
        return _merge(resolver, node, site)
    if isinstance(node, Comprehension):
        return _comprehend(resolver, node, site)
    if node.op == "group":
        from .assembly import project
        view = project(node.args[0])
        if isinstance(view, Mapping):
            return _result(resolver, node, view)
    left = (_receiver(resolver, node, site) if node.op in ("subscript", "suffix")
            else _ready(resolver, node, 0, site))
    if node.op in ("and", "or", "not"):
        answer = _condition(resolver, left, node)
        if node.op == "not":
            answer = not answer
        elif node.op == "and" and answer or node.op == "or" and not answer:
            answer = _condition(resolver, _ready(resolver, node, 1, site), node)
        value = Scalar(node.line, node.col, "bool", answer)
    elif node.op == "compare":
        answer = True
        for i, op in enumerate(node.value, 1):
            right = _ready(resolver, node, i, site)
            if not _compare(resolver, op, left, right, node):
                answer = False
                break
            left = right
        value = Scalar(node.line, node.col, "bool", answer)
    elif node.op == "subscript":
        key = _ready(resolver, node, 1, site)
        if not isinstance(key, Scalar) or key.type not in ("int", "str"):
            resolver._akan("a subscript takes an integer index or string key", node)
        step = ("index" if key.type == "int" else "sub", key.value)
        value = resolver._step(left, step, source(node), site)
        if isinstance(value, YString):
            raise _Waiting
    elif node.op == "suffix":
        value = _suffix(resolver, node, left, site)
    elif node.op in ("identity", "group"):
        value = left
    else:
        raise Yakamashiwa(f"unknown expression operation {node.op}")
    return _result(resolver, node, value)


def evaluate(resolver, site):
    """One expression site: a value, or None to join the ordinary fixpoint."""
    from .resolver import _Short

    try:
        return _evaluate(resolver, site)
    except _Waiting:
        return None
    except _Short:
        return _result(resolver, site.node,
                       Scalar(site.node.line, site.node.col, "none", None))
