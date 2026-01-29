[Back to hardware_installation.md](./hardware_installation.md)

# Table of Contents

Hardware installation

- [Hardware Assembly](#hardware-assembly)
  - [Displays with headers](#displays-with-headers-pitft-or-e-ink-displays)


Software installation

- [Software Installation](#software-installation)
  - [Raspberry Pi OS](#Raspberry-Pi-OS)
    - [Display](#display)
- [Quick Start](#quick-start)
  - [Run on X Window](#run-on-x-window)
  - [Run on console](#run-on-console)
- [Usage](#usage)
  - [Button](#button)
    - [Hardware button](#hardware-button)

# Hardware Assembly

## Displays with headers (PiTFT or E-ink displays)

The PiTFT is easy to get and easy to run the pizero_bikecomputer program on X Window, so it's a good idea to start with this one.

<img src="https://camo.qiitausercontent.com/2847993611146135559cd82c405bc25a7a27c789/68747470733a2f2f71696974612d696d6167652d73746f72652e73332e61702d6e6f727468656173742d312e616d617a6f6e6177732e636f6d2f302f3130303734312f37643739386365392d386237362d313862312d303963372d3835663036383930336638392e706e67" />

- top left: PiTFT 2.4
- central left: Raspberry Pi Zero WH
- central right: GPS module
- bottom left: Enviro pHAT
- bottom right: ANT+ USB dongle and micro USB OTG Adapter

First of all, connect the Enviro pHAT without the header(I2C SDA, I2C SCL, 3.3V and GND).

<img src="https://qiita-user-contents.imgix.net/https%3A%2F%2Fqiita-image-store.s3.ap-northeast-1.amazonaws.com%2F0%2F100741%2Ff632a516-466c-3ee7-c217-aed050ece23f.png?ixlib=rb-1.2.2&auto=format&gif-q=60&q=75&s=2698e3f7326f9ff9f918b724cbcb43ed" />

<img src="https://qiita-user-contents.imgix.net/https%3A%2F%2Fqiita-image-store.s3.ap-northeast-1.amazonaws.com%2F0%2F100741%2F427c55a8-9927-036f-5f4f-2ad5eb544720.png?ixlib=rb-1.2.2&auto=format&gif-q=60&q=75&s=3616e3461d34423220d117592d206ae7" />

Next, connect the PiTFT.

<img src="https://qiita-user-contents.imgix.net/https%3A%2F%2Fqiita-image-store.s3.ap-northeast-1.amazonaws.com%2F0%2F100741%2F82984a06-6b9d-8afb-3a58-4c5566dd8f3a.png?ixlib=rb-1.2.2&auto=format&gif-q=60&q=75&s=e691e95d858143339d966afe6f646c48" />

Connect the GPS module in the same way as the Enviro pHAT.

| Name | Raspberry Pi | GPS |
|:-|:-:|:-:|
| UART TX | IO8 | RX |
| UART RX | IO10 | TX |
| GND     | IO6  | GND |
| VCC     | 5V or 3.3V  | VIN(5V or 3.3V) |


Finally, fix each parts with screws.
To prevent from being disconnected by vibration, fix the USB power cable and ANT+ USB dongle to the PiTFT board with the tape.

<img src="https://qiita-user-contents.imgix.net/https%3A%2F%2Fqiita-image-store.s3.ap-northeast-1.amazonaws.com%2F0%2F100741%2F2f63cc6d-8e14-0320-3227-6e05fa8851cd.png?ixlib=rb-1.2.2&auto=format&gif-q=60&q=75&s=1999499f8315fd2656f9537bc7b6ed48" width=480 />

It is more reliable to solder the PiTFT directly to the header of Raspberry Pi Zero.

<img src="https://qiita-user-contents.imgix.net/https%3A%2F%2Fqiita-image-store.s3.ap-northeast-1.amazonaws.com%2F0%2F100741%2F5aa2428a-9252-4941-5599-a5a8038be925.png?ixlib=rb-1.2.2&auto=format&gif-q=60&q=75&s=92dba596bc8304adfeaab31528681bd8" width=480 />


# Software Installation

## Requirements

- Raspberry Pi OS Trixie or later
- Python 3.13+
- Qt 6.8+ (PyQt6 or PySide6)

## Raspberry Pi OS

### Display

#### PiTFT 2.4

Follow [official setup guide](https://learn.adafruit.com/adafruit-2-4-pitft-hat-with-resistive-touchscreen-mini-kit/overview) of Adafruit, or [my setup guide (Japanese)](https://qiita.com/hishi/items/bdd630666277e4f8162a).

Install libinput for touchscreen support:

```
$ sudo apt-get install libinput-dev libinput-tools
```


# Quick Start

## Run on X Window

### PiTFT

If you run the program from the SSH login shell, add the following environment variable.

```
export DISPLAY=:0.0
```

Then, run the program.

```
$ python3 pizero_bikecomputer.py -f
```

## Run on console

### PiTFT

First, create a udev rule for touchscreen rotation (270 degrees). You only need to do this once.

```
$ sudo nano /etc/udev/rules.d/99-pitft-touch.rules
```

Add the following line:

```
SUBSYSTEM=="input", ATTRS{name}=="stmpe-ts", ENV{LIBINPUT_CALIBRATION_MATRIX}="0 1 0 -1 0 1"
```

Apply the rule:

```
$ sudo udevadm control --reload-rules
$ sudo udevadm trigger
```

Then, run the program with the following environment variables:

```
$ export QT_QPA_PLATFORM=linuxfb:fb=/dev/fb1
$ export QT_QPA_GENERIC_PLUGINS=libinput
$ python3 pizero_bikecomputer.py
```

Note: The calibration matrix values depend on display rotation:

| Rotation | Matrix |
|:-|:-|
| 0° | `1 0 0 0 1 0` |
| 90° | `0 -1 1 1 0 0` |
| 180° | `-1 0 1 0 -1 1` |
| 270° | `0 1 0 -1 0 1` |


# Usage

## Button

### Hardware button

#### PiTFT 2.4

<img width="300" alt="pitft_button" src="https://user-images.githubusercontent.com/12926652/100878687-da579b00-34ed-11eb-987f-e15bf488f1f3.png">

From left to right, the button assignments are as follows.

| GPIO NUM | Short press | Long press |
|:-|:-|:-|
| 5 | Left (<-) | None |
| 6 | Lap | Reset |
| 12 | Screen brightness On/Off | None |
| 13 | Start/Stop | None |
| 16 | Right (->) | Menu |

In the menu, the button has different assignments. From left to right, the button assignments are as follows.

| GPIO NUM | Short press | Long press |
|:-|:-|:-|
| 5 | Back | None |
| 6 | None | None |
| 12 | Enter | None |
| 13 | Select items (Back) | None |
| 16 | Select items (Forward) | None |

Both short press and long press can be changed. And only the GPIO number of PiTFT 2.4 is supported. For other models, you need to change it in modules/config.py.


[Back to hardware_installation.md](./hardware_installation.md)
