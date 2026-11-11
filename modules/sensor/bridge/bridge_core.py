"""Common lifecycle for application-owned hardware bridges."""

import asyncio
from abc import ABC, abstractmethod
from typing import final


class Bridge(ABC):
    """Start once and share one shutdown operation for each instance."""

    def __init__(self) -> None:
        self._started = False
        self._quit_task: asyncio.Task[None] | None = None

    @property
    def has_buttons(self) -> bool:
        return False

    @final
    def start_coroutine(self) -> None:
        """Start once; a bridge whose shutdown has begun cannot restart."""
        if self._quit_task is not None:
            raise RuntimeError("Cannot start a bridge after shutdown has begun")
        if not self._started:
            self._start()
            self._started = True

    @final
    async def quit(self) -> None:
        """Close once, including before start, and survive caller cancellation."""
        if self._quit_task is None:
            self._quit_task = asyncio.create_task(self._quit())
        await asyncio.shield(self._quit_task)

    @abstractmethod
    def _start(self) -> None:
        """Start device-specific tasks or readers in the current event loop."""

    @abstractmethod
    async def _quit(self) -> None:
        """Release device resources and await all device-specific tasks."""
