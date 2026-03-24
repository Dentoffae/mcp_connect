"""
Safe calculator using Python AST — eval() is never called.
Supported operators: + - * / // % ** and unary - +
"""

import ast
import operator
from typing import Union

Number = Union[int, float]

_BINARY_OPS = {
    ast.Add:      operator.add,
    ast.Sub:      operator.sub,
    ast.Mult:     operator.mul,
    ast.Div:      operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod:      operator.mod,
    ast.Pow:      operator.pow,
}

_UNARY_OPS = {
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _eval_node(node: ast.AST) -> Number:
    """Recursively evaluate a safe AST node."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"Unsupported constant type: {type(node.value).__name__}")

    if isinstance(node, ast.BinOp):
        op_cls = type(node.op)
        if op_cls not in _BINARY_OPS:
            raise ValueError(f"Unsupported operator: {op_cls.__name__}")
        left  = _eval_node(node.left)
        right = _eval_node(node.right)
        if op_cls is ast.Pow and abs(right) > 300:
            raise ValueError("Exponent too large (max 300)")
        return _BINARY_OPS[op_cls](left, right)

    if isinstance(node, ast.UnaryOp):
        op_cls = type(node.op)
        if op_cls not in _UNARY_OPS:
            raise ValueError(f"Unsupported unary operator: {op_cls.__name__}")
        return _UNARY_OPS[op_cls](_eval_node(node.operand))

    raise ValueError(f"Unsupported expression node: {type(node).__name__}")


def safe_calculate(expression: str) -> Number:
    """
    Parse and evaluate a mathematical expression safely via AST.
    Raises ValueError on unsupported syntax or division by zero.
    """
    expr = expression.strip().replace("^", "**")
    if not expr:
        raise ValueError("Empty expression")
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise ValueError(f"Syntax error in expression '{expr}': {e}")
    try:
        result = _eval_node(tree.body)
    except ZeroDivisionError:
        raise ValueError("Division by zero")
    # Round floats that are actually whole numbers for cleaner output
    if isinstance(result, float) and result == int(result):
        return int(result)
    return result
