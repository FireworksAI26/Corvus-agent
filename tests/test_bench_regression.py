"""Bench regression gate."""
from evals.benchmark import check_regression


def test_no_history_no_regression():
    assert check_regression([]) == (False, 0.0)
    assert check_regression([{"pass_rate": 1.0}]) == (False, 0.0)


def test_improvement_is_not_a_regression():
    regressed, delta = check_regression([{"pass_rate": 0.6}, {"pass_rate": 0.8}])
    assert regressed is False and round(delta, 2) == 0.2


def test_drop_is_flagged():
    regressed, delta = check_regression([{"pass_rate": 1.0}, {"pass_rate": 0.66}])
    assert regressed is True and delta < 0


def test_noise_within_epsilon_is_ok():
    regressed, _ = check_regression([{"pass_rate": 0.90}, {"pass_rate": 0.895}], epsilon=0.01)
    assert regressed is False
