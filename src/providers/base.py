import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

logger = logging.getLogger("agentic_runtime")


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class LlmMessage:
    role: str  # system, user, assistant, tool
    content: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
    tool_call_id: Optional[str] = None


@dataclass
class LlmResponse:
    content: Optional[str] = None
    tool_calls: List[ToolCall] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = "unknown"
    provider: str = "unknown"


class BaseLlmProvider(ABC):
    @abstractmethod
    async def generate(self, messages: List[LlmMessage], tools: List[Dict[str, Any]]) -> LlmResponse:
        pass


class MockLlmProvider(BaseLlmProvider):
    """
    Deterministic production simulator.
    Demonstrates realistic agentic tool-calling without consuming live API tokens.
    """
    def __init__(self, model_name: str = "mock-llm"):
        self.model_name = model_name
        self.call_count = 0

    async def generate(self, messages: List[LlmMessage], tools: List[Dict[str, Any]]) -> LlmResponse:
        self.call_count += 1
        last_msg = messages[-1]

        # Step 2: If previous message was a tool result, formulate executive answer
        if last_msg.role == "tool":
            return LlmResponse(
                content=(
                    "### 📊 Executive Strategic Analysis\n\n"
                    "Based on the analytical data retrieved:\n"
                    "- **Financial Trajectory**: The organization achieved a **68.18% CAGR** over the 3-year evaluation window.\n"
                    "- **Profitability**: Projected annual EBITDA stands at **$137,500 USD** (25% EBITDA margin on $550k ARR).\n"
                    "- **Customer Cohorts**: Enterprise retention remains exceptionally strong at **98.5%** with 2,520 aggregate active seats across top tenants.\n\n"
                    "**Recommendation**: The metrics demonstrate healthy unit economics and warrant proceeding with the planned expansion."
                ),
                tool_calls=[],
                prompt_tokens=320,
                completion_tokens=140,
                model=self.model_name,
                provider="mock",
            )

        # Step 1: Detect intent and trigger appropriate tool call
        user_text = ""
        for m in reversed(messages):
            if m.role == "user" and m.content:
                user_text = m.content.lower()
                break

        if "growth" in user_text or "cagr" in user_text or "revenue" in user_text or "finance" in user_text:
            return LlmResponse(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="call_cagr_101",
                        name="calculate_financial_metrics",
                        arguments={"initial_revenue": 100000.0, "ending_revenue": 550000.0, "years": 3, "ebitda_margin_pct": 25.0},
                    )
                ],
                prompt_tokens=180,
                completion_tokens=45,
                model=self.model_name,
                provider="mock",
            )

        # Default query warehouse
        return LlmResponse(
            content=None,
            tool_calls=[
                ToolCall(
                    id="call_sql_202",
                    name="query_analytical_warehouse",
                    arguments={"query": "SELECT tenant_id, tier, arr_usd FROM organizations WHERE retention_rate > 0.95 ORDER BY arr_usd DESC"},
                )
            ],
            prompt_tokens=210,
            completion_tokens=52,
            model=self.model_name,
            provider="mock",
        )


class MultiProviderGateway(BaseLlmProvider):
    """
    Resilient Gateway: Coordinates multi-provider fallback.
    If the primary provider suffers rate limits (429) or timeouts, it automatically falls back
    to secondary providers while recording failover telemetry.
    """
    def __init__(self, providers: List[BaseLlmProvider]):
        if not providers:
            raise ValueError("Gateway requires at least one provider.")
        self.providers = providers
        self.fallback_events: List[Dict[str, Any]] = []

    async def generate(self, messages: List[LlmMessage], tools: List[Dict[str, Any]]) -> LlmResponse:
        errors = []
        for index, provider in enumerate(self.providers):
            try:
                response = await provider.generate(messages, tools)
                return response
            except Exception as ex:
                logger.warning(f"Provider {provider.__class__.__name__} failed: {ex}. Attempting fallback...")
                self.fallback_events.append({
                    "failed_provider": provider.__class__.__name__,
                    "error": str(ex),
                    "fallback_index": index + 1,
                })
                errors.append(f"{provider.__class__.__name__}: {ex}")

        raise RuntimeError(f"All providers in the fallback chain exhausted. Failures: {'; '.join(errors)}")
