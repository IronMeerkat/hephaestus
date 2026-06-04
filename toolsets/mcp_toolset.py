"""Generic, server-agnostic wrapper around stdio MCP servers.

Hand it a mapping shaped like ``MCP_SERVERS`` (see ``tools/load_mcps.py``) and
it gives you back a list of *synchronous* LangChain tools you can drop straight
into ``model.bind_tools(...)``. All the fiddly bits — a shared background event
loop, piping each subprocess' stderr into the hephaestus logger, and clean
shutdown — are handled for you. 🔌

Usage::

    from tools.mcp_toolset import MCPToolset

    toolset = MCPToolset({
        "firefox": {
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@mozilla/firefox-devtools-mcp-moz@latest"],
            "env": {...},
            "emoji": "🦊",  # optional; prefixes this server's stderr logs
        }
    })
    model.bind_tools(toolset.tools)
"""

import asyncio
import atexit
import contextlib
import os
import threading
from concurrent.futures import Future
from logging import getLogger
from typing import AsyncIterator, Callable, TextIO

from langchain_core.tools import BaseTool, StructuredTool
from langchain_mcp_adapters.tools import load_mcp_tools
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class MCPToolset:
    """Connects to one or more stdio MCP servers and exposes their tools.

    Every session (and the subprocess it drives) lives on a single, long-lived
    event loop running in its own daemon thread, so all tool calls share the
    exact same session regardless of which loop/thread an agent invokes them
    from. The returned tools are synchronous: calling one hops the work onto the
    background loop and blocks until it resolves.
    """

    def __init__(self, servers: dict[str, dict], *, logger_name: str = __name__):
        self._servers = servers
        self._logger = getLogger(logger_name)
        self._subprocess_logger = getLogger(f"{logger_name}.subprocess")

        # A single, long-lived event loop in its own daemon thread. 🧵
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(
            target=self._loop.run_forever,
            name="mcp-session-loop",
            daemon=True,
        )
        self._loop_thread.start()

        # Signalling between the calling thread and the session task.
        self._ready: "Future[list[BaseTool]]" = Future()
        self._shutdown_event: asyncio.Event | None = None
        self._session_future = asyncio.run_coroutine_threadsafe(
            self._session_main(), self._loop
        )

        try:
            raw_tools = self._ready.result()
        except Exception:
            self._logger.exception("Failed to start MCP session(s)")
            raise

        # Ready-to-bind, synchronous tools. ✅
        self._tools: list[BaseTool] = [self._bind_to_loop(t) for t in raw_tools]
        atexit.register(self._shutdown)

    @property
    def tools(self) -> list[BaseTool]:
        return self._tools
    
    @property
    def tools_as_dict(self) -> dict[str, BaseTool]:
        return {t.name: t for t in self._tools}

    def get_only(self, *tool_names: str) -> list[BaseTool]:
        return [self.tools_as_dict[name] for name in tool_names]

    def get_without(self, *tool_names: str) -> list[BaseTool]:
        return [t for t in self._tools if t.name not in tool_names]

    @staticmethod
    def _log_prefix(server_name: str, config: dict) -> str:
        """Emoji if one is supplied, otherwise the server name in brackets."""
        emoji = config.get("emoji")
        return emoji if emoji else f"[{server_name}]"

    def _stderr_to_logger(self, server_name: str, prefix: str) -> tuple[TextIO, Callable[[], None]]:
        """Build a real OS-pipe stderr stream that forwards each line to the logger.

        asyncio's subprocess machinery requires stderr to be a real file
        descriptor (it calls ``.fileno()``), so we can't hand it a logging
        adapter directly — that's exactly what raises
        ``io.UnsupportedOperation: fileno``. Instead we open an actual OS pipe:
        the write end becomes the subprocess' stderr, while a daemon thread
        drains the read end and routes every line through hephaestus.

        Returns the write stream (to pass as ``errlog``) and a ``stop`` callable
        that tears the pipe + reader thread down once the subprocess is gone.
        """
        read_fd, write_fd = os.pipe()
        write_stream = os.fdopen(write_fd, "w", buffering=1, encoding="utf-8")
        read_stream = os.fdopen(read_fd, "r", encoding="utf-8", errors="replace")

        def _drain() -> None:
            try:
                for line in read_stream:
                    line = line.rstrip("\n")
                    if line:
                        self._subprocess_logger.info(f"{prefix} {line}")
            except Exception:
                self._subprocess_logger.exception(
                    f"Failed while reading stderr from MCP server {server_name}"
                )
            finally:
                read_stream.close()

        thread = threading.Thread(target=_drain, name="mcp-stderr", daemon=True)
        thread.start()

        def _stop() -> None:
            # Closing the write end signals EOF so the reader thread can finish.
            try:
                write_stream.close()
            except Exception:
                self._subprocess_logger.exception(
                    f"Failed to close stderr pipe for MCP server {server_name}"
                )
            thread.join(timeout=2)

        return write_stream, _stop

    @contextlib.asynccontextmanager
    async def _open_session(self, server_name: str, config: dict) -> AsyncIterator[ClientSession]:
        """Open a stdio MCP session whose subprocess stderr is piped to the logger."""
        params = StdioServerParameters(
            command=config["command"],
            args=config.get("args", []),
            env=config.get("env"),
            cwd=config.get("cwd"),
        )
        prefix = self._log_prefix(server_name, config)
        errlog, stop = self._stderr_to_logger(server_name, prefix)
        try:
            async with (
                stdio_client(params, errlog=errlog) as (read, write),
                ClientSession(read, write) as session,
            ):
                await session.initialize()
                yield session
        finally:
            stop()

    async def _session_main(self) -> None:
        """Open every MCP session, publish the tools, then idle until shutdown.

        The whole session lifecycle (enter -> serve -> exit) lives inside this
        one task because anyio cancel scopes must be exited in the same task
        that entered them. Closing from a different task is what triggers the
        "exit cancel scope in a different task" error.
        """
        self._shutdown_event = asyncio.Event()
        try:
            async with contextlib.AsyncExitStack() as stack:
                tools: list[BaseTool] = []
                for server_name, server_config in self._servers.items():
                    session = await stack.enter_async_context(
                        self._open_session(server_name, server_config)
                    )
                    server_tools = await load_mcp_tools(session)
                    self._logger.info(
                        f"🔌 Connected MCP server {server_name} "
                        f"with {len(server_tools)} tool(s) 🛠️"
                    )
                    tools.extend(server_tools)
                self._ready.set_result(tools)
                await self._shutdown_event.wait()
                self._logger.info("👋 Shutting down MCP sessions")
        except Exception as exc:
            if not self._ready.done():
                self._ready.set_exception(exc)
            else:
                self._logger.exception("💥 MCP session task crashed")

    def _bind_to_loop(self, tool: BaseTool) -> BaseTool:
        """Wrap a tool as a synchronous tool that runs on the background loop.

        The underlying MCP stdio streams are bound to ``self._loop``; invoking
        them from any other event loop would corrupt the session. This wrapper
        hops every call back onto ``self._loop`` and blocks until it resolves,
        giving callers a plain synchronous tool to bind to a model.
        """
        original_coroutine = tool.coroutine
        loop = self._loop

        def _run(*args, **kwargs):
            future = asyncio.run_coroutine_threadsafe(
                original_coroutine(*args, **kwargs), loop
            )
            return future.result()

        return StructuredTool(
            name=tool.name,
            description=tool.description,
            args_schema=tool.args_schema,
            func=_run,
            response_format=tool.response_format,
            metadata=tool.metadata,
        )

    def _shutdown(self) -> None:
        if self._shutdown_event is None:
            return
        try:
            self._loop.call_soon_threadsafe(self._shutdown_event.set)
            self._session_future.result(timeout=10)
        except Exception:
            self._logger.exception("Error during MCP shutdown")
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
