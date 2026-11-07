from typing import Any

from pydantic import BaseModel


def to_strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """JSON Schema compatível com Structured Outputs (strict): todos os campos
    obrigatórios, additionalProperties=false, sem title/default."""
    schema = model.model_json_schema()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            node.pop("title", None)
            node.pop("default", None)
            if node.get("type") == "object" or "properties" in node:
                props = node.get("properties", {})
                node["additionalProperties"] = False
                node["required"] = list(props)
            for key, value in node.items():
                if key in ("properties", "$defs"):
                    for child in value.values():
                        walk(child)
                else:
                    walk(value)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(schema)
    return schema
