"""Command object representing a single operation for the Elero transmitter.

This module defines :class:`Command`, a lightweight container that describes a
single queued operation (type, target channels, priority) and its serialized
packet. It also carries a Future so callers can await processing results.

Priority handling:
    Higher numeric values indicate higher priority. The queue implementation
    compares commands using ``__lt__`` such that a command with a **higher**
    priority value is considered "less" (i.e., pops first from a min-heap).
"""

import asyncio
from asyncio import Future

from custom_components.elero.command.command_packet import CommandPacket
from custom_components.elero.command.command_type import CommandType
from custom_components.elero.command.command_util import CommandUtil
from custom_components.elero.response.response_status import ResponseStatus


class Command:
    """Represents a command to be sent to the Elero transmitter.

    Encapsulates the command type, channel targets, execution priority, the
    serialized packet to transmit, and a future for reporting results.

    Class Attributes:
        COMMAND_STOP_PRIORITY (int): Recommended priority for STOP commands.
        COMMAND_PRIORITY (int): Default priority for standard movement commands.
        FAST_INFO_PRIORITY (int): Priority for burst/fast info commands.
        INFO_PRIORITY (int): Baseline priority for info/telemetry.
    """

    # Class representing a Command
    COMMAND_STOP_PRIORITY = 30
    COMMAND_PRIORITY = 20
    FAST_INFO_PRIORITY = 10
    INFO_PRIORITY = 0

    def __init__(self, command_type: CommandType, *channel_ids: int, priority: int):
        """Initialize a new :class:`Command` instance.

        Args:
            command_type: The type of command to perform.
            *channel_ids: One or more 1-based channel identifiers.
            priority: Numeric priority; higher numbers are processed sooner.
                If ``None``, defaults to :data:`Command.INFO_PRIORITY`.
        """
        self._channel_ids = channel_ids
        self._command_type: CommandType = command_type
        self._priority: int = (
            priority if priority is not None else Command.INFO_PRIORITY
        )
        self._packet = CommandUtil.create_packet(command_type, *channel_ids)
        self._future: Future[dict[int, ResponseStatus | None] | None] = asyncio.Future()

    def __str__(self) -> str:
        """Human-readable representation including type, channels, and priority."""
        return (
            f"Command {self._command_type.name} on channels {self._channel_ids} "
            f"with priority {self._priority}"
        )

    def get_priority(self) -> int:
        """Return the command's priority (higher means sooner)."""
        return self._priority

    def get_channel_ids(self) -> tuple[int, ...]:
        """Return the tuple of 1-based channel IDs for this command."""
        return self._channel_ids

    def get_command_type(self) -> CommandType:
        """Return the :class:`CommandType` of this command."""
        return self._command_type

    def get_package(self) -> CommandPacket:
        """Return the serialized :class:`CommandPacket` for transmission."""
        return self._packet

    def get_future(self) -> Future[dict[int, ResponseStatus | None] | None]:
        """Return the future associated with this command's processing.

        The future allows the caller to observe the processing outcome. Typical
        results may be a mapping from channel ID to :class:`ResponseStatus`, but
        the exact result shape is determined by the processing code.
        """
        return self._future

    def get_response_length(self) -> int:
        """Return the expected response length for this command type.

        Returns:
            int: ``6`` for ``CommandType.CHECK`` commands, otherwise ``7``.
        """
        if self._command_type == CommandType.CHECK:
            return 6
        
        return 7

    def __lt__(self, other: "Command") -> bool:
        """Define heap ordering so higher priority pops first from a min-heap."""
        return self._priority > other.get_priority()  # higher number = higher priority
