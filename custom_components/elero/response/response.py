"""Utilities for parsing and representing responses from the Elero device.

This module provides :class:`Response` (a parsed, high-level representation of
an Easy protocol frame) and :class:`ResponseUtil` (helpers for constructing
``Response`` objects and extracting channel IDs from bitmaps).

Only documentation was added; functional behavior is unchanged.
"""

from custom_components.elero.command.command_packet import CommandPacket
from custom_components.elero.response.response_status import ResponseStatus


class Response:
    """Represents a response from the Elero transmitter.

    A ``Response`` captures optional status information and the list of
    channels referenced by the frame.

    Attributes:
        status (ResponseStatus | None): Parsed status byte (for ACK frames) or
            ``None`` when the frame does not carry a status.
        channels (list[int]): Channel IDs (1-based) extracted from the frame.
    """

    # Class representing a Response from the device.

    def __init__(
        self, status: ResponseStatus | None, channels: list[int] | None = None
    ):
        self.status: ResponseStatus | None = status
        self.channels = channels if channels is not None else []

    def is_moving(self) -> bool:
        """Return ``True`` if the status indicates active motion (up or down)."""
        return self.status in (ResponseStatus.MOVING_DOWN, ResponseStatus.MOVING_UP)

    def get_channel_ids(self) -> list[int]:
        """Return the list of 1-based channel IDs carried by this response."""
        return self.channels

    def has_status(self) -> bool:
        """Return ``True`` when a status byte was present in the frame."""
        return self.status is not None

    def get_status(self) -> ResponseStatus | None:
        """Return the :class:`ResponseStatus` value, or ``None`` if absent."""
        return self.status

    def is_response_for(self, cmd: CommandPacket) -> bool:
        """Return ``True`` if this response matches the specified ``cmd``.

        The comparison checks that the response's channel set equals the channel
        set encoded in ``cmd``. ``EASY_CHECK`` packets are not expected to
        receive matching responses and always return ``False``.
        """
        if cmd is None or cmd.is_easy_check():
            return False
        cmd_bytes = cmd.get_bytes()
        cmd_channels = ResponseUtil.get_channel_ids(cmd_bytes[3], cmd_bytes[4])
        return self.channels == cmd_channels

    def __str__(self) -> str:
        """Human-readable representation with status and channel IDs."""
        return f"{self.status} for channels {self.channels}"


class ResponseUtil:
    """Helper functions to construct and interpret :class:`Response` objects."""

    @staticmethod
    def create_response(upper_channel_byte: int, lower_channel_byte: int) -> Response:
        """Create a response that carries channel IDs but no explicit status.

        Args:
            upper_channel_byte: High byte (channels 9–16) of the bitmap.
            lower_channel_byte: Low byte (channels 1–8) of the bitmap.

        Returns:
            Response: A response with ``status=None`` and decoded ``channels``.
        """
        return Response(
            status=None,
            channels=ResponseUtil.get_channel_ids(
                upper_channel_byte, lower_channel_byte
            ),
        )

    @staticmethod
    def create_response_with_status(
        upper_channel_byte: int, lower_channel_byte: int, response_type: int
    ) -> Response:
        """Create a response with a specific status and decoded channel IDs.

        Args:
            upper_channel_byte: High byte (channels 9–16) of the bitmap.
            lower_channel_byte: Low byte (channels 1–8) of the bitmap.
            response_type: Raw status byte from the ACK frame (0–255).

        Returns:
            Response: A response with the mapped :class:`ResponseStatus` and
            decoded ``channels``.
        """
        return Response(
            status=ResponseStatus.get_for(response_type),
            channels=ResponseUtil.get_channel_ids(
                upper_channel_byte, lower_channel_byte
            ),
        )

    @staticmethod
    def get_channel_ids(upper_channel_byte: int, lower_channel_byte: int) -> list[int]:
        """Decode 1-based channel IDs from a two-byte bitmap.

        The low byte encodes channels 1–8 (LSB = channel 1), and the high byte
        encodes channels 9–16 (LSB = channel 9). Bits set to 1 indicate that
        the channel is present in the response.

        Args:
            upper_channel_byte: High byte containing channels 9–16.
            lower_channel_byte: Low byte containing channels 1–8.

        Returns:
            list[int]: Channel IDs in ascending order.
        """
        result: list[int] = []
        # Lower byte: channels 1-8
        b = lower_channel_byte
        for i in range(8):
            if b & 1:
                result.append(i + 1)
            b >>= 1
        # Upper byte: channels 9-16
        b = upper_channel_byte
        for i in range(8):
            if b & 1:
                result.append(i + 9)
            b >>= 1
        return result
