"""Home Assistant Elero cover platform entities.

This module wires Elero channels to Home Assistant's ``cover`` platform. It
exposes an :class:`EleroCover` entity per taught channel and provides the
standard cover commands (open/close/stop, set position, tilt presets) by
translating them to :class:`~custom_components.elero.command.command_type.CommandType`
operations issued via the integration's transmitter and coordinator.

Only documentation was added; functional behavior is unchanged.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.cover import (
    ATTR_POSITION,
    ATTR_TILT_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

import custom_components.elero as elero
from custom_components.elero.command.command_type import CommandType
from custom_components.elero.command.command_util import CommandUtil
from custom_components.elero.const import (
    ATTR_REQUEST_POSITION,
    BRAND,
    DOMAIN,
    ELERO_COVER_DEVICE_CLASSES,
    POSITION_OPEN,
    SUPPORTED_FEATURES,
)
from custom_components.elero.coordinator import EleroDataUpdateCoordinator


_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Elero cover entities for a config entry.

    Creates one :class:`EleroCover` per channel defined in the entry data and
    registers them with Home Assistant.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry created by the integration's flow. Expected to
            contain a ``channels`` list with per-channel configuration (``name``,
            ``channel``, ``device_class``, and ``supported_features`` identifiers).
        async_add_entities: Callback used to add entities to the platform.
    """
    _LOGGER.debug("Setting up entry: %s", entry.entry_id)

    coordinator: EleroDataUpdateCoordinator | None = hass.data[DOMAIN].get(
        entry.entry_id
    )
    if coordinator is None:
        _LOGGER.error("No coordinator found for entry %s", entry.entry_id)
        return

    _LOGGER.debug("Adding covers with data: %s", entry.data)

    covers: list[EleroCover] = []
    for channel_cfg in entry.data.get("channels", []):
        covers.append(
            EleroCover(
                hass,
                coordinator,
                serial_number=coordinator.unique_id,
                channel=channel_cfg["channel"],
                channel_name=channel_cfg.get("name"),
                device_class=ELERO_COVER_DEVICE_CLASSES[channel_cfg["device_class"]],
                supported_features=channel_cfg["supported_features"],
            )
        )

    _LOGGER.debug("Adding covers entities: %s", covers)
    async_add_entities(covers)


class EleroCover(CoordinatorEntity[EleroDataUpdateCoordinator], CoverEntity):
    """Representation of an Elero cover entity (one entity per channel).

    The entity is backed by a single transmitter device (shared across all
    channel entities). It subscribes to :class:`EleroDataUpdateCoordinator`
    updates and reflects derived attributes like ``is_closed`` and
    ``current_cover_position``.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: EleroDataUpdateCoordinator,
        serial_number: str,
        channel: int,
        channel_name: str | None,
        device_class: CoverDeviceClass,
        supported_features: list[str],
    ) -> None:
        """Initialize an Elero cover entity bound to a transmitter channel.

        Args:
            hass: Home Assistant instance.
            coordinator: Data update coordinator that fetches/holds channel
                state and manages fast polling during motion.
            serial_number: Transmitter serial number used for unique IDs and
                grouping entities under the same device.
            channel: 1-based Elero channel number represented by this entity.
            channel_name: Optional friendly label for the channel (used as the
                entity name); falls back to ``"Channel <n>"``.
            device_class: Home Assistant cover device class for this entity.
            supported_features: List of feature keys defined in
                :data:`SUPPORTED_FEATURES` used to compute the feature bitmask.
        """
        super().__init__(coordinator)

        # unique_id — stable & consistent (case-fold serial; add channel)
        self._attr_unique_id = f"{serial_number.lower()}_{channel}"
        self._attr_translation_key = elero.DOMAIN

        self._hass = hass
        self._transmitter = coordinator.transmitter
        self._serial_number = serial_number
        self._channel = channel
        self._request_position: int | None = None

        # Device grouping: a SINGLE transmitter device with many channel entities
        # -> identifiers must be shared across entities (use the transmitter serial)
        self._attr_device_info = DeviceInfo(
            identifiers={(elero.DOMAIN, self._serial_number)},
            manufacturer=BRAND,
            model="Transmitter Stick",
            name="Transmitter Stick",
            serial_number=self._serial_number,
        )

        # Entity name part — use the configured channel label (already localized
        # by your flow), or fall back to an English default.
        self._attr_name = channel_name or f"Channel {channel}"
        self._attr_device_class = device_class

        # Combine cover features using bitwise OR
        features = CoverEntityFeature(0)
        for f in supported_features:
            features |= SUPPORTED_FEATURES[f]
        self._attr_supported_features = features

    async def async_added_to_hass(self) -> None:
        """Handle entity addition to Home Assistant.

        Subscribes to coordinator updates and ensures the entity state is kept
        in sync after each refresh.
        """
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.async_add_listener(self._elero_update_listener)
        )

    # ---------------------------------------------------------------------
    # Standard Cover behavior
    # ---------------------------------------------------------------------
    @property
    def state(self):
        """Return the state of the cover (CoverState enum in modern HA)."""
        cover_data = self._get_cover_data()
        if not cover_data:
            return None
        return cover_data.state

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional entity attributes (integration-specific)."""
        return {ATTR_REQUEST_POSITION: self.request_cover_position}

    @property
    def request_cover_position(self) -> int | None:
        """Return the last requested absolute cover position (if any)."""
        return self._request_position

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover fully (maps to :data:`CommandType.UP`)."""
        await self._async_update_cover_cmd(CommandType.UP)

    def open_cover(self, **kwargs) -> None:
        """Compatibility wrapper that schedules :meth:`async_open_cover`."""
        asyncio.create_task(self.async_open_cover(**kwargs))

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover fully (maps to :data:`CommandType.DOWN`)."""
        await self._async_update_cover_cmd(CommandType.DOWN)

    def close_cover(self, **kwargs) -> None:
        """Compatibility wrapper that schedules :meth:`async_close_cover`."""
        asyncio.create_task(self.async_close_cover(**kwargs))

    async def async_stop_cover(self, **kwargs) -> None:
        """Stop any ongoing movement (maps to :data:`CommandType.STOP`)."""
        await self._async_update_cover_cmd(CommandType.STOP)

    async def async_cover_ventilation_tilting_position(self, **kwargs):
        """Move slats/tilt to the ventilation preset (``VENTILATION``)."""
        await self._async_update_cover_cmd(CommandType.VENTILATION)

    async def async_cover_intermediate_position(self, **kwargs) -> None:
        """Move to the intermediate preset (``INTERMEDIATE``)."""
        await self._async_update_cover_cmd(CommandType.INTERMEDIATE)

    async def async_close_cover_tilt(self, **kwargs) -> None:
        """Alias for ventilation preset for tilt-capable covers."""
        await self._async_update_cover_cmd(CommandType.VENTILATION)

    async def async_open_cover_tilt(self, **kwargs) -> None:
        """Alias for intermediate preset for tilt-capable covers."""
        await self.async_cover_intermediate_position()

    async def async_stop_cover_tilt(self, **kwargs) -> None:
        """Alias for :meth:`async_stop_cover` for tilt-capable covers."""
        await self.async_stop_cover()

    async def async_set_cover_tilt_position(self, **kwargs) -> None:
        """Approximate a tilt position using presets.

        If ``ATTR_TILT_POSITION`` is provided and below 50%, ``VENTILATION`` is
        used; above 50%, ``INTERMEDIATE`` is used. A missing value is ignored.
        """
        tilt_position: int | None = kwargs.get(ATTR_TILT_POSITION)
        if tilt_position is None:
            return
        if tilt_position < 50:
            await self._async_update_cover_cmd(CommandType.VENTILATION)
        elif tilt_position > 50:
            await self._async_update_cover_cmd(CommandType.INTERMEDIATE)

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Move the cover to an absolute position (0-100%)."""
        await self._async_update_cover(int(kwargs[ATTR_POSITION]))

    # ---------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------
    async def _async_update_cover_cmd(
        self, command_type: CommandType, req_position: int | None = None
    ) -> None:
        """Send a command and trigger a coordinator refresh.

        This issues the specified Elero command for the channel, records the
        requested position (either provided or inferred from the command type),
        flags the channel for **fast polling**, and requests an immediate
        coordinator refresh so UI reflects motion/position as soon as possible.

        Args:
            command_type: Elero command (e.g., ``UP``, ``DOWN``, ``STOP``).
            req_position: Optional absolute position to store alongside the
                command (if omitted, derived via
                :func:`CommandUtil.get_requested_position`).
        """
        if not self._transmitter:
            return
        await self._transmitter.async_change_request_command(
            self._channel, command_type
        )
        self._request_position = (
            req_position
            if req_position is not None
            else CommandUtil.get_requested_position(command_type)
        )
        self.coordinator.register_fast_channel(self._channel)
        await self.coordinator.async_request_refresh()

    async def _async_update_cover(self, position: int | None) -> None:
        """Move the cover to an absolute position.

        Determines direction based on current position and desired target, then
        dispatches the appropriate command via :meth:`_async_update_cover_cmd`.

        Args:
            position: Target position (0-100). If ``None``, defaults to
                :data:`POSITION_OPEN`.
        """
        current_pos = (
            self.current_cover_position
            if self.current_cover_position is not None
            else POSITION_OPEN
        )
        req_position = position if position is not None else POSITION_OPEN
        cmd = CommandType.UP if req_position >= current_pos else CommandType.DOWN
        await self._async_update_cover_cmd(command_type=cmd, req_position=position)

    def _data_key(self) -> str:
        """Return the key used to access this channel in coordinator data."""
        return f"{self._serial_number}_{self._channel}"

    def _get_cover_data(self):
        """Return the coordinator payload for this channel (or ``None``)."""
        data = self.coordinator.data
        if not isinstance(data, dict):
            return None
        return data.get(self._data_key())

    @callback
    def _elero_update_listener(self) -> None:
        """Refresh entity attributes from coordinator data after each update.

        Also stops fast polling once the requested position is reached to reduce
        load.
        """
        cover_data = self._get_cover_data()
        if not cover_data:
            return
        
        # Update derived attributes
        self._attr_is_closed = cover_data.closed
        self._attr_is_opening = cover_data.is_opening
        self._attr_is_closing = cover_data.is_closing
        self._attr_current_cover_position = cover_data.cover_position

        # Stop fast polling when target reached
        if self._request_position == cover_data.cover_position:
            self.coordinator.unregister_fast_channel(self._channel)

        self.async_write_ha_state()
