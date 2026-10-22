import inspect
from typing import Callable, Any, Dict, Type
from pydantic import BaseModel, create_model


class BaseTool:
    def __init__(self, name: str, description: str, func: Callable, args_schema: Type[BaseModel] | None = None):
        self.name = name
        self.description = description
        self.func = func
        self.args_schema = args_schema or self._infer_schema(func)

    def _infer_schema(self, func: Callable) -> Type[BaseModel]:
        sig = inspect.signature(func)
        fields = {}
        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue
            param_type = param.annotation if param.annotation != inspect.Parameter.empty else Any
            default = param.default if param.default != inspect.Parameter.empty else ...
            fields[param_name] = (param_type, default)
        return create_model(f"{self.name}_Args", **fields)

    def to_json_schema(self) -> Dict[str, Any]:
        schema = self.args_schema.model_json_schema()
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": schema.get("properties", {}),
                    "required": schema.get("required", []),
                },
            },
        }

    async def execute(self, **kwargs) -> Any:
        # Validate arguments through Pydantic
        validated = self.args_schema(**kwargs)
        if inspect.iscoroutinefunction(self.func):
            return await self.func(**validated.model_dump())
        return self.func(**validated.model_dump())


def tool(name: str | None = None, description: str | None = None, args_schema: Type[BaseModel] | None = None):
    def decorator(func: Callable):
        tool_name = name or func.__name__
        tool_desc = description or (func.__doc__.strip() if func.__doc__ else "No description provided.")
        return BaseTool(name=tool_name, description=tool_desc, func=func, args_schema=args_schema)
    return decorator
