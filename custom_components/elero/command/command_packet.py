"""Module representing a Command Packet."""


class CommandPacket:
    """Represents a command packet to be sent to the Elero transmitter.

    Handles construction, encoding, and parsing of command packets for communication with the device.
    """

    EASY_CHECK = 0x4A
    EASY_SEND = 0x4C
    EASY_INFO = 0x4E

    def __init__(self, bytes_in):
        """Initialize the CommandPacket with input bytes.

        Args:
            bytes_in (bytes or bytearray): The raw bytes to construct the packet.
        """
        self._data = bytearray(bytes_in) + bytearray([self.checksum(bytes_in)])

    def get_bytes(self) -> bytes:
        """Return the byte representation of the command packet.

        Returns:
            bytes: The complete byte sequence including checksum.
        """
        return bytes(self._data)

    def get_response_timeout(self) -> float:
        """Determine the timeout duration for awaiting a response.

        Returns:
            float: Timeout in seconds based on packet type.
        """
        if self.is_easy_check():
            return 2.0
        return 5.0

    def checksum(self, data) -> int:
        """Compute the checksum for the given data.

        Args:
            data (bytes or bytearray): The data to compute checksum for.

        Returns:
            int: The computed checksum value.
        """
        val = sum(data) % 256
        return (256 - val) % 256

    def is_easy_check(self) -> bool:
        """Check if the packet is of type EASY_CHECK.

        Returns:
            bool: True if packet is EASY_CHECK, False otherwise.
        """
        return len(self._data) > 2 and self._data[2] == self.EASY_CHECK

    def get_response_length(self) -> int:
        """Get the expected length of the response packet.

        Returns:
            int: Length of the response packet.
        """
        return 6 if self.is_easy_check() else 7

    def __str__(self) -> str:
        """Return a hexadecimal string representation of the packet.

        Returns:
            str: Hexadecimal string of the packet data.
        """
        return self._data.hex().upper()
