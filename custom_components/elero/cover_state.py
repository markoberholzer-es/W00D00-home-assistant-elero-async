"""
Cover state data structures and mapping logic for Elero integration.
"""

from dataclasses import dataclass

from homeassistant.components.cover import CoverState
from homeassistant.const import STATE_UNKNOWN

from custom_components.elero.const import (
    POSITION_CLOSED,
    POSITION_INTERMEDIATE,
    POSITION_OPEN,
    POSITION_TILT_VENTILATION,
    POSITION_UNDEFINED,
    STATE_INTERMEDIATE,
    STATE_STOPPED,
    STATE_TILT_VENTILATION,
)
from custom_components.elero.response.response_status import ResponseStatus


@dataclass
class CoverStateData:
    """Data class for storing the state of a cover device.

    Attributes:
        closed (bool | None): Whether the cover is closed.
        is_closing (bool | None): Whether the cover is currently closing.
        is_opening (bool | None): Whether the cover is currently opening.
        state (str): The current state string (e.g., open, closed, intermediate).
        cover_position (int | None): The current position of the cover.
        tilt_position (int | None): The current tilt position of the cover.
    """

    closed: bool | None
    is_closing: bool | None
    is_opening: bool | None
    state: str
    cover_position: int | None
    tilt_position: int | None

    @staticmethod
    def get_for(status: ResponseStatus) -> "CoverStateData":
        """Map a ResponseStatus to a CoverStateData instance.

        Args:
            status (ResponseStatus): The status reported by the Elero transmitter.

        Returns:
            CoverStateData: The mapped state data for the given status.
        """

        known_status: set[ResponseStatus] = {
            # stationary
            ResponseStatus.TOP,
            ResponseStatus.BOTTOM,
            ResponseStatus.INTERMEDIATE,
            ResponseStatus.VENTILATION,
            ResponseStatus.STOPPED,
            ResponseStatus.BOTTOM_INTERMEDIATE,
            ResponseStatus.TOP_TILT,
            # moving
            ResponseStatus.START_MOVE_DOWN,
            ResponseStatus.MOVING_DOWN,
            ResponseStatus.START_MOVE_UP,
            ResponseStatus.MOVING_UP,
        }

        # Unknown/unhandled: return a sparse/unknown structure immediately
        if status not in known_status:
            return CoverStateData(
                closed=None,
                is_closing=None,
                is_opening=None,
                state=STATE_UNKNOWN,
                cover_position=None,
                tilt_position=None,
            )

        # Base defaults for all known statuses (prevents stale flags/positions)
        cover_state = CoverStateData(
            closed=False,
            is_closing=False,
            is_opening=False,
            state=STATE_UNKNOWN,
            cover_position=POSITION_UNDEFINED,
            tilt_position=POSITION_UNDEFINED,
        )

        match status:
            case ResponseStatus.TOP:
                cover_state.state = CoverState.OPEN
                cover_state.cover_position = POSITION_OPEN

            case ResponseStatus.BOTTOM:
                cover_state.closed = True
                cover_state.state = CoverState.CLOSED
                cover_state.cover_position = POSITION_CLOSED

            case ResponseStatus.INTERMEDIATE:
                cover_state.state = STATE_INTERMEDIATE
                cover_state.cover_position = POSITION_INTERMEDIATE
                cover_state.tilt_position = POSITION_INTERMEDIATE

            case ResponseStatus.VENTILATION | ResponseStatus.TOP_TILT:
                cover_state.state = STATE_TILT_VENTILATION
                cover_state.cover_position = POSITION_TILT_VENTILATION
                cover_state.tilt_position = POSITION_TILT_VENTILATION

            case ResponseStatus.START_MOVE_UP | ResponseStatus.MOVING_UP:
                cover_state.is_opening = True
                cover_state.state = CoverState.OPENING

            case ResponseStatus.START_MOVE_DOWN | ResponseStatus.MOVING_DOWN:
                cover_state.is_closing = True
                cover_state.state = CoverState.CLOSING

            case ResponseStatus.STOPPED:
                cover_state.state = STATE_STOPPED

            case ResponseStatus.BOTTOM_INTERMEDIATE:
                cover_state.closed = True
                cover_state.state = STATE_INTERMEDIATE
                cover_state.cover_position = POSITION_INTERMEDIATE
                cover_state.tilt_position = POSITION_INTERMEDIATE

            case _:
                # Nothing to do — base defaults already set
                pass

        return cover_state
