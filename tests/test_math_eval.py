from app.skills.math_eval import evaluate_expr, EvalError


def test_basic_arithmetic():
    v, e = evaluate_expr("9+9")
    assert v == 18
    v, e = evaluate_expr("2*(3+4)/5")
    assert abs(v - (2 * (3 + 4) / 5)) < 1e-9
    v, e = evaluate_expr("50% of 40")
    assert abs(v - 20.0) < 1e-9


def test_sqrt_and_pow_and_approx():
    v, e = evaluate_expr("sqrt(16)")
    assert v == 4
    v, e = evaluate_expr("2^3")
    assert v == 8
    b, e = evaluate_expr("9 == 9")
    assert b is True
    b, e = evaluate_expr("10/3 != 3")
    assert b is True


