import json
import asyncio
from typing import List, Dict, Any, AsyncGenerator
from src.providers.base import BaseLlmProvider, LlmMessage, ToolCall
from src.tools.registry import ToolRegistry
from src.telemetry.cost_tracker import TokenUsage


class AgentExecutionResult:
    def __init__(self, final_answer: str, iterations: int, messages: List[LlmMessage], telemetry: TokenUsage):
        self.final_answer = final_answer
        self.iterations = iterations
        self.messages = messages
        self.telemetry = telemetry

    def to_dict(self) -> Dict[str, Any]:
        return {
            "final_answer": self.final_answer,
            "iterations": self.iterations,
            "telemetry": {
                "total_tokens": self.telemetry.total_tokens,
                "prompt_tokens": self.telemetry.prompt_tokens,
                "completion_tokens": self.telemetry.completion_tokens,
                "total_cost_usd": round(self.telemetry.total_cost_usd, 6),
                "calls_count": self.telemetry.calls_count,
            },
        }


class AgentRunner:
    def __init__(
        self,
        provider: BaseLlmProvider,
        registry: ToolRegistry,
        system_prompt: str = "You are a Principal AI Strategic Analyst. Use available tools accurately to answer enterprise questions.",
        max_iterations: int = 8,
        max_budget_usd: float = 0.50,
    ):
        self.provider = provider
        self.registry = registry
        self.system_prompt = system_prompt
        self.max_iterations = max_iterations
        self.max_budget_usd = max_budget_usd

    async def run(self, user_prompt: str) -> AgentExecutionResult:
        messages: List[LlmMessage] = [
            LlmMessage(role="system", content=self.system_prompt),
            LlmMessage(role="user", content=user_prompt),
        ]
        telemetry = TokenUsage()
        tools_schema = self.registry.list_tools()

        for iteration in range(1, self.max_iterations + 1):
            # 1. Query LLM Provider
            response = await self.provider.generate(messages, tools_schema)
            telemetry.record_usage(
                model=response.model,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                max_budget_usd=self.max_budget_usd,
            )

            # 2. Check if agent responded directly without tools
            if not response.tool_calls:
                messages.append(LlmMessage(role="assistant", content=response.content))
                return AgentExecutionResult(
                    final_answer=response.content or "Task completed.",
                    iterations=iteration,
                    messages=messages,
                    telemetry=telemetry,
                )

            # 3. Process Tool Calls
            messages.append(LlmMessage(role="assistant", content=response.content, tool_calls=response.tool_calls))

            async def _run_tool(call: ToolCall):
                res = await self.registry.execute_tool(call.name, call.arguments)
                return call, res

            tool_executions = await asyncio.gather(*[_run_tool(tc) for tc in response.tool_calls])

            for call, execution_result in tool_executions:
                messages.append(
                    LlmMessage(
                        role="tool",
                        content=json.dumps(execution_result),
                        tool_call_id=call.id,
                    )
                )

        # Max iterations reached
        return AgentExecutionResult(
            final_answer="Execution reached maximum configured tool-calling iterations.",
            iterations=self.max_iterations,
            messages=messages,
            telemetry=telemetry,
        )

    async def stream_events(self, user_prompt: str) -> AsyncGenerator[Dict[str, Any], None]:
        """Server-Sent Events (SSE) generator for streaming tool and reasoning progress."""
        messages: List[LlmMessage] = [
            LlmMessage(role="system", content=self.system_prompt),
            LlmMessage(role="user", content=user_prompt),
        ]
        telemetry = TokenUsage()
        tools_schema = self.registry.list_tools()

        yield {"event": "start", "data": {"status": "initializing_loop", "max_iterations": self.max_iterations}}

        for iteration in range(1, self.max_iterations + 1):
            yield {"event": "iteration_start", "data": {"iteration": iteration}}

            response = await self.provider.generate(messages, tools_schema)
            telemetry.record_usage(
                model=response.model,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                max_budget_usd=self.max_budget_usd,
            )

            if not response.tool_calls:
                yield {
                    "event": "final_answer",
                    "data": {
                        "content": response.content,
                        "iteration": iteration,
                        "telemetry": {
                            "total_tokens": telemetry.total_tokens,
                            "cost_usd": round(telemetry.total_cost_usd, 6),
                        },
                    },
                }
                return

            for tc in response.tool_calls:
                yield {
                    "event": "tool_calling",
                    "data": {"tool": tc.name, "arguments": tc.arguments, "call_id": tc.id},
                }

            messages.append(LlmMessage(role="assistant", content=response.content, tool_calls=response.tool_calls))

            for tc in response.tool_calls:
                result = await self.registry.execute_tool(tc.name, tc.arguments)
                yield {
                    "event": "tool_result",
                    "data": {"tool": tc.name, "result": result, "call_id": tc.id},
                }
                messages.append(LlmMessage(role="tool", content=json.dumps(result), tool_call_id=tc.id))

        yield {
            "event": "timeout",
            "data": {"message": "Maximum reasoning iterations exhausted without terminal answer."},
        }
