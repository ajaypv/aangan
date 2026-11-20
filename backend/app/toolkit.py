"""Tool definition and execution. Every tool call is logged to the state's event feed with its agent name."""

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable


class ToolError(Exception):
    """Raise from a tool to report a recoverable failure (shown as FAILED in the UI)."""


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict  # JSON Schema, root type "object" (used for LLM tool calling)
    fn: Callable[..., dict]  # fn(state, **args) -> JSON-serialisable dict
    stage: str = "action"  # which stage indicator this tool lights up: action | after

    def schema(self) -> dict:
        return {"name": self.name, "description": self.description, "input_schema": self.parameters}


def run_tool(state, agent: str, tool: Tool, args: dict[str, Any], latency: float = 0.0) -> tuple[str, dict]:
    state.stage = tool.stage
    start = time.perf_counter()
    if latency:
        time.sleep(latency)
    try:
        result, status = tool.fn(state, **args), "ok"
    except ToolError as exc:
        result, status = {"error": str(exc)}, "error"
    state.log(agent, tool.name, args, status, result, int((time.perf_counter() - start) * 1000))
    return status, result


def run_parallel(state, agent: str, calls: list[tuple[Tool, dict]]) -> list[tuple[str, dict]]:
    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        futures = [pool.submit(run_tool, state, agent, tool, args) for tool, args in calls]
        return [f.result() for f in futures]
