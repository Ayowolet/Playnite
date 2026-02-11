"""
AST-whitelist expression evaluator for action conditions and profile filters.

Uses a whitelist of allowed AST node types and an explicit block on dunder names
and attributes to prevent class-hierarchy escapes that bypass ``__builtins__``
restriction dicts.

Usage
-----
::

    from playnite_python.actions.safe_eval import safe_eval, SafeEvalError

    result = safe_eval("game.play_time > 0", {"game": game})
    # Raises SafeEvalError for: game.__class__, __import__('os'), open(...)
"""

from __future__ import annotations

import ast
import builtins
from typing import Any, Dict, FrozenSet, Type

_SAFE_FUNCTION_NAMES: FrozenSet[str] = frozenset({
    "len", "str", "int", "float", "bool", "any", "all",
    "min", "max", "abs", "round", "sorted", "list",
    "tuple", "set", "isinstance", "hasattr", "getattr",
})

_SAFE_BUILTINS: Dict[str, Any] = {
    name: getattr(builtins, name)
    for name in _SAFE_FUNCTION_NAMES
    if hasattr(builtins, name)
}

_ALLOWED_NODE_TYPES: FrozenSet[Type[ast.AST]] = frozenset({
    ast.Expression,
    # Boolean ops
    ast.BoolOp, ast.And, ast.Or,
    # Unary ops
    ast.UnaryOp, ast.Not, ast.USub, ast.UAdd, ast.Invert,
    # Comparisons
    ast.Compare,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.In, ast.NotIn, ast.Is, ast.IsNot,
    # Arithmetic
    ast.BinOp,
    ast.Add, ast.Sub, ast.Mult, ast.Div,
    ast.Mod, ast.FloorDiv, ast.Pow, ast.MatMult,
    ast.LShift, ast.RShift, ast.BitOr, ast.BitXor, ast.BitAnd,
    # Terminals
    ast.Name, ast.Constant, ast.Attribute,
    # Calls
    ast.Call, ast.keyword,
    # Collections
    ast.List, ast.Tuple, ast.Set, ast.Dict,
    ast.Load,
    # Conditional expression
    ast.IfExp,
    # Subscripts
    ast.Subscript, ast.Slice,
    # Comprehensions (read-only iteration)
    ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp,
    ast.comprehension,
    ast.Store,  # needed inside comprehensions for loop variables
})


class SafeEvalError(ValueError):
    """Raised when the expression contains disallowed constructs."""


class _SafeEvalVisitor(ast.NodeVisitor):
    """Validate that all AST nodes in an expression are on the whitelist."""

    def generic_visit(self, node: ast.AST) -> None:
        if type(node) not in _ALLOWED_NODE_TYPES:
            raise SafeEvalError(
                f"Disallowed AST node type: {type(node).__name__}"
            )
        super().generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id.startswith("__") and node.id.endswith("__"):
            raise SafeEvalError(f"Dunder name not allowed: {node.id!r}")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr.startswith("__") and node.attr.endswith("__"):
            raise SafeEvalError(f"Dunder attribute not allowed: {node.attr!r}")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # Allow whitelisted built-in names and method calls on objects
        if isinstance(node.func, ast.Name):
            if node.func.id not in _SAFE_FUNCTION_NAMES:
                raise SafeEvalError(
                    f"Function call not allowed: {node.func.id!r}"
                )
        elif not isinstance(node.func, ast.Attribute):
            raise SafeEvalError("Only simple function/method calls are allowed")
        self.generic_visit(node)


def safe_eval(expr: str, ctx: Dict[str, Any]) -> Any:
    """
    Evaluate *expr* safely against *ctx* using an AST whitelist.

    Only arithmetic, comparisons, boolean logic, attribute access, whitelisted
    built-in calls, and method calls are allowed.  Dunder names/attributes,
    non-whitelisted function calls, and all statement-level constructs are
    rejected before evaluation.

    Security
    --------
    Method calls on context objects (e.g. ``game.name.lower()``) are
    permitted because they are structurally indistinguishable from safe
    attribute lookups followed by a call.  The safety guarantee relies on
    the objects in *ctx* not exposing dangerous methods.  Callers **must**
    ensure that every object placed in *ctx* is a trusted, library-controlled
    type (e.g. :class:`~models.game.Game`).  Never pass raw user-supplied
    objects or objects that inherit from user-controlled code.

    Parameters
    ----------
    expr:
        Python expression string to evaluate.
    ctx:
        Variable bindings (e.g. ``{"game": game}``).

    Returns
    -------
    Any
        The result of evaluating *expr*.

    Raises
    ------
    SafeEvalError
        If the expression contains disallowed constructs **or has a syntax
        error**.  ``SafeEvalError`` is a subclass of ``ValueError``, so
        callers that catch ``ValueError`` continue to work unchanged.
    """
    try:
        tree = ast.parse(expr.strip(), mode="eval")
    except SyntaxError as exc:
        raise SafeEvalError(f"Syntax error in expression: {exc}") from exc
    _SafeEvalVisitor().visit(tree)
    return eval(  # noqa: S307
        compile(tree, "<safe_expr>", "eval"),
        {"__builtins__": _SAFE_BUILTINS},
        ctx,
    )
