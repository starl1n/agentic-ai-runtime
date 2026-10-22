import pytest
from src.tools.registry import create_default_registry, ToolRegistry
from src.tools.base import BaseTool, tool
from src.providers.base import BaseLlmProvider, MockLlmProvider, MultiProviderGateway, LlmResponse, LlmMessage
from src.agents.orchestrator import AgentRunner
from src.telemetry.cost_tracker import TokenUsage, BudgetExceededException
from pydantic import BaseModel, Field


@pytest.mark.asyncio
async def test_tool_calling_loop_executes_successfully():
    """Verifies that the agent executes the tool, gets the result, and formulates a terminal synthesis."""
    registry = create_default_registry()
    provider = MockLlmProvider()
    runner = AgentRunner(provider=provider, registry=registry)

    result = await runner.run("Analyze our ARR trajectory over 3 years starting from $100k to $550k.")

    assert result.iterations == 2
    assert "Executive Strategic Analysis" in result.final_answer
    assert result.telemetry.total_tokens > 0
    assert result.telemetry.calls_count == 2


@pytest.mark.asyncio
async def test_multi_provider_fallback_on_failure():
    """Verifies that the gateway gracefully falls back to a secondary model if the primary fails."""
    class FailingProvider(BaseLlmProvider):
        async def generate(self, messages, tools):
            raise ConnectionError("Anthropic API 529 Overloaded")

    primary = FailingProvider()
    secondary = MockLlmProvider(model_name="fallback-mock")
    gateway = MultiProviderGateway(providers=[primary, secondary])

    registry = create_default_registry()
    runner = AgentRunner(provider=gateway, registry=registry)

    result = await runner.run("Show financial CAGR metrics.")

    assert len(gateway.fallback_events) == 2  # Fell back on iteration 1 and 2
    assert gateway.fallback_events[0]["failed_provider"] == "FailingProvider"
    assert "Executive Strategic Analysis" in result.final_answer


@pytest.mark.asyncio
async def test_budget_exceeded_guardrail():
    """Verifies that runaway agent loops are halted if cost exceeds maximum budget."""
    telemetry = TokenUsage()
    
    with pytest.raises(BudgetExceededException):
        # Record huge usage exceeding $0.05 limit
        telemetry.record_usage(model="claude-3-5-sonnet", prompt_tokens=50_000, completion_tokens=10_000, max_budget_usd=0.05)


def test_sql_warehouse_mutation_blocking():
    """Verifies that dangerous SQL mutations are safely blocked by tool policy."""
    registry = create_default_registry()
    tool = registry.get("query_analytical_warehouse")
    assert tool is not None

    import asyncio
    result = asyncio.run(tool.execute(query="DROP TABLE organizations;"))
    assert "Security Alert" in result["error"]
