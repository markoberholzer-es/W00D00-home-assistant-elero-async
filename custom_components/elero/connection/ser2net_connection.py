"""Asynchronous ser2net (TCP) connection for Elero devices.

This module implements :class:`Ser2NetConnection`, a :class:`Connection`
subclass that connects to a remote serial bridge (ser2net/RFC2217). It creates
and configures a non-blocking TCP socket (e.g., enabling ``TCP_NODELAY`` and
``SO_KEEPALIVE``), performs the connection using ``loop.sock_connect`` and then
wraps the socket with ``asyncio.open_connection`` to obtain reader/writer
streams.

Only docstrings were added; functional behavior is unchanged.
"""

import asyncio
import logging
import socket
from urllib.parse import urlparse

from custom_components.elero.connection.config import Ser2NetConfig
from custom_components.elero.connection.connection import Connection

_LOGGER = logging.getLogger(__name__)


class Ser2NetConnection(Connection):
    """Connection class for Elero devices over Ser2Net (TCP/IP serial bridge)."""

    # Class managing an asynchronous TCP connection via ser2net.

    def __init__(self, ser2net_config: Ser2NetConfig) -> None:
        """Create a TCP connection to a ser2net endpoint.

        Args:
            ser2net_config: Configuration containing the ``address`` in the
                form ``host:port`` used to build the target URL.
        """
        super().__init__(ser2net_config.address)
        self._address = ser2net_config.address
        self._url = f"socket://{ser2net_config.address}"
        self._writer = None
        self._reader = None

    async def open_connection(self) -> None:
        """Open the ser2net TCP connection and prepare reader/writer streams.

        Uses a pre-created non-blocking socket to set desired TCP options, then
        connects via ``loop.sock_connect`` and wraps it with
        ``asyncio.open_connection``.
        """
        if not self.is_open():
            _LOGGER.debug("Opening Ser2Net connection to %s", self._url)
            try:
                parsed = urlparse(self._url)
                host = parsed.hostname
                port = parsed.port
                # Precreate socket to apply options, then explicitly connect it
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.setblocking(False)
                try:
                    # Flush small telegrams immediately
                    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                except OSError:
                    pass
                try:
                    # Keepalives to detect half-open sessions
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                except OSError:
                    pass
                loop = asyncio.get_running_loop()
                await loop.sock_connect(
                    sock, (host, port)
                )  # <-- crucial: actually connect
                reader, writer = await asyncio.open_connection(sock=sock)
                self._reader = reader
                self._writer = writer
                _LOGGER.debug("Ser2Net connection to %s:%s opened.", host, port)
            except (OSError, ValueError) as ex:
                await self.close()
                _LOGGER.error(
                    "Failed to open Ser2Net connection to %s: %s", self._url, ex
                )
                raise

    @staticmethod
    def is_valid_url(url: str) -> bool:
        """Return ``True`` if ``url`` is a valid ser2net-style address.

        A valid URL uses one of the schemes ``tcp``, ``telnet``, or ``rfc2217``,
        and has both a hostname and a port.
        """
        parsed = urlparse(url)
        if (
            parsed.scheme in ("tcp", "telnet", "rfc2217")
            and parsed.hostname
            and parsed.port
        ):
            return True
        return False
