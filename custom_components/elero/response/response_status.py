"""Response status codes used by the Elero Easy protocol.

This module defines :class:`ResponseStatus`, an enumeration of status/telemetry
bytes emitted by the Elero transmitter. These values may be present in ACK
frames and can be used to infer motion state, position hints, or error states
(e.g., blocking, overheated).

Only documentation was added; functional behavior is unchanged.
"""

from enum import Enum


class ResponseStatus(Enum):
    """Enumeration of possible response statuses from the Elero transmitter.

    Members below correspond to single-byte values found in Easy protocol
    responses. A subset indicates positions (e.g., ``TOP``, ``BOTTOM``), others
    indicate transitions or errors (e.g., ``MOVING_UP``, ``BLOCKING``).

    Special members:
        EASY_CONFIRM (0x4B): Indicates a 6-byte confirm frame.
        EASY_ACK (0x4D): Indicates a 7-byte acknowledge frame with status.
    """

    # Enum representing various response statuses.
    NO_INFORMATION = 0x00
    TOP = 0x01
    BOTTOM = 0x02
    INTERMEDIATE = 0x03
    VENTILATION = 0x04
    BLOCKING = 0x05
    OVERHEATED = 0x06
    TIMEOUT = 0x07
    START_MOVE_UP = 0x08
    START_MOVE_DOWN = 0x09
    MOVING_UP = 0x0A
    MOVING_DOWN = 0x0B
    STOPPED = 0x0D
    TOP_TILT = 0x0E
    BOTTOM_INTERMEDIATE = 0x0F
    SWITCHED_OFF = 0x10
    SWITCHED_ON = 0x11

    EASY_CONFIRM = 0x4B
    EASY_ACK = 0x4D

    @staticmethod
    def get_for(status_byte: int) -> "ResponseStatus | None":
        """Return the enum member matching ``status_byte``, or ``None``.

        Args:
            status_byte: Numeric byte value (0–255) extracted from a response.

        Returns:
            ResponseStatus | None: The matching enumeration value if found;
            otherwise ``None``.
        """
        # Try to match by value, fallback to None if not found
        for status in ResponseStatus:
            if status.value == status_byte:
                return status
        return None
