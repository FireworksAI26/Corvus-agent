import pytest

from agent.core import _parse_step


def test_parse_valid_step():
    raw = 'some noise {"thought": "t", "tool": "run_python", "args": {"code": "1"}} trailing'
    step = _parse_step(raw)
    assert step["tool"] == "run_python"
    assert step["args"]["code"] == "1"


def test_parse_final_answer():
    step = _parse_step('{"thought": "done", "final_answer": "ok"}')
    assert step["final_answer"] == "ok"


def test_parse_invalid_raises():
    with pytest.raises(ValueError):
        _parse_step("no json here at all")
