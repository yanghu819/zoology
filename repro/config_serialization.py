"""Serialize the concrete fields of nested Pydantic configuration models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, TypeAdapter


_JSON_VALUE_ADAPTER = TypeAdapter(Any)


def _dump_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return {
            name: _dump_value(getattr(value, name))
            for name in type(value).model_fields
        }
    if isinstance(value, dict):
        return {
            str(_JSON_VALUE_ADAPTER.dump_python(key, mode="json")): _dump_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_dump_value(item) for item in value]
    return _JSON_VALUE_ADAPTER.dump_python(value, mode="json")


def dump_full_config(config: BaseModel) -> dict[str, Any]:
    """Return JSON-compatible fields from every concrete nested model type."""
    if not isinstance(config, BaseModel):
        raise TypeError("config must be a Pydantic BaseModel")
    payload = _dump_value(config)
    if not isinstance(payload, dict):
        raise TypeError("serialized config must be an object")
    return payload
