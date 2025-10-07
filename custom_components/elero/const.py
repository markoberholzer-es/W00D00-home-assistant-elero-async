"""Constants for the Nikobus integration."""

from typing import Final
from datetime import timedelta
import serial

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntityFeature,
)

# =============================================================================
# General
# =============================================================================
DOMAIN: Final[str] = "elero"
BRAND: Final[str] = "elero GmbH"
PRODUCT = "Transmitter Stick"


# =============================================================================
# Serial Connection
# =============================================================================
BAUD_RATE: Final[int] = 38400
BYTE_SIZE: Final[int] = serial.EIGHTBITS
PARITY: Final[str] = serial.PARITY_NONE
STOP_BITS: Final[int] = serial.STOPBITS_ONE
SERIAL_TIMEOUT: Final[float] = 20
COMMAND_TIMEOUT: Final[float] = 5

# =============================================================================
# Coordinator Update
# =============================================================================
REGULAR_INTERVAL = timedelta(seconds=30)
FAST_INTERVAL = timedelta(seconds=2)

# =============================================================================
# Elero states that are exposed by HA Covers
# =============================================================================
STATE_INTERMEDIATE = "intermediate"
STATE_STOPPED = "stopped"
STATE_TILT_VENTILATION = "ventilation_tilt"
STATE_UNDEFINED = "undefined"

# =============================================================================
# Custom Attributes
# =============================================================================
ATTR_REQUEST_POSITION = "request_position"

# =============================================================================
# Elero Supported Positions
# =============================================================================
POSITION_CLOSED = 0
POSITION_INTERMEDIATE = 75
POSITION_OPEN = 100
POSITION_TILT_VENTILATION = 25
POSITION_UNDEFINED = 50


# =============================================================================
# Elero Supported Positions
# =============================================================================
CONF_SERIAL_NUMBER: Final = "serial_number"
CONF_BAUD_RATE: Final = "baud_rate"
CONF_BYTE_SIZE: Final = "byte_size"
CONF_PARITY: Final = "parity"
CONF_STOP_BITS: Final = "stop_bits"

# =============================================================================
# Elero Supported Device Classes
# =============================================================================
ELERO_COVER_DEVICE_CLASSES: dict[str, CoverDeviceClass] = {
    "blind": CoverDeviceClass.BLIND,
    "shade": CoverDeviceClass.SHADE,
    "shutter": CoverDeviceClass.SHUTTER,
}

# =============================================================================
# Elero Supported Features
# =============================================================================
# Supported features.
SUPPORTED_FEATURES = {
    "up": CoverEntityFeature.OPEN,
    "down": CoverEntityFeature.CLOSE,
    "stop": CoverEntityFeature.STOP,
    "open_tilt": CoverEntityFeature.OPEN_TILT,
    "close_tilt": CoverEntityFeature.CLOSE_TILT,
}
