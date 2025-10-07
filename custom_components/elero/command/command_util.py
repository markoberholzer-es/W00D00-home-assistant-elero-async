"""Command operations and packet-construction utilities for Elero.

This module exposes :class:`CommandUtil`, a small helper that translates high-
level command intentions (e.g., ``UP``, ``DOWN``, ``INFO``) into low-level
bytes suitable for the Elero Easy protocol via :class:`CommandPacket`.

Functions include:
    * Building the 15-bit channel bitmap from 1-based channel IDs.
    * Creating protocol frames for INFO, CHECK, and SEND commands.
    * Mapping :class:`CommandType` values to their corresponding command byte.
    * Converting command types to requested position constants.

Notes:
    * The Easy protocol encodes up to 15 channels in a two-byte bitmap. This
      utility keeps only the lowest 15 bits. Channel IDs are expected to be
      in the inclusive range ``1..15``.
"""

from struct import pack

from custom_components.elero.command.command_packet import CommandPacket
from custom_components.elero.command.command_type import CommandType
from custom_components.elero.const import (
    POSITION_CLOSED,
    POSITION_INTERMEDIATE,
    POSITION_OPEN,
    POSITION_TILT_VENTILATION,
)


class CommandUtil:
    """Utility methods to create :class:`CommandPacket` frames and helpers.

    All methods are stateless and safe to call from any context.
    """

    @staticmethod
    def create_channel_bits(*channel_ids: int) -> bytes:
        """Build the two-byte channel bitmap from 1-based channel IDs.

        Each channel ID ``n`` sets bit ``(n-1)`` in the 15-bit bitmap. Only the
        lowest 15 bits are retained in the final result.

        Args:
            *channel_ids: One or more 1-based channel identifiers (``1..15``).

        Returns:
            bytes: A big-endian two-byte bitmap representing the selected
            channels (``>H`` packed unsigned short).
        """
        channels = 0
        for channel_id in channel_ids:
            channels += 1 << (channel_id - 1)
        # Only keep the lowest 15 bits (modulo 32768)
        channels = channels % 32768
        # Pack as unsigned short (2 bytes, big-endian)
        return pack(">H", channels)

    @staticmethod
    def create_packet(command_type: CommandType, *channel_ids: int) -> CommandPacket:
        """Construct a :class:`CommandPacket` for the given command and channels.

        INFO and CHECK commands have dedicated frame formats. All other command
        types produce a SEND frame with the appropriate command byte.

        Args:
            command_type: The high-level command to encode.
            *channel_ids: One or more 1-based channel identifiers.

        Returns:
            CommandPacket: The fully constructed protocol frame ready to send.

        Raises:
            ValueError: If ``command_type`` is not handled by
                :meth:`get_command_byte` for SEND frames.
        """
        if command_type == CommandType.INFO:
            channel_bits = CommandUtil.create_channel_bits(*channel_ids)
            return CommandPacket(
                [0xAA, 0x04, CommandPacket.EASY_INFO, channel_bits[0], channel_bits[1]]
            )

        if command_type == CommandType.CHECK:
            return CommandPacket([0xAA, 0x02, CommandPacket.EASY_CHECK])

        channel_bits = CommandUtil.create_channel_bits(*channel_ids)
        cmd_byte = CommandUtil.get_command_byte(command_type)
        return CommandPacket(
            [
                0xAA,
                0x05,
                CommandPacket.EASY_SEND,
                channel_bits[0],
                channel_bits[1],
                cmd_byte,
            ]
        )

    @staticmethod
    def get_command_byte(command_type: CommandType) -> int:
        """Map a :class:`CommandType` to its protocol command byte.

        Args:
            command_type: The command type to translate.

        Returns:
            int: The protocol byte associated with ``command_type``.

        Raises:
            ValueError: If ``command_type`` is not recognized for SEND frames.
        """
        if command_type == CommandType.DOWN:
            return 0x40
        elif command_type == CommandType.INTERMEDIATE:
            return 0x44
        elif command_type == CommandType.STOP:
            return 0x10
        elif command_type == CommandType.UP:
            return 0x20
        elif command_type == CommandType.VENTILATION:
            return 0x24
        raise ValueError(f"Unhandled command type {command_type}")

    @staticmethod
    def get_requested_position(command_type: CommandType) -> int | None:
        """Return the target position constant for a given command, if any.

        Args:
            command_type: The command type being requested.

        Returns:
            int | None: One of the ``POSITION_*`` constants for movement
            commands, or ``None`` for non-positional commands (e.g., STOP,
            INFO, CHECK).
        """
        if command_type == CommandType.UP:
            return POSITION_OPEN
        if command_type == CommandType.INTERMEDIATE:
            return POSITION_INTERMEDIATE
        if command_type == CommandType.VENTILATION:
            return POSITION_TILT_VENTILATION
        if command_type == CommandType.DOWN:
            return POSITION_CLOSED
        return None
