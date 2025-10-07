
> ## 🛠 Status: In Development
> This lib is currently in development. I encourage you to use it and give me your feedback, but there are things that haven't been finalized yet and you can expect some changes.



<img src="elero.png" alt="drawing" height="150"/>  <img src="home_assistant_logo.png" alt="drawing" height="150"/>



Elero Python lib to the Home Assistant home automation platform
===============================================================

[Home Assistant](https://www.home-assistant.io/) is a home automation platform running on Python 3. It is able to track and control all devices at home and offer a platform for automating control.

This `elero` platform allows you to control different [Elero](https://www.elero.com) components/devices (such as venetian blinds, a roller shutters, tubular motors, electrical devices, rolling door drives, etc.).

---

# Prerequisite

The Elero Transmitter Stick is a 15-channel handheld radio transmitter for bidirectional communication between transmitter and receiver(s).

To use the receiver control of the Home Assistant, at least one receiver must be taught-in into the Elero Transmitter Stick. For further details of the learning procedure please visit the [Elero's Downloads webpage](https://www.elero.com/en/downloads-service/downloads/) and find the [Centero Operation instruction](https://www.elero.com/en/downloads-service/downloads/?tx_avelero_downloads%5Bdownload%5D=319&tx_avelero_downloads%5Baction%5D=download&cHash=5cf4212966ff0d58470d8cc9aa029066)


# Limitations

1. According to the [documentation of the Elero USB Transmitter](https://www.elero.com/en/downloads-service/downloads/?tx_avelero_downloads%5Baction%5D=search&tx_avelero_downloads%5Blanguage%5D=0&tx_avelero_downloads%5Bquery%5D=stick&tx_avelero_downloads%5Barchive%5D=&cHash=dd3c489f199ddf8e24e38a1d897d2812), more Elero devices could be controlled at the same time with one command. However, It does not work. This causes many timing and control problems. I tried to contact with Elero via mail however the company has so far given no answer to my question about this error.


# Elero features

The Elero Transmitter stick supports the following Elero device features:
- up
- down
- stop
- intermediate position
- ventilation / turning position

---

# Configuration of Elero platform
You can use as many **Elero USB Transmitter Sticks** as needed to control more than 15 devices. Each stick is **automatically discovered** by Home Assistant when connected to a USB port, so in most cases, no manual configuration is required.

> **Note:** The transmitter is configured exclusively through the **Home Assistant UI**. Automatic discovery handles the setup by default.

The setup process guides through all configured channels of the attached transmitter, where the device class and the supported features of a given channel can be configured.

Make sure you have the logger set to the INFO level to see the log message. You can do this by adding following to the config file `configuration.yaml`:

```yaml
logger:
  default: info
```
Then you should see the following long line after a restart of HA:

```
Elero - an Elero Transmitter Stick is found on port: '<serial port>' with serial number: '<serial number>'.
```

Make sure to disable the logger config again afterwards to avoid excessive logging!

The given serial number of a transmitter should be used to match a HA channel to the transmitter in the yaml config file.


## Cover 'Position' and 'Tilt position' Sliders

Unfortunately, by default, the Position slider is not configurable on a cover so, the 'step' of the slider either. Thus, the `set_position` and the `set_tilt_position` functions are not usable. Another problem that the Elero devices are not supporting these functions.

For the Elero 'intermediate' function use the `open_tilt` HA function and the Elero 'ventilation' function use the `close_tilt` HA function.

Nevertheless, these controls are shown and useable only if the pop-up window of the given cover is open.

Alternative methods for the Elero 'intermediate' and the 'ventilation' functions:

1. [Call a Service](https://www.home-assistant.io/docs/scripts/service-calls/)

```yaml
entities:
  - name: Intermediate
    service: cover.close_cover_tilt
    service_data:
      entity_id: cover.all_cover_group
    type: call-service
  - name: Ventilation
    service: cover.open_cover_tilt
    service_data:
      entity_id: cover.all_cover_group
    type: call-service
```


2. An [`input_number`](https://www.home-assistant.io/integrations/input_number/) slider with automation.

```yaml
input_number:
    diningroom_set_position:
        name: Position
        mode: slider
        initial: 0
        min: 0
        max: 100
        step: 25

automation:
  - alias: diningroom_set_position
    trigger:
        platform: numeric_state
        entity_id: input_number.diningroom_set_position
        to: 25
    action:
        - service: cover.close_cover_tilt
          entity_id:
            - cover.diningroom

```

3. An [`input_select`](https://www.home-assistant.io/integrations/input_select/) Scene with automation.

```yaml
input_select:
    scene_diningroom:
        name: Scene
        options:
            - open
            - close
            - stop
            - intermediate
            - ventilation

automation:
  - alias: Diningroom scene
    trigger:
      platform: state
      entity_id: input_select.scene_diningroom
      to: intermediate
    action:
        - service: cover.close_cover_tilt
          entity_id:
            - cover.diningroom
```
---

## Cover groups
To create `Cover Groups` in an installation, add the following into the `configuration.yaml` file:

```yaml
# Example configuration.yaml entry
cover:
    - platform: group
      name: "All Cover"
      entities:
          - cover.shower
          - cover.george
```

---

# Installation of the lib
## Manual Installation
Just copy the contents of the `custom_components` folder into the Home Assistant `../config/custom_components/` folder.

Configurate the `/config/configuration.yaml` file and its all linked files like `covers` and `groups`, etc. Restart the Home Assistant.

## HACS Installation
You can use [HACS](https://hacs.xyz) to install the custom component. You need to add this repository https://github.com/W00D00/home-assistant-elero as a custom repository in HACS.

## Example config files
Some example files can be found in the `config` folder as a help or starting point.

---------------

# Automation

It is possible to specify triggers for automation of your covers.

```yaml
# Example automations.yaml entry
# Covers
    - alias: 'Close the covers after sunset'
      trigger:
        platform: sun
        event: sunset
        offset: '+00:30:00'
      action:
        service: cover.close_cover
        entity_id: cover.all_Cover
```
---

# Report an issue:

Please use the Github Issues section to report a problem or feature request: https://github.com/W00D00/home-assistant-elero-async/issues/new


# Known issues:

Please see the Issues section: https://github.com/W00D00/home-assistant-elero-async/issues

# Contribution:

Please, Test first!

For minor fixes and documentation, please go ahead and submit a pull request. A gentle introduction to the process can be found [here](https://www.freecodecamp.org/news/a-simple-git-guide-and-cheat-sheet-for-open-source-contributors/).

Check out the list of issues. Working on them is a great way to move the project forward.

Larger changes (rewriting parts of existing code from scratch, adding new functions) should generally be discussed by opening an issue first.

Feature branches with lots of small commits (especially titled "oops", "fix typo", "forgot to add file", etc.) should be squashed before opening a pull request. At the same time, please refrain from putting multiple unrelated changes into a single pull request.

---

**If you have any question or you have faced with trouble, do not hesitate to contact me, all comments, insight, criticism is welcomed!**

---

# Version
* 0.1.0 - October 15, 2025 - Initial release


# Remote connection

Connect the Elero component to an USB stick that is connected to a Raspberry PI

## Installation of ser2net on a Raspberry PI

```bash
sudo rpi-update

sudo apt-get install ser2net
```

ser2net version 4.3.3 will be installed and a YAML configuration will be used.


### Configuration of ser2net

Connect the Elero transmitter stick to the Raspberry PI

For finding the ID of Elero transmitter call

```bash
ls /dev/serial/by-id
``` 


Update the ser2net.yaml configuration
```
sudo nano /etc/ser2net.yaml
```

and add the following configuration to the file. Use the ID of your stick.

```yaml
connection: &con02
  accepter: tcp,20109
  enable: off
 #connector: serialdev,/dev/ttyUSB1,38400n81,local
  connector: serialdev,/dev/serial/by-id/usb-elero_GmbH_Transmitter_Stick_AU00JHUU-if00-port0,38400n81,local
  options:
    kickolduser: true
```


### Fix problems of starting ser2net service after reboot

The manually ser2net application has some problems after raspberry pi's reboot. The USB-sticks can't be hosted as TCP ports and
the `sudo service ser2net status` shows Invalid name/port.

This can be simply fixed by a manual restart of the service `sudo service ser2net restart`.


This manual restart can be automatically called using crontab.
Add the restart 30s after a reboot (Absolute paths must be set in the crontab)

```
sudo crontab -e
```
and add the following line to the file
```
@reboot /usr/bin/sleep 30 && /usr/sbin/service ser2net restart
```

### Helper tools
Helper command to show open ports: `ss -tulw`


Helper script `list_ports.py` to show information of the USB device

```python
from serial.tools import list_ports

if __name__ == "__main__":
  
  for cp in list_ports.comports():
    print(cp)
    print("Device:", cp.device)
    print("Serial Number:", cp.serial_number)
    print("Product:", cp.product)
    print("Manufacturer:", cp.manufacturer)
    print("----")
```


## Homeassistant configuration of remote transmitters

The remote transmitters can be configured by adding its address in the UI guided setup process ex. 192.168.10.29:20109. In that case the settings for the baudrate etc. can be ignored.



