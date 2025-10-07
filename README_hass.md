---
layout: page
title: "Elero Cover"
description: "Instructions on how to integrate Elero covers into Home Assistant."
date: 2025-10-15 10:00
sidebar: true
comments: false
sharing: true
footer: true
logo: elero.png
ha_category: Cover
ha_release: 0.9x
---


This `elero` platform allows you to control different [Elero](https://www.elero.com) components/devices (such as venetian blinds, a roller shutters, tubular motors, electrical devices, rolling door drives, etc.).


## {% linkable_title Prerequisite %}

The Elero Transmitter Stick is a 15-channel handheld radio transmitter for bidirectional communication between transmitter and receiver(s).

To use the receiver control of the Home Assistant, at least one receiver must be taught-in into the Elero Transmitter Stick. For further details of the learning procedure please visit the [Elero's Downloads webpage](https://www.elero.com/en/downloads-service/downloads/) and find the [Centero Operation instruction](https://www.elero.com/en/downloads-service/downloads/?tx_avelero_downloads%5Bdownload%5D=319&tx_avelero_downloads%5Baction%5D=download&cHash=5cf4212966ff0d58470d8cc9aa029066)


## {% linkable_title Elero features %}

The Elero Transmitter stick supports the following Elero device features:
- up
- down
- stop
- tilt
    - open (intermediate position)
    - close (ventilation / turning position)
    - stop


## {% linkable_title Configuration %}
You can use as many **Elero USB Transmitter Sticks** as needed to control more than 15 devices. Each stick is **automatically discovered** by Home Assistant when connected to a USB port, so in most cases, no manual configuration is required.

> **Note:** The transmitter is configured exclusively through the **Home Assistant UI**. Automatic discovery handles the setup by default.

The setup process guides through all configured channels of the attached transmitter, where the device class and the supported features of a given channel can be configured.

## {% linkable_title Configuration of the Elero cover component %}

To create `Cover Groups` in your installation, add the following to your `configuration.yaml` file:

```yaml
# Example configuration.yaml entry
  - platform: group
    name: <name of your cover group>
    entities:
      - cover.<name of your cover device>
```


{% Example configuration: %}

```yaml
# Example configuration.yaml entry
cover:
  - platform: elero
    covers:
      bathroom_small:
        name: Shower
        serial_number: 00000000
        channel: 1
        device_class: window # shutter
      guestroom:
        name: Guest room
        serial_number: 00000000
        channel: 2
        device_class: window # shutter
      childrenroom:
        name: George
        serial_number: 00000000
        channel: 3
        device_class: window # blind
      bathroom_big:
        name: Bathroom
        channel: 4
        device_class: window # blind
  - platform: group
    name: Shutters
    entities:
      - cover.shower
      - cover.guest_room
  - platform: group
    name: Blinds
    entities:
      - cover.george
      - cover.bathroom
```


## {% linkable_title Functionality %}

The supported features are `open`/`close`/`stop`.


## {% linkable_title Installation %}
Just copy the contents of the `custom_components` folder into your Home Assistant `../config/custom_components/` folder.

After a restart of your device, the integration should automatically detect any attached USB-Transmitter.
