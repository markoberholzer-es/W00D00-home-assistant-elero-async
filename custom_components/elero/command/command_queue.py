"""Command queue utilities for Elero integrations.

This module provides :class:`CommandQueue`, a small asynchronous priority queue
that coordinates the execution of Elero ``Command`` objects. It ensures that
commands are processed in priority order (via a heap) and deduplicates
``CommandType.INFO`` commands per channel so that only the most recent INFO
request for a given channel remains in the queue.

Typical usage example::

    queue = CommandQueue()

    async def process(cmd: Command):
        # Do something with the command (I/O, protocol call, etc.)
        return await some_async_handler(cmd)

    queue.start(process)
    queue.add_command(Command(...))
    ...
    await queue.close()

The queue runs a background task that continuously processes commands until
``close()`` is called. On shutdown, any pending commands receive an
``asyncio.CancelledError`` through their stored future (if present).
"""

import asyncio
import heapq
import logging

from custom_components.elero.command.command import Command
from custom_components.elero.command.command_type import CommandType

_LOGGER = logging.getLogger(__name__)


class CommandQueue:
    """Asynchronous priority queue for Elero :class:`Command` objects.

    The queue maintains a min-heap of :class:`Command` instances and processes
    them in priority order. For INFO telemetry requests, it ensures that at most
    one pending ``CommandType.INFO`` exists **per channel** at any time; when a
    new INFO command for the same set of channel IDs is enqueued, any older
    INFO command targeting the same channels is removed before the new one is
    pushed.

    Attributes:
        _queue (list[Command]): In-memory heap of pending commands.
        _queue_event (asyncio.Event): Notifies the processor that the heap has
            work available.
        _processing_task (asyncio.Task | None): Background task running the
            command-processing loop started by :meth:`start`.
    """

    def __init__(self):
        """Initialize an empty queue and supporting synchronization primitives."""
        self._queue: list[Command] = []
        self._queue_event = asyncio.Event()
        self._processing_task = None

    def start(self, process_func):
        """Start the background processing loop.

        The loop invokes ``process_func`` for each dequeued command. This
        method is idempotent—calling it multiple times will only create the
        processing task the first time.

        Args:
            process_func: An **async** callable with the signature
                ``await process_func(command: Command) -> Any`` that performs
                the actual command handling and returns an optional result.
        """
        if not self._processing_task:
            self._processing_task = asyncio.create_task(
                self._process_commands(process_func)
            )

    def add_command(self, command: Command) -> None:
        """Add a :class:`Command` to the queue.

        If ``command`` is of type ``CommandType.INFO``, the queue first removes
        any existing pending INFO command for the **same channel IDs**, keeping
        only the newest request for that channel set. All other commands are
        simply pushed onto the heap to be processed by priority.

        Args:
            command: The command instance to enqueue.
        """
        # Deduplicate INFO commands for the same channel
        if command.get_command_type() == CommandType.INFO:
            # Remove any existing INFO command for the same channel
            self._queue = [
                c
                for c in self._queue
                if not (
                    c.get_command_type() == CommandType.INFO
                    and c.get_channel_ids() == command.get_channel_ids()
                )
            ]
            heapq.heapify(self._queue)

        heapq.heappush(self._queue, command)
        self._queue_event.set()

    async def _process_commands(self, process_func):
        """Continuously process commands from the queue.

        This internal coroutine waits for the queue event, pops the next command
        by priority, and awaits ``process_func(command)``. If the command holds
        a future (e.g., created by the caller), the result or any exception is
        forwarded to that future unless it is already done.

        Args:
            process_func: An async callable invoked for each dequeued command.

        Notes:
            * The queue event is cleared whenever the heap becomes empty.
            * Exceptions raised by ``process_func`` are captured and set on the
              command's future (if present), allowing callers to observe the
              failure.
        """
        while True:
            await self._queue_event.wait()
            if not self._queue:
                self._queue_event.clear()
                continue

            command = heapq.heappop(self._queue)
            if not self._queue:
                self._queue_event.clear()

            try:
                result = await process_func(command)
                if command.get_future() and not command.get_future().done():
                    command.get_future().set_result(result)
            except Exception as exc:  # noqa: BLE001 - propagate to command future
                if command.get_future() and not command.get_future().done():
                    command.get_future().set_exception(exc)

    async def close(self) -> None:
        """Shut down the queue and cancel background processing.

        Cancels the processing task (if running) and resolves/clears any
        remaining queued commands. For each pending command that carries a
        future, the future is completed with ``asyncio.CancelledError`` so that
        callers are promptly informed of the shutdown.

        This method is safe to call multiple times.
        """
        if self._processing_task:
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass

        if self._queue:
            _LOGGER.warning(
                "Flushing %d commands from queue: %s", len(self._queue), self._queue
            )
            for cmd in self._queue:
                if cmd.get_future() and not cmd.get_future().done():
                    cmd.get_future().set_exception(
                        asyncio.CancelledError("Command queue closed")
                    )
            self._queue.clear()
