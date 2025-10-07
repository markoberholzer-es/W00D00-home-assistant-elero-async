"""Core connection primitives for the Elero integration.

This module defines :class:`Connection`, an abstract base class that provides a
common, asyncio-based interface for opening/closing a transport and for safely
sending a :class:`~custom_components.elero.command.command_packet.CommandPacket`
then reading/analyzing its response.

Key features
------------
* Maintains ``asyncio.StreamReader``/``StreamWriter`` references for the
  underlying transport (serial or TCP).
* Serializes I/O using an ``asyncio.Lock`` so that reads/writes do not overlap
  when multiple coroutines call :meth:`send_packet` concurrently.
* Provides robust close semantics that tolerate cancellation and connection
  errors.
* Implements a minimal parser in :meth:`_analyze_buffer` that validates length
  and checksum, and extracts either CONFIRM or ACK responses.

Subclasses must implement :meth:`open_connection` to create the reader/writer
pair (e.g., via serial or ser2net).
"""

import asyncio
import logging
from abc import ABC, abstractmethod

from custom_components.elero.command.command_packet import CommandPacket
from custom_components.elero.response.response import Response, ResponseUtil
from custom_components.elero.response.response_status import ResponseStatus

_LOGGER = logging.getLogger(__name__)


class Connection(ABC):
    """Base class for connections, providing common interface and properties.

    Args:
        port_name: A human-readable endpoint identifier (e.g., ``/dev/ttyUSB0``
            or ``host:port``) used for logging purposes.

    Attributes:
        _reader (asyncio.StreamReader | None): Stream used to read response
            bytes from the transport.
        _writer (asyncio.StreamWriter | None): Stream used to write request
            bytes to the transport.
        _port_name (str): Endpoint name used in logs.
        _lock (asyncio.Lock): Ensures that sending/reading is serialized.
    """

    def __init__(self, port_name: str) -> None:
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._port_name = port_name
        self._lock = asyncio.Lock()

    @property
    def reader(self) -> asyncio.StreamReader | None:
        """Return the current reader stream or ``None`` if not open."""
        return self._reader

    @property
    def writer(self) -> asyncio.StreamWriter | None:
        """Return the current writer stream or ``None`` if not open."""
        return self._writer

    def is_open(self) -> bool:
        """Return ``True`` if a writer is present, meaning the connection is open."""
        return self._writer is not None

    @abstractmethod
    async def open_connection(self) -> None:
        """Open the concrete transport and populate ``reader``/``writer``.

        Subclasses must establish the transport (e.g., serial or TCP) and set
        ``self._reader``/``self._writer`` accordingly.
        """

    async def close(self) -> None:
        """Close the connection and release underlying resources.

        The method is resilient to cancellation and network/OS errors. It will
        attempt to call ``writer.wait_closed()`` when available to ensure a
        clean shutdown. It is safe to call multiple times.
        """
        _LOGGER.debug("Closing serial connection to %s...", self._port_name)
        writer = self._writer
        self._writer = None
        self._reader = None
        if writer is None:
            return
        try:
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, RuntimeError):
                pass
        except (OSError, asyncio.CancelledError):
            pass

    async def send_packet(
        self, packet: CommandPacket, timeout: float | None
    ) -> Response | None:
        """Send a command packet and await its response.

        This method acquires the connection-level lock to serialize I/O, writes
        the packet, and then attempts to read and parse the expected response.

        Args:
            packet: The command to send to the transport.
            timeout: Optional timeout (seconds) applied to the write ``drain``
                and the read operation. If ``None``, the operations are awaited
                without a timeout.

        Returns:
            Response | None: A parsed :class:`Response` on success, or ``None``
            if no valid response was received before the timeout or an error
            occurred.
        """
        async with self._lock:
            await self._send(packet, timeout)
            response = await self._read(packet, timeout)
            _LOGGER.debug("Stick answered %s for packet %s.", response, packet)
            return response

    async def _send(self, packet: CommandPacket, timeout: float | None) -> None:
        """Write the packet bytes to the transport, honoring an optional timeout.

        Args:
            packet: The packet to send.
            timeout: Optional timeout (seconds) for ``StreamWriter.drain``.
        """
        if self._writer is None:
            _LOGGER.warning(
                "Skipped sending packet %s. Connection is not open.", packet
            )
            return None
        _LOGGER.debug("Sending packet: %s, bytes: %s", packet, packet.get_bytes().hex())
        try:
            self._writer.write(packet.get_bytes())
            if timeout is None:
                await self._writer.drain()
            else:
                await asyncio.wait_for(self._writer.drain(), timeout=timeout)
        except asyncio.TimeoutError as err:
            _LOGGER.error("Timeout while sending packet %s: %s", packet, err)
        except (OSError, asyncio.CancelledError, ConnectionError) as err:
            _LOGGER.error("Error while sending packet %s: %s", packet, err)

    async def _read(
        self, packet: CommandPacket, timeout: float | None
    ) -> Response | None:
        """Read and parse a response for ``packet``.

        The method reads exactly the number of bytes reported by
        ``packet.get_response_length()`` and forwards the buffer to
        :meth:`_analyze_buffer` for parsing.

        Args:
            packet: The original command packet.
            timeout: Optional timeout (seconds) applied to the read.

        Returns:
            Response | None: Parsed response if recognized and valid, otherwise
            ``None``.
        """
        if self._reader is None:
            _LOGGER.warning(
                "Skipped reading packet %s. Connection is not open.", packet
            )
            return None
        try:
            if timeout is None:
                resp = await self._reader.readexactly(packet.get_response_length())
            else:
                resp = await asyncio.wait_for(
                    self._reader.readexactly(packet.get_response_length()),
                    timeout=timeout,
                )
            return self._analyze_buffer(packet, resp)
        except asyncio.TimeoutError:
            _LOGGER.debug("Timeout waiting for response to packet %s", packet)
            return None
        except (OSError, asyncio.CancelledError, ConnectionError) as err:
            _LOGGER.error("Error reading response for packet %s: %s", packet, err)
            return None

    def _analyze_buffer(self, packet: CommandPacket, buffer: bytes) -> Response | None:
        """Analyze a raw buffer to extract a valid Easy protocol response.

        The parser searches for the sync byte ``0xAA`` and requires the next
        byte to be a length value of ``0x04`` or ``0x05``. A simple modulo-256
        checksum is validated across the candidate frame. If the type is
        ``EASY_CONFIRM``, a 6-byte frame is expected; if ``EASY_ACK``, a
        7-byte frame that includes an additional status byte is expected.

        Args:
            packet: The original request packet, used to verify the ACK matches.
            buffer: Raw bytes read from the transport.

        Returns:
            Response | None: A constructed :class:`Response` if a valid frame
            is found and (for ACK) it matches the request; otherwise ``None``.
        """
        _LOGGER.debug("Analyzing buffer: %s", buffer.hex())
        idx = 0
        while idx < len(buffer):
            # second byte should be length byte (has to be either 0x04 or 0x05)
            while idx < len(buffer) and buffer[idx] != 0xAA:
                idx += 1
            if idx >= len(buffer) - 1:
                break
            length = buffer[idx + 1]
            if length not in (4, 5):
                idx += 1
                continue
            if idx + length + 1 >= len(buffer):
                break
            resp_type = buffer[idx + 2]
            if resp_type == ResponseStatus.EASY_CONFIRM.value:
                if sum(buffer[idx : idx + 6]) % 256 == 0:
                    return ResponseUtil.create_response(
                        buffer[idx + 3], buffer[idx + 4]
                    )
            elif resp_type == ResponseStatus.EASY_ACK.value:
                if sum(buffer[idx : idx + 7]) % 256 == 0:
                    r = ResponseUtil.create_response_with_status(
                        buffer[idx + 3], buffer[idx + 4], buffer[idx + 5]
                    )
                    if r.is_response_for(packet):
                        return r
            idx += 1
        return None
