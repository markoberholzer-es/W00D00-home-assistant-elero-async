"""High-level wrapper for an Elero Centero USB Transmitter Stick.

This module provides :class:`EleroTransmitter`, a convenience class that
coordinates a concrete connection (direct serial or ser2net TCP), an internal
:class:`~custom_components.elero.command.command_queue.CommandQueue`, and the
request/response flow for Elero ``Command`` objects.

Key responsibilities
--------------------
* Open/close the underlying transport asynchronously.
* Queue commands with priorities and process them in the background.
* Track and expose *learned channels* reported by the transmitter.
* Provide simple APIs to send movement commands and request INFO/telemetry.

Typical usage example::

    tx = EleroTransmitter(serial_config=SerialConfig(...), timeout=2.0)
    ok = await tx.async_open_serial()
    if ok:
        await tx.async_info(1, 2, 3)
        await tx.async_change_request_command(1, CommandType.UP)
        await tx.async_close()

Only documentation is added—functional behavior is unchanged.
"""

import asyncio
import logging
import time

from serial.tools import list_ports
from serial.tools.list_ports_common import ListPortInfo

from custom_components.elero.command.command import Command
from custom_components.elero.command.command_queue import CommandQueue
from custom_components.elero.command.command_type import CommandType
from custom_components.elero.connection.config import Ser2NetConfig, SerialConfig
from custom_components.elero.connection.connection import Connection
from custom_components.elero.connection.ser2net_connection import Ser2NetConnection
from custom_components.elero.connection.serial_connection import SerialConnection
from custom_components.elero.const import BRAND, PRODUCT
from custom_components.elero.response.response import Response, ResponseStatus


_LOGGER = logging.getLogger(__name__)


class EleroTransmitter:
    """Representation of an Elero Centero USB Transmitter Stick.

    This class abstracts away connection management (serial or ser2net),
    command queuing, and response handling. It also maintains a mapping of
    *learned channels*—channels that the transmitter reports as available—along
    with the most recently observed :class:`ResponseStatus` for each channel.

    Args:
        serial_config: Serial port configuration. Provide either this or
            ``ser2net_config``.
        ser2net_config: TCP bridge configuration for ser2net/RFC2217. Provide
            either this or ``serial_config``.
        timeout: Optional per-operation timeout (seconds) used when sending
            packets and waiting for responses.

    Raises:
        ValueError: If neither ``serial_config`` nor ``ser2net_config`` is
            provided.
    """

    def __init__(
        self,
        serial_config: SerialConfig | None = None,
        ser2net_config: Ser2NetConfig | None = None,
        timeout: float | None = None,
    ) -> None:
        # Setup the serial connection to the transmitter.
        self._learned_channels: dict[int, ResponseStatus | None] = {}
        self._serial_config = serial_config
        self._ser2net_config = ser2net_config
        self._serial_number: str = ""
        self._timeout = timeout

        self._connection: Connection | None
        if self._serial_config is not None:
            self._connection = SerialConnection(serial_config=self._serial_config)
            self._serial_number = self._serial_config.serial_number
        elif self._ser2net_config is not None:
            self._connection = Ser2NetConnection(ser2net_config=self._ser2net_config)
            self._serial_number = self._ser2net_config.serial_number
        else:
            raise ValueError("Either serial_config or ser2net_config must be provided.")

        self._command_queue = CommandQueue()
        self._command_queue.start(self._process_command_from_queue)

    async def _process_command_from_queue(
        self, command: Command
    ) -> dict[int, ResponseStatus | None] | None:
        """Adapter used by the background queue to process a single command.

        This forwards to :meth:`__process_command`, which performs the transport
        I/O and updates learned channel state.

        Args:
            command: The command dequeued by :class:`CommandQueue`.

        Returns:
            dict[int, ResponseStatus | None] | None: The current learned-channel
            mapping after processing, or ``None`` if the connection is missing.
        """
        return await self.__process_command(command)

    async def async_open_serial(self) -> bool:
        """Initialize the underlying connection.

        Returns ``True`` if the transport is open at the end of the call. A
        short delay is added after opening to allow the transport to settle.

        Returns:
            bool: ``True`` if open, otherwise ``False``.
        """
        if not self._connection:
            return False
        await self._connection.open_connection()
        if self._connection.is_open():
            # Small settle right after transport is up
            await asyncio.sleep(0.10)
        return self._connection.is_open()

    async def _async_close_serial(self) -> None:
        """Close the underlying transport if it is currently open."""
        if not self._connection:
            return None
        if self._connection.is_open():
            await self._connection.close()

    async def async_close(self) -> None:
        """Close the transmitter: stop the queue and close the transport."""
        await self._command_queue.close()
        await self._async_close_serial()

    def get_transmitter_state(self) -> bool:
        """Return ``True`` if a connection exists and is currently open."""
        return True if (self._connection and self._connection.is_open()) else False

    def get_serial_number(self) -> str:
        """Return the transmitter's serial number (from configuration)."""
        return self._serial_number

    async def async_check(self) -> int:
        """Query the transmitter for learned channels via ``CHECK``.

        Enqueues a high-priority :data:`CommandType.CHECK` command and waits for
        the queue to process it, which updates the internal learned-channel map.

        Returns:
            int: The number of learned channels reported by the transmitter.
        """
        cmd = Command(CommandType.CHECK, 0, priority=Command.FAST_INFO_PRIORITY)
        self._command_queue.add_command(cmd)
        await cmd.get_future()
        # return the number of learned channels
        return len(self._learned_channels)

    def __set_learned_channels(self, channels: list[int]) -> None:
        """Replace the learned-channel set while preserving prior entries.

        Any newly reported channel IDs are added; channels no longer present are
        removed. Existing per-channel status values are retained when possible.

        Args:
            channels: List of 1-based channel IDs learned from the transmitter.
        """
        for ch in channels:
            if ch not in self._learned_channels:
                self._learned_channels[ch] = None
        # Optionally, remove channels that are no longer present
        for ch in list(self._learned_channels.keys()):
            if ch not in channels:
                del self._learned_channels[ch]
        chs = " ".join(map(str, list(self._learned_channels.keys())))
        _LOGGER.debug(
            "The taught channels on the '%s' transmitter are '%s'.",
            self._serial_number,
            chs,
        )

    def get_learned_channels(self) -> list[int]:
        """Return the current list of learned (taught) channel IDs."""
        return list(self._learned_channels.keys())

    async def async_change_request_command(
        self, channel: int, command_type: CommandType
    ) -> dict[int, ResponseStatus | None] | None:
        """Send a movement command for a single channel.

        Args:
            channel: 1-based channel identifier to control.
            command_type: The desired action (e.g., ``UP``, ``DOWN``, ``STOP``).

        Returns:
            dict[int, ResponseStatus | None] | None: The updated learned-channel
            mapping once the command has been processed, or ``None`` on error.
        """
        cmd = Command(command_type, int(channel), priority=Command.COMMAND_PRIORITY)
        self._command_queue.add_command(cmd)
        return await cmd.get_future()

    async def async_info(
        self, *channel_ids: int
    ) -> dict[int, ResponseStatus | None] | None:
        """Request INFO status for one or more channels.

        The queue deduplicates INFO requests per channel set, so scheduling many
        INFO commands quickly will keep only the latest for a given set.

        Args:
            *channel_ids: One or more 1-based channel identifiers.

        Returns:
            dict[int, ResponseStatus | None] | None: The updated learned-channel
            mapping after processing, or ``None`` on error.
        """
        cmd = Command(CommandType.INFO, *channel_ids, priority=Command.INFO_PRIORITY)
        self._command_queue.add_command(cmd)
        return await cmd.get_future()

    async def __process_command(
        self, command: Command
    ) -> dict[int, ResponseStatus | None] | None:
        """Send a command packet, handle the response, and update state.

        This method converts the command into a packet, sends it via the active
        :class:`Connection`, and analyzes the time-to-response. For long
        durations (close to the response timeout) a warning is logged. The
        internal learned-channel map is updated based on the response.

        Args:
            command: The command to process.

        Returns:
            dict[int, ResponseStatus | None] | None: The learned-channel mapping
            after processing, or ``None`` if no connection is configured.
        """
        if not self._connection:
            return None

        packet = command.get_package()
        start = time.monotonic()
        rsp = await self._connection.send_packet(packet, self._timeout)
        duration = time.monotonic() - start

        if duration > (0.8 * packet.get_response_timeout()):
            _LOGGER.warning(
                "Slow response for channels %s on transmitter %s. %.1f seconds.",
                command.get_channel_ids(),
                self._serial_number,
                duration,
            )
        _LOGGER.debug(
            "Response received in %.1f seconds for channels: %s",
            duration,
            command.get_channel_ids(),
        )

        if rsp is not None:
            channels = rsp.get_channel_ids()
            if command.get_command_type() == CommandType.CHECK:
                self.__set_learned_channels(channels)
            else:
                self.__process_response(rsp)
        else:
            _LOGGER.debug(
                "No response received for command '%s' on transmitter '%s'",
                command.get_command_type(),
                self._serial_number,
            )
        return self._learned_channels

    def __process_response(self, resp: Response):
        """Update per-channel status cache from a device response."""
        for ch in resp.get_channel_ids():
            self._learned_channels[ch] = (
                resp.get_status() if ch in self._learned_channels else None
            )

    @staticmethod
    async def async_get_serial_devices(hass) -> dict[str, ListPortInfo]:
        """Return a mapping of available serial devices without blocking the loop.

        This offloads :meth:`get_serial_devices` to the executor using the
        provided Home Assistant ``hass`` instance.

        Args:
            hass: Home Assistant instance used to schedule executor work.

        Returns:
            dict[str, ListPortInfo]: Mapping of device path to port info.
        """
        return await hass.async_add_executor_job(EleroTransmitter.get_serial_devices)

    @staticmethod
    def get_serial_devices() -> dict[str, ListPortInfo]:
        """Return available Elero serial devices discovered on the host.

        Filters :func:`serial.tools.list_ports.comports` results to only include
        devices matching :data:`custom_components.elero.const.BRAND` and
        :data:`custom_components.elero.const.PRODUCT`, with a non-empty serial
        number.

        Returns:
            dict[str, ListPortInfo]: Mapping of device path to ``ListPortInfo``.
        """
        return {
            cp.device: cp
            for cp in list_ports.comports(include_links=True)
            if cp.manufacturer == BRAND and cp.product == PRODUCT and cp.serial_number
        }


class TransmitterConnectionError(Exception):
    """Exception raised for transmitter connection errors."""

    pass
