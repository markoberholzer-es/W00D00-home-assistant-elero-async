"""Command type definitions for Elero integration.

This module defines the :class:`CommandType` enumeration, which represents
the different types of commands that can be sent to Elero devices.

Each command type corresponds to a specific action or request, such as moving
a shade up or down, stopping movement, or requesting status information.

Typical usage example::

    from command_type import CommandType

    if cmd_type == CommandType.UP:
        # Handle upward movement
        ...

"""

from enum import Enum


class CommandType(Enum):
    """Enumeration of supported Elero command types.

    Members:
        UP (int): Move the device upward.
        INTERMEDIATE (int): Move to an intermediate position.
        VENTILATION (int): Move to a ventilation position.
        DOWN (int): Move the device downward.
        STOP (int): Stop any ongoing movement.
        INFO (int): Request status or information from the device.
        CHECK (int): Perform a check or validation command.
        NONE (int): Represents no operation or an undefined command.
    """

    UP = 1
    INTERMEDIATE = 2
    VENTILATION = 3
    DOWN = 4
    STOP = 5
    INFO = 6
    CHECK = 7
    NONE = 8
