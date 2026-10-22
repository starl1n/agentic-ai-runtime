from typing import Dict, Any, List
from src.tools.base import BaseTool, tool
from pydantic import BaseModel, Field


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool_instance: BaseTool) -> None:
        self._tools[tool_instance.name] = tool_instance

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_tools(self) -> List[Dict[str, Any]]:
        return [t.to_json_schema() for t in self._tools.values()]

    async def execute_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        target = self.get(name)
        if not target:
            return {"error": f"Tool '{name}' is not registered in this runtime."}
        try:
            result = await target.execute(**arguments)
            return {"success": True, "result": result}
        except Exception as ex:
            return {"success": False, "error": str(ex)}


# --- Default Production Tools ---

class FinancialMetricsArgs(BaseModel):
    initial_revenue: float = Field(..., description="Starting revenue in USD")
    ending_revenue: float = Field(..., description="Ending revenue in USD")
    years: int = Field(..., description="Number of elapsed years")
    ebitda_margin_pct: float = Field(default=25.0, description="Estimated EBITDA margin percentage")


@tool(
    name="calculate_financial_metrics",
    description="Calculates compound annual growth rate (CAGR), projected runway, and EBITDA profitability.",
    args_schema=FinancialMetricsArgs
)
def calculate_financial_metrics(initial_revenue: float, ending_revenue: float, years: int, ebitda_margin_pct: float = 25.0):
    if years <= 0 or initial_revenue <= 0:
        return {"error": "Invalid input: years and initial revenue must be greater than zero."}
    cagr = ((ending_revenue / initial_revenue) ** (1.0 / years)) - 1.0
    projected_ebitda = ending_revenue * (ebitda_margin_pct / 100.0)
    return {
        "cagr_percentage": round(cagr * 100, 2),
        "initial_revenue_usd": initial_revenue,
        "ending_revenue_usd": ending_revenue,
        "years": years,
        "projected_annual_ebitda_usd": round(projected_ebitda, 2),
        "status": "Healthy enterprise growth trajectory" if cagr > 0.15 else "Moderate growth",
    }


class SqlQueryArgs(BaseModel):
    query: str = Field(..., description="Read-only SQL query to execute against analytical data lake")


@tool(
    name="query_analytical_warehouse",
    description="Executes a sanitized, read-only analytical query to fetch customer cohorts or ARR metrics.",
    args_schema=SqlQueryArgs
)
def query_analytical_warehouse(query: str):
    clean = query.strip().upper()
    if any(keyword in clean for keyword in ("DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE")):
        return {"error": "Security Alert: Mutation queries are strictly forbidden in read-only warehouse."}
    
    # Realistic analytical warehouse simulation
    return {
        "columns": ["tenant_id", "tier", "arr_usd", "retention_rate", "active_seats"],
        "rows": [
            ["org_acme_global", "Enterprise", 450000.00, 0.98, 1250],
            ["org_globex_corp", "Pro", 125000.00, 0.94, 380],
            ["org_apex_logistics", "Enterprise", 310000.00, 0.99, 890],
        ],
        "executed_query": query,
        "row_count": 3,
        "latency_ms": 14.2,
    }


def create_default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(calculate_financial_metrics)
    registry.register(query_analytical_warehouse)
    return registry
