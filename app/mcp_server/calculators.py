"""Pure finance calculators (no I/O), so they are trivial to unit test."""

import math


def budget_guardrail(monthly_limit: float, spent_so_far: float, days_remaining: int) -> str:
    if (
        not math.isfinite(monthly_limit)
        or not math.isfinite(spent_so_far)
        or monthly_limit <= 0
        or spent_so_far < 0
        or days_remaining <= 0
    ):
        return (
            "Calculation error: limit must be positive, spending non-negative "
            "and days remaining positive."
        )
    remaining = monthly_limit - spent_so_far
    utilization = spent_so_far / monthly_limit * 100
    daily = max(0.0, remaining) / days_remaining
    status = (
        f"Already over budget by ${abs(remaining):.2f}."
        if remaining < 0
        else f"Even daily target: ${daily:.2f}/day."
    )
    return (
        f"Budget used: {utilization:.1f}%; remaining: ${remaining:.2f}; "
        f"days remaining: {days_remaining}. {status}"
    )


def card_rewards(spending_category: str, monthly_spend: float, card_reward_rates: dict[str, float]) -> str:
    if (
        not spending_category.strip()
        or not math.isfinite(monthly_spend)
        or monthly_spend < 0
        or not card_reward_rates
    ):
        return "Comparison error: give category, non-negative spend and known card rates."
    rows = []
    for card, rate in card_reward_rates.items():
        if not card.strip() or not math.isfinite(rate) or rate < 0 or rate > 100:
            return "Comparison error: rates must be between 0 and 100 percent."
        rows.append((card, rate))
    rows.sort(key=lambda r: r[1], reverse=True)
    out = [f"Estimated rewards for ${monthly_spend:.2f}/month in {spending_category}:"]
    out += [f"- {card}: {rate:.2f}% = ${monthly_spend * rate / 100:.2f}/month" for card, rate in rows]
    out.append("Caps, exclusions, fees and redemption restrictions are not included unless supplied.")
    return "\n".join(out)
