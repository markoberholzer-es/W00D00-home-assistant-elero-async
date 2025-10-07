"""Configuration flow for the Elero Home Assistant integration.

This module implements the user and USB discovery flows for configuring the
Elero transmitter, and an options flow for adjusting serial/connection
parameters later.

Highlights
---------
* Presents available serial devices discovered on the host and prevents
  selecting addresses already configured.
* Validates connectivity (serial or ser2net) before proceeding.
* Discovers *learned channels* from the transmitter and runs a per-channel
  wizard so users can assign names, device classes, and supported features.
* Provides an options flow to adjust transport parameters and command timeout.

Only docstrings were added; functional behavior remains unchanged.
(Structure derived from the provided source file.)
"""

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_ADDRESS, CONF_NAME, CONF_TIMEOUT
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.service_info.usb import UsbServiceInfo
from homeassistant.helpers.translation import async_get_translations

from custom_components.elero.connection.config import Ser2NetConfig, SerialConfig
from custom_components.elero.connection.ser2net_connection import Ser2NetConnection
from custom_components.elero.connection.serial_connection import SerialConnection
from custom_components.elero.const import (
    BAUD_RATE,
    BYTE_SIZE,
    CONF_BAUD_RATE,
    CONF_BYTE_SIZE,
    CONF_PARITY,
    CONF_STOP_BITS,
    DOMAIN,
    ELERO_COVER_DEVICE_CLASSES,
    PARITY,
    STOP_BITS,
    SUPPORTED_FEATURES,
    COMMAND_TIMEOUT,
)
from custom_components.elero.transmitter.transmitter import EleroTransmitter

_LOGGER = logging.getLogger(__name__)

# Base schemas used to render forms. The address field is injected via
# build_data_schema to support dynamic selection and ordering.
DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME, default="Elero Transmitter"): str,
        vol.Required(CONF_ADDRESS): str,
        vol.Required(CONF_TIMEOUT, default=5): int,
        vol.Optional(CONF_BAUD_RATE, default=BAUD_RATE): int,
        vol.Optional(CONF_BYTE_SIZE, default=BYTE_SIZE): int,
        vol.Optional(CONF_PARITY, default=PARITY): str,
        vol.Optional(CONF_STOP_BITS, default=STOP_BITS): int,
    }
)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TIMEOUT, default=COMMAND_TIMEOUT): int,
        vol.Optional(CONF_BAUD_RATE, default=BAUD_RATE): int,
        vol.Optional(CONF_BYTE_SIZE, default=BYTE_SIZE): int,
        vol.Optional(CONF_PARITY, default=PARITY): str,
        vol.Optional(CONF_STOP_BITS, default=STOP_BITS): int,
    }
)


def build_data_schema(addresses: list[str], default_address: str) -> vol.Schema:
    """Build a dynamic user schema with a selectable ``CONF_ADDRESS`` field.

    This helper clones :data:`DATA_SCHEMA`, removes the existing address
    definition, and reinserts a new address field (with either a list selector
    or a plain string) in the same relative position that ``CONF_ADDRESS``
    appears in :data:`OPTIONS_SCHEMA`.

    Args:
        addresses: A list of device paths/URLs available for selection. If
            empty, the address field will accept a free-form string input.
        default_address: The initial address to preselect in the UI.

    Returns:
        vol.Schema: A new schema object suitable for the user step form.
    """
    base = dict(DATA_SCHEMA.schema)

    # Remove the old CONF_ADDRESS
    base = {
        k: v
        for k, v in base.items()
        if not (isinstance(k, vol.Marker) and k.schema == CONF_ADDRESS)
    }

    # Prepare the new CONF_ADDRESS field
    new_key = vol.Required(CONF_ADDRESS, default=default_address)
    new_value = vol.In(addresses) if addresses else str

    # Get the desired order from OPTIONS_SCHEMA
    desired_order = [k.schema for k in OPTIONS_SCHEMA.schema.keys()]

    # Insert CONF_ADDRESS at the correct position
    new_base: dict[Any, Any] = {}
    inserted = False
    for k, v in base.items():
        if not inserted and isinstance(k, vol.Marker) and k.schema in desired_order:
            # Insert CONF_ADDRESS before the first matching key from OPTIONS_SCHEMA
            new_base[new_key] = new_value
            inserted = True
        new_base[k] = v

    # If not inserted yet, append at the end
    if not inserted:
        new_base[new_key] = new_value

    return vol.Schema(new_base)


async def validate_input(user_input: dict[str, Any]) -> dict[str, str] | None:
    """Validate connectivity to the given address and return errors if any.

    Attempts to open a connection to the address provided in ``user_input``.
    If the address matches a ser2net URL, a :class:`Ser2NetConnection` is used;
    otherwise a :class:`SerialConnection` is created. On success, the connection
    is immediately closed; on failure, a translated error key is returned.

    Args:
        user_input: Mapping containing at least ``CONF_ADDRESS``.

    Returns:
        dict[str, str] | None: A dict of form errors (e.g., ``{"base":
        "connection_error"}``) or ``None`` if validation succeeded.
    """
    errors = None
    address = user_input[CONF_ADDRESS]

    conn: Ser2NetConnection | SerialConnection | None = None
    try:
        if Ser2NetConnection.is_valid_url(address):
            ser2net_config = Ser2NetConfig(address=address, serial_number="unknown")
            conn = Ser2NetConnection(ser2net_config)
        else:
            serial_config = SerialConfig(device=address, serial_number="unknown")
            conn = SerialConnection(serial_config)

        await conn.open_connection()
        # If open succeeds, try to get some info (serial, etc.)
        # For now, just return True; you can extend to actually read info if protocol allows
        await conn.close()
    except OSError:
        _LOGGER.exception("Connection error when trying to connect to Elero")
        errors = {"base": "connection_error"}

    return errors


async def get_channels(user_input: dict[str, Any]) -> list[int] | None:
    """Discover learned channels from the transmitter at ``CONF_ADDRESS``.

    Opens an :class:`EleroTransmitter` for the address and issues a ``CHECK``
    command to retrieve taught channels, then closes the connection.

    Args:
        user_input: Mapping containing at least ``CONF_ADDRESS``.

    Returns:
        list[int] | None: List of 1-based channel IDs if successful, otherwise
        ``None``.
    """
    address = user_input[CONF_ADDRESS]
    transmitter: EleroTransmitter | None = None

    if Ser2NetConnection.is_valid_url(address):
        ser2net_config = Ser2NetConfig(address=address, serial_number="unknown")
        transmitter = EleroTransmitter(
            serial_config=None, ser2net_config=ser2net_config
        )
    else:
        serial_config = SerialConfig(device=address, serial_number="unknown")
        transmitter = EleroTransmitter(serial_config=serial_config, ser2net_config=None)

    await transmitter.async_open_serial()
    await transmitter.async_check()
    channels = transmitter.get_learned_channels()
    await transmitter.async_close()

    return channels


class EleroConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the Elero initial configuration flow.

    Steps:
        * ``user`` — user picks an address (serial URL/path or ser2net URL),
          we validate connectivity, then fetch learned channels and start the
          per-channel wizard.
        * ``channels`` — repeated once per learned channel to collect channel
          name, device class, and supported features.
        * ``usb`` / ``usb_confirm`` — auto-discovered USB devices can be
          confirmed and then proceed as the manual flow.
    """

    VERSION = 1

    def __init__(self):
        self._discovered_channels: list[int] = []
        self._channels_config: list[dict] = []
        self._channel_idx: int = 0
        self._base_config: dict = {}

    async def async_step_channels(self, user_input=None):
        """Handle the per-channel configuration step.

        This collects and stores configuration for one channel at a time. When
        all channels are configured, a single config entry is created with the
        accumulated data.
        """
        _LOGGER.debug("Starting channel step with input: %s", user_input)

        channel = self._discovered_channels[self._channel_idx]

        if user_input is not None:
            # Inject the channel number into the config, since it's not user-editable
            user_input_with_channel = dict(user_input)
            user_input_with_channel["channel"] = channel
            self._channels_config.append(user_input_with_channel)
            self._channel_idx += 1
            if self._channel_idx < len(self._discovered_channels):
                return await self._show_channel_form(self._channel_idx)

            # All channels configured, create entry
            entry_data = self._base_config.copy()
            entry_data["channels"] = self._channels_config
            return self.async_create_entry(
                title=entry_data[CONF_NAME],
                data=entry_data,
            )

        # First time: show form for first channel
        return await self._show_channel_form(self._channel_idx)

    async def _show_channel_form(self, idx: int):
        """Render the per-channel form for index ``idx`` in the channel list."""
        channel = self._discovered_channels[idx]
        translations = await async_get_translations(
            hass=self.hass,
            language=self.hass.config.language,
            category="common",
            integrations=[DOMAIN],
        )
        default_channel_name = translations.get(
            f"component.{DOMAIN}.common.default_channel_name", "Channel"
        )
        return self.async_show_form(
            step_id="channels",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "name", default=default_channel_name + f" {channel}"
                    ): str,
                    vol.Required("device_class"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=list(ELERO_COVER_DEVICE_CLASSES.keys()),
                            sort=True,
                            translation_key="device_class",
                        )
                    ),
                    vol.Required(
                        "supported_features",
                        default=["up", "down", "stop"],
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=list(SUPPORTED_FEATURES.keys()),
                            multiple=True,
                            translation_key="supported_features",
                        )
                    ),
                }
            ),
            description_placeholders={"channel": str(channel)},
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial user step.

        Shows a form with available addresses, validates the input, ensures the
        unique ID is reserved (device serial when available), then discovers
        channels and enters the per-channel wizard.
        """
        # Get all available serial devices
        serial_devices = await EleroTransmitter.async_get_serial_devices(self.hass)

        # Remove addresses already configured
        configured_addresses = [
            entry.data.get(CONF_ADDRESS, "") for entry in self._async_current_entries()
        ]
        available_addresses = [
            a for a in serial_devices.keys() if a not in configured_addresses
        ]

        # Set the default address to the first available, or empty string if none
        default_address = available_addresses[0] if available_addresses else ""

        # Build the schema using the helper
        data_schema = build_data_schema(available_addresses, default_address)

        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=data_schema)

        # Check for unique address
        if user_input[CONF_ADDRESS] in configured_addresses:
            return self.async_show_form(
                step_id="user",
                data_schema=data_schema,
                errors={CONF_ADDRESS: "address_exists"},
            )

        # Try to connect and get info
        errors = await validate_input(user_input)
        if errors is not None:
            return self.async_show_form(
                step_id="user", data_schema=data_schema, errors=errors
            )

        device = user_input[CONF_ADDRESS]
        serial_device = serial_devices.get(device)
        serial_no = serial_device.serial_number if serial_device else device

        await self.async_set_unique_id(serial_no)
        self._abort_if_unique_id_configured()

        self._discovered_channels = await get_channels(user_input) or []
        self._base_config = user_input.copy()
        self._channels_config = []
        self._channel_idx = 0

        return await self.async_step_channels()

    async def async_step_usb(self, discovery_info: UsbServiceInfo) -> ConfigFlowResult:
        """Handle USB discovery of an Elero transmitter.

        Sets a nice title for the discovery tile, reserves the unique ID (serial
        number or device path), updates an existing entry if one is already
        present, and prepares base configuration for the confirm step.
        """
        # give the discovery tile rich context
        self.context["title_placeholders"] = {
            "model": "Transmitter Stick",
            "serial": (discovery_info.serial_number or discovery_info.device),
        }

        unique_id = discovery_info.serial_number or discovery_info.device
        await self.async_set_unique_id(unique_id, raise_on_progress=False)

        # If already configured, just update the device path and abort the flow
        self._abort_if_unique_id_configured(
            updates={CONF_ADDRESS: discovery_info.device}
        )

        # Stash values for the confirm step and next stages
        self._base_config = {
            CONF_NAME: "Elero Transmitter",
            CONF_ADDRESS: discovery_info.device,
            CONF_TIMEOUT: COMMAND_TIMEOUT,
            CONF_BAUD_RATE: BAUD_RATE,
            CONF_BYTE_SIZE: BYTE_SIZE,
            CONF_PARITY: PARITY,
            CONF_STOP_BITS: STOP_BITS,
        }

        # Let the user confirm before we try to talk to the device
        self._set_confirm_only()
        return self.async_show_form(step_id="usb_confirm")

    async def async_step_usb_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm USB discovery and continue like the manual flow.

        Validates connectivity using :func:`validate_input`, then discovers
        learned channels with :func:`get_channels` and proceeds to the channel
        wizard.
        """
        if user_input is None:
            return self.async_show_form(step_id="usb_confirm")

        # Validate connectivity using your existing helper
        errors = await validate_input(self._base_config)
        if errors is not None:
            # On error, abort with a generic reason the UI understands
            return self.async_abort(reason=errors.get("base", "cannot_connect"))

        # Discover learned channels and jump into your existing channel wizard
        self._discovered_channels = await get_channels(self._base_config) or []
        self._channels_config = []
        self._channel_idx = 0
        return await self.async_step_channels()

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow handler for this integration."""
        return EleroOptionsFlowHandler()


class EleroOptionsFlowHandler(OptionsFlow):
    """Handle the Elero options flow.

    Allows users to reconfigure serial transport parameters and the command
    timeout after the initial setup without removing/re-adding the integration.
    """

    async def async_step_init(self, user_input=None):
        """Present or process the options form.

        On first call, shows the options with current values populated from the
        existing config entry options (or data defaults). When submitted, stores
        the new values on the entry.
        """
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        data = self.config_entry.data

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_BAUD_RATE,
                        default=options.get(
                            CONF_BAUD_RATE, data.get(CONF_BAUD_RATE, BAUD_RATE)
                        ),
                    ): int,
                    vol.Optional(
                        CONF_BYTE_SIZE,
                        default=options.get(
                            CONF_BYTE_SIZE, data.get(CONF_BYTE_SIZE, BYTE_SIZE)
                        ),
                    ): int,
                    vol.Optional(
                        CONF_PARITY,
                        default=options.get(CONF_PARITY, data.get(CONF_PARITY, PARITY)),
                    ): str,
                    vol.Optional(
                        CONF_STOP_BITS,
                        default=options.get(
                            CONF_STOP_BITS, data.get(CONF_STOP_BITS, STOP_BITS)
                        ),
                    ): int,
                    vol.Optional(
                        CONF_TIMEOUT,
                        default=options.get(
                            CONF_TIMEOUT, data.get(CONF_TIMEOUT, COMMAND_TIMEOUT)
                        ),
                    ): int,
                }
            ),
        )
