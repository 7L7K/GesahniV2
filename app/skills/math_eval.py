from __future__ import annotations

import ast
import math
import os
from typing import Any

EPS = float(os.getenv("MATH_EPS", "1e-9"))
REL_TOL = float(os.getenv("MATH_REL_TOL", "1e-7"))


class EvalError(Exception):
    pass


def _eval_node(node: ast.AST) -> Any:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Num):  # type: ignore
        return node.n  # type: ignore
    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        if isinstance(node.op, ast.Pow):
            return left**right
        if isinstance(node.op, ast.Mod):
            return left % right
        raise EvalError("unsupported binary operator")
    if isinstance(node, ast.UnaryOp):
        operand = _eval_node(node.operand)
        if isinstance(node.op, ast.UAdd):
            return +operand
        if isinstance(node.op, ast.USub):
            return -operand
        raise EvalError("unsupported unary operator")
    if isinstance(node, ast.BoolOp):
        vals = [_eval_node(v) for v in node.values]
        if isinstance(node.op, ast.And):
            return all(vals)
        if isinstance(node.op, ast.Or):
            return any(vals)
        raise EvalError("unsupported boolean operator")
    if isinstance(node, ast.Call):
        # allow only a small whitelist of math functions
        if not isinstance(node.func, ast.Name):
            raise EvalError("invalid function call")
        func = node.func.id
        args = [_eval_node(a) for a in node.args]
        MATH_FUNCS = {
            "sqrt": (math.sqrt, 1),
            "pow": (math.pow, 2),
            "sin": (math.sin, 1),
            "cos": (math.cos, 1),
            "tan": (math.tan, 1),
            "log": (math.log, 1),
            "abs": (abs, 1),
        }
        if func in MATH_FUNCS:
            f, arity = MATH_FUNCS[func]
            if len(args) != arity:
                raise EvalError("wrong_number_of_args")
            return f(*args)
        raise EvalError("unsupported function call")
    if isinstance(node, ast.Name):
        # allow math constants like pi and e
        if node.id == "pi":
            return math.pi
        if node.id == "e":
            return math.e
        raise EvalError("unsupported name")
    if isinstance(node, ast.Compare):
        left = _eval_node(node.left)
        results = []
        for op, comp in zip(node.ops, node.comparators, strict=False):
            right = _eval_node(comp)
            if isinstance(op, ast.Eq):
                results.append(_approx_eq(left, right))
            elif isinstance(op, ast.NotEq):
                results.append(not _approx_eq(left, right))
            elif isinstance(op, ast.Lt):
                results.append(left < right)
            elif isinstance(op, ast.LtE):
                results.append(left <= right)
            elif isinstance(op, ast.Gt):
                results.append(left > right)
            elif isinstance(op, ast.GtE):
                results.append(left >= right)
            else:
                raise EvalError("unsupported comparison")
            left = right
        return all(results)
    raise EvalError(f"unsupported AST node: {type(node)}")


def _approx_eq(a: Any, b: Any) -> bool:
    try:
        return abs(float(a) - float(b)) <= EPS
    except Exception:
        return a == b


def evaluate_expr(expr: str) -> tuple[Any, str]:
    """Safely evaluate a numeric/comparison expression and return (value, explanation).

    Uses the AST module with a small whitelist. Returns either a numeric value or a
    boolean. Raises EvalError for invalid expressions.
    """
    # normalize common notations
    expr = expr.strip()
    expr = expr.replace("^", "**")
    expr = expr.replace("×", "*")
    expr = expr.replace("x", "*")

    # Replace percentages like '20%' -> '(20/100.0)'
    try:
        import re

        expr = re.sub(
            r"(?P<pct>\d+(?:\.\d+)?)\s*%", lambda m: f"(({m.group('pct')})/100.0)", expr
        )
    except Exception:
        pass

    # Normalize single '=' to '==' but avoid touching '!=' '>=' '<=' '=='
    try:
        import re

        expr = re.sub(r"(?<![!<>=])=(?!=)", "==", expr)
    except Exception:
        pass

    # Handle approximate operator (≈, ≃, ≅) by rewriting to an abs diff <= EPS
    try:
        import re

        if re.search(r"[≈≃≅]", expr):
            # replace the first occurrence of a ≈ b with (abs(a-b) <= EPS)
            expr = re.sub(
                r"(?P<a>[^≈≃≅]+?)\s*[≈≃≅]\s*(?P<b>.+)",
                lambda m: f"((abs(({m.group('a').strip()})-({m.group('b').strip()})) <= {EPS}) or (abs(({m.group('a').strip()})-({m.group('b').strip()})) <= {REL_TOL}*abs(({m.group('a').strip()}))) or (abs(({m.group('a').strip()})-({m.group('b').strip()})) <= {REL_TOL}*abs(({m.group('b').strip()}))))",
                expr,
                count=1,
            )
    except Exception:
        pass

    # Handle human-friendly percentage phrasing like '50% of 40' -> (50/100)*40
    try:
        import re

        expr = re.sub(
            r"(?P<pct>\d+(?:\.\d+)?)\s*%\s*of\s*(?P<num>\d+(?:\.\d+)?)",
            lambda m: f"(({m.group('pct')})/100.0)*({m.group('num')})",
            expr,
            flags=re.I,
        )
    except Exception:
        pass

    try:
        node = ast.parse(expr, mode="eval")
    except Exception as e:
        raise EvalError("parse_error") from e

    val = _eval_node(node)
    # Prepare explanation
    if isinstance(val, bool):
        expl = f"Evaluated boolean: {val} (EPS={EPS})"
    else:
        expl = f"Evaluated numeric: {val}"
    return val, expl


__all__ = ["evaluate_expr", "EvalError", "EPS"]
