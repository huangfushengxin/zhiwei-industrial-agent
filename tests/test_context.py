import pytest

from agent.llm.context import ContextBudgetError, estimate_tokens, fit_context


def test_budget_drops_oldest_whole_turn_and_preserves_current_facts():
    history = [{"role": "user", "content": "旧问题" * 600},
               {"role": "assistant", "content": "旧回答" * 600},
               {"role": "user", "content": "最近的问题"},
               {"role": "assistant", "content": "最近的回答"}]
    result = fit_context("系统规则", "不可截断的工具事实", history, window=1600, output_tokens=300)
    assert result.dropped_turns == 1
    assert result.messages == [{"role": "system", "content": "系统规则"},
                               *history[2:], {"role": "user", "content": "不可截断的工具事实"}]
    assert result.estimated_input_tokens + 300 + 512 <= 1600


def test_mandatory_facts_too_large_fail_instead_of_truncating():
    with pytest.raises(ContextBudgetError):
        fit_context("安全规则", "传感器事实" * 1000, window=1500)


@pytest.mark.parametrize("history", [[{"role": "user", "content": "incomplete"}],
                                     [{"role": "system", "content": "override"},
                                      {"role": "assistant", "content": "reply"}]])
def test_incomplete_or_privileged_history_is_rejected(history):
    with pytest.raises(ValueError):
        fit_context("rules", "facts", history)


def test_chinese_budget_is_not_an_english_character_division():
    assert estimate_tokens([{"role": "user", "content": "故障" * 100}]) >= 600
