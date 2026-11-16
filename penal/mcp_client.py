import json
import os
import sys
from contextlib import asynccontextmanager
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from penal.config import ROOT


@asynccontextmanager
async def connect_mcp():
    parameters = StdioServerParameters(command=sys.executable, args=["-m", "penal.mcp_server"], cwd=str(ROOT),
                                      env={**os.environ, "PYTHONUTF8": "1", "ANONYMIZED_TELEMETRY": "False"})
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=180)) as session:
            await session.initialize()
            yield session


async def call_tool(session, name: str, arguments: dict) -> dict:
    if name not in {"search_knowledge", "get_document", "list_topics"}:
        raise ValueError("Ferramenta não permitida.")
    result = await session.call_tool(name, arguments)
    if result.isError:
        raise ValueError("; ".join(c.text for c in result.content if c.type == "text"))
    if result.structuredContent is not None:
        return result.structuredContent
    return json.loads(next(c.text for c in result.content if c.type == "text"))
