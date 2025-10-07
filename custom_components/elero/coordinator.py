"""
Elero Data Update Coordinator for Home Assistant
"""

import asyncio
import logging
from datetime import datetime

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util.dt import now
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, CONF_TIMEOUT
from custom_components.elero.command.command_queue import CommandQueue
from custom_components.elero.const import (
    FAST_INTERVAL,
    REGULAR_INTERVAL,
    CONF_BAUD_RATE,
    CONF_BYTE_SIZE,
    CONF_STOP_BITS,
    CONF_PARITY,
)
from custom_components.elero.cover_state import CoverStateData
from custom_components.elero.response.response_status import ResponseStatus
from custom_components.elero.transmitter.transmitter import (
    EleroTransmitter,
    TransmitterConnectionError,
)
from custom_components.elero.connection.ser2net_connection import Ser2NetConnection
from custom_components.elero.connection.config import Ser2NetConfig, SerialConfig

_LOGGER = logging.getLogger(__name__)


class EleroDataUpdateCoordinator(DataUpdateCoordinator[dict[str, CoverStateData]]):
    """Coordinator for managing Elero transmitter data and periodic updates.

    Handles connection management, polling intervals, and state caching for all Elero covers.
    """

    """Elero Data Update Coordinator."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry):
        """Initialize the Elero Data Update Coordinator.

        Sets up configuration, connection parameters, and initializes the command queue and data cache.

        Args:
            hass (HomeAssistant): The Home Assistant instance.
            config_entry (ConfigEntry): The configuration entry for this integration.
        """
        self.hass = hass
        self._config_entry = config_entry
        self.unique_id = config_entry.unique_id or config_entry.entry_id
        self._address: str = self._config_entry.options.get(
            CONF_ADDRESS, self._config_entry.data.get(CONF_ADDRESS)
        )
        self._timeout: int = self._config_entry.options.get(
            CONF_TIMEOUT, self._config_entry.data.get(CONF_TIMEOUT)
        )
        self._baud_rate: int = self._config_entry.options.get(
            CONF_BAUD_RATE, self._config_entry.data.get(CONF_BAUD_RATE)
        )
        self._byte_size: int = self._config_entry.options.get(
            CONF_BYTE_SIZE, self._config_entry.data.get(CONF_BYTE_SIZE)
        )
        self._parity: str = self._config_entry.options.get(
            CONF_PARITY, self._config_entry.data.get(CONF_PARITY)
        )
        self._stop_bits: int = self._config_entry.options.get(
            CONF_STOP_BITS, self._config_entry.data.get(CONF_STOP_BITS)
        )
        self.transmitter: EleroTransmitter | None = None
        self._command_queue = CommandQueue()
        self._fast_channels: list[int] = []
        self._data_cache: dict[str, CoverStateData] = {}
        self._last_full_update: datetime | None = None

        super().__init__(
            self.hass,
            _LOGGER,
            name="Elero",
            update_method=self._async_update_data,
            update_interval=REGULAR_INTERVAL,
        )

    async def connect(self) -> None:
        """Connect to the Elero transmitter.

        Establishes a connection to the Elero transmitter using either a serial or Ser2Net configuration.
        Raises TransmitterConnectionError if the connection fails.
        """
        if Ser2NetConnection.is_valid_url(self._address):
            ser2net_config = Ser2NetConfig(
                address=self._address, serial_number=self.unique_id
            )
            transmitter = EleroTransmitter(
                serial_config=None, ser2net_config=ser2net_config, timeout=self._timeout
            )
        else:
            serial_config = SerialConfig(
                device=self._address,
                baudrate=self._baud_rate,
                bytesize=self._byte_size,
                parity=self._parity,
                stopbits=self._stop_bits,
                serial_number=self.unique_id,
            )
            transmitter = EleroTransmitter(
                serial_config=serial_config, ser2net_config=None, timeout=self._timeout
            )

        is_connected = await transmitter.async_open_serial()

        if is_connected:
            await transmitter.async_check()
            self.transmitter = transmitter
        else:
            _LOGGER.error("Failed to connect to Elero transmitter")
            raise TransmitterConnectionError("Failed to connect to Elero transmitter")

    async def disconnect(self) -> None:
        """Disconnect from the Elero transmitter.

        Closes the connection to the transmitter and cleans up resources.
        """
        if not self.transmitter:
            return None

        await self.transmitter.async_close()
        self.transmitter = None

    async def _async_update_data(self) -> dict[str, CoverStateData]:
        """Fetch the latest data from the Elero transmitter.

        Queries the transmitter for the current state of all or fast channels, updates the data cache,
        and manages polling intervals based on channel activity.

        Returns:
            dict[str, CoverStateData]: A mapping of channel identifiers to their current state data.

        Raises:
            UpdateFailed: If an error occurs while updating data from the transmitter.
        """
        if not self.transmitter:
            return {}

        try:
            data: dict[str, CoverStateData] = {}
            serial_no = self.transmitter.get_serial_number()
            channels = self.transmitter.get_learned_channels()

            should_fetch_all = (
                self._last_full_update is None
                or now() - self._last_full_update >= REGULAR_INTERVAL
                or not self._fast_channels
            )

            channels_to_fetch = channels if should_fetch_all else self._fast_channels

            info_results = await asyncio.gather(
                *(self.transmitter.async_info(channel) for channel in channels_to_fetch)
            )

            for channel, info_result in zip(channels_to_fetch, info_results):
                channel_status = (
                    info_result[channel] if info_result is not None else None
                )
                if not channel_status:
                    continue
                data[f"{serial_no}_{channel}"] = CoverStateData.get_for(channel_status)

            self._data_cache.update(data)

            # this is for safety if a channel is not removing itself from the fast channels
            if not self._moving_channels(info_results):
                for channel in self._fast_channels[:]:
                    self.unregister_fast_channel(channel)

            if should_fetch_all:
                self._last_full_update = now()

            return self._data_cache

        except Exception as err:
            raise UpdateFailed(f"Error updating Elero data: {err}") from err

    def register_fast_channel(self, channel_nr: int) -> None:
        """Register a channel for fast polling.

        Adds the channel to the list of fast channels and switches the update interval to FAST_INTERVAL.

        Args:
            channel_nr (int): The channel number to register for fast polling.
        """
        if channel_nr not in self._fast_channels:
            self._fast_channels.append(channel_nr)
            _LOGGER.debug("Channel %s registered for fast polling", channel_nr)

        if self._fast_channels:
            self._register_fast_request()

    def unregister_fast_channel(self, channel_nr: int) -> None:
        """Unregister a channel from fast polling.

        Removes the channel from the fast polling list and switches to regular polling if no fast channels remain.

        Args:
            channel_nr (int): The channel number to unregister from fast polling.
        """
        if channel_nr in self._fast_channels:
            self._fast_channels.remove(channel_nr)
            _LOGGER.debug("Channel %s removed from fast polling", channel_nr)

        if not self._fast_channels:
            self._register_regular_request()

    def _register_fast_request(self) -> None:
        """Switch the update interval to FAST_INTERVAL for rapid polling.

        Called when at least one channel requires fast updates (e.g., while moving).
        """
        if self.update_interval != FAST_INTERVAL:
            self.update_interval = FAST_INTERVAL
            _LOGGER.debug("Fast update interval set.")

    def _register_regular_request(self) -> None:
        """Switch the update interval to REGULAR_INTERVAL for normal polling.

        Called when no channels require fast updates.
        """
        if self.update_interval != REGULAR_INTERVAL:
            self.update_interval = REGULAR_INTERVAL
            _LOGGER.debug("Regular update interval set.")

    def _moving_channels(
        self, info_results: list[dict[int, ResponseStatus | None] | None]
    ) -> list[int]:
        """Check if any channel is currently moving.

        Inspects the info results to determine which channels are in a moving state.

        Args:
            info_results (list): List of info result dicts from the transmitter.

        Returns:
            list[int]: List of channel IDs that are currently moving.
        """
        moving_channels: list[int] = []

        for result in info_results:
            if result is None:
                continue
            for channel_id, status in result.items():
                if status in {
                    ResponseStatus.START_MOVE_UP,
                    ResponseStatus.START_MOVE_DOWN,
                    ResponseStatus.MOVING_UP,
                    ResponseStatus.MOVING_DOWN,
                }:
                    moving_channels.append(channel_id)

        return moving_channels

    async def async_config_entry_updated(self, entry: ConfigEntry) -> None:
        """Handle config entry or options update.

        Called when the user updates the integration's options in the Home Assistant UI.
        Updates connection parameters and reconnects if necessary.

        Args:
            entry (ConfigEntry): The updated configuration entry.
        """
        # Reload or reinitialize as needed
        new_baud_rate = entry.options.get(CONF_BAUD_RATE, self._baud_rate)
        new_stop_bits = entry.options.get(CONF_STOP_BITS, self._stop_bits)
        new_byte_size = entry.options.get(CONF_BYTE_SIZE, self._byte_size)
        new_parity = entry.options.get(CONF_PARITY, self._parity)
        new_timeout = entry.options.get(CONF_TIMEOUT, self._timeout)

        baud_rate_changed = new_baud_rate != self._baud_rate
        stop_bits_changed = new_stop_bits != self._stop_bits
        byte_size_changed = new_byte_size != self._byte_size
        parity_changed = new_parity != self._parity
        timeout_changed = new_timeout != self._timeout
        if (
            baud_rate_changed
            or stop_bits_changed
            or byte_size_changed
            or parity_changed
            or timeout_changed
        ):
            self._baud_rate = new_baud_rate
            self._stop_bits = new_stop_bits
            self._byte_size = new_byte_size
            self._parity = new_parity
            self._timeout = new_timeout
            _LOGGER.info("Elero connection settings updated via options.")

            # Reconnect if the connection string has changed
            await self.disconnect()
            await self.connect()
            # await self.async_request_refresh()

            # Restart the coordinator to apply new settings
            await self.async_refresh()
