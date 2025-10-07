"""Module for connection configurations."""

from dataclasses import dataclass
import serial

@dataclass
class Config:
    """Base Config class."""

    serial_number: str


@dataclass
class SerialConfig(Config):
    """Configuration for serial connection."""

    device: str
    baudrate: int = 38400
    bytesize: int = serial.EIGHTBITS
    parity: str = serial.PARITY_NONE
    stopbits: int = serial.STOPBITS_ONE


@dataclass
class Ser2NetConfig(Config):
    """Configuration for ser2Net connection."""

    address: str

@dataclass
class CommandConfig():
    """Configuration for command settings."""

    timeout: float | None
