from app.mcp_server.calculators import budget_guardrail, card_rewards


def test_budget_on_track():
    out = budget_guardrail(350, 100, 10)
    assert "Budget used: 28.6%" in out
    assert "remaining: $250.00" in out
    assert "$25.00/day" in out


def test_budget_over():
    assert "over budget by $50.00" in budget_guardrail(300, 350, 5)


def test_budget_rejects_bad_input():
    for args in [(0, 10, 5), (100, -1, 5), (100, 10, 0), (float("nan"), 1, 1)]:
        assert "Calculation error" in budget_guardrail(*args)


def test_rewards_sorted_and_computed():
    out = card_rewards("dining", 400, {"A": 2.0, "B": 3.0})
    lines = out.splitlines()
    assert lines[1].startswith("- B: 3.00% = $12.00")
    assert lines[2].startswith("- A: 2.00% = $8.00")


def test_rewards_rejects_bad_rates():
    assert "Comparison error" in card_rewards("dining", 100, {"A": 150})
    assert "Comparison error" in card_rewards("dining", 100, {})
