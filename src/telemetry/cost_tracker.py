from dataclasses import dataclass, field
from typing import Dict

# Pricing per million tokens (USD)
MODEL_PRICING: Dict[str, Dict[str, float]] = {
    # Anthropic
    "claude-3-5-sonnet": {"input": 3.00, "output": 15.00},
    "claude-3-5-haiku": {"input": 0.80, "output": 4.00},
    # OpenAI
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    # Google Gemini
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    # Mock / Demo
    "mock-llm": {"input": 0.00, "output": 0.00},
}


class BudgetExceededException(Exception):
    """Raised when an agent execution exceeds its assigned fiscal budget."""
    pass


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    calls_count: int = 0
    cost_breakdown: list = field(default_factory=list)

    def record_usage(self, model: str, prompt_tokens: int, completion_tokens: int, max_budget_usd: float = 1.0) -> float:
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.total_tokens += (prompt_tokens + completion_tokens)
        self.calls_count += 1

        pricing = MODEL_PRICING.get(model, {"input": 2.00, "output": 8.00})
        cost = (prompt_tokens / 1_000_000 * pricing["input"]) + (completion_tokens / 1_000_000 * pricing["output"])
        self.total_cost_usd += cost

        self.cost_breakdown.append({
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "step_cost_usd": round(cost, 6),
        })

        if self.total_cost_usd > max_budget_usd:
            raise BudgetExceededException(
                f"Agent run exceeded safety budget limit (${max_budget_usd:.4f}). "
                f"Current accumulated spend: ${self.total_cost_usd:.4f}"
            )

        return cost
