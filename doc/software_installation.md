[Back to README.md](../README.md)

# Table of Contents

- [Software Installation](#software-installation)
  - [macOS or Linux](#macOS-or-Linux)
  - [Raspberry Pi OS](#Raspberry-Pi-OS)
    - [common](#common)
    - [Bluetooth and Cloud](#bluetooth-and-cloud)
    - [GPS module](#gps-module)
    - [ANT+ USB dongle](#ant-usb-dongle)
    - [Display](#display)
    - [I2C sensors](#i2c-sensors)
- [Quick Start](#quick-start)
  - [Run on Wayland / X Window](#run-on-wayland--x-window)
  - [Run in console](#run-in-console)
    - [Manual execution](#manual-execution)
    - [Run as a service](#run-as-a-service)
  - [Usage](#usage)
  - [Button](#button)
    - [Software button](#software-button)
    - [Hardware button](#hardware-button)
  - [Menu screen](#menu-screen)
    - [Sensors](#sensors)
    - [Courses](#courses)
    - [Connectivity](#connectivity)
    - [Upload Activity](#upload-activity)
    - [Map and Data](#map-and-data)
    - [Profile](#profile)
    - [System](#System)
  - [Settings](#settings)
    - [setting.conf](#settingconf)
    - [state.pickle](#statepickle)
    - [layout.yaml](#layoutyaml)
    - [map.yaml](#mapyaml)
    - [config.py](#configpy)
  - [Prepare course files and maps](#prepare-course-files-and-maps)

# Software Installation

Requires Python version 3.13 or later, Qt 6.8 or later (PyQt6 or PySide6).
Raspberry Pi OS Trixie or later. Bookworm is not supported.

## macOS or Linux

Please build a python virtual environment since the pip command is used.

```
# macOS (Homebrew)
$ brew install python pyqt
$ python3 -m venv .venv
$ source .venv/bin/activate
$ pip install -U pip setuptools
$ pip install PyQt6 numpy cython pillow pyqtgraph fitparse oyaml polyline aiohttp qasync psutil

# or Linux (Debian/Ubuntu)
$ python3 -m venv .venv
$ source .venv/bin/activate
$ pip install -U pip setuptools
$ pip install PyQt6 numpy cython pillow pyqtgraph fitparse oyaml polyline aiohttp qasync psutil
$ sudo apt install sqlite3 libsqlite3-dev

# optional: cloud upload / live track
$ pip install garminconnect requests tb-mqtt-client mmh3 timezonefinder

$ git clone https://github.com/hishizuka/pizero_bikecomputer.git
$ cd pizero_bikecomputer
```

The RDP implementation from `hishizuka/crdp` is vendored in this repository,
so no separate `crdp` installation is required.

## Raspberry Pi OS

The program works with any Raspberry Pi OS [32-bit/64-bit] * [Lite/desktop].

Execute the following commands on the Raspberry Pi immediately after installation with the Internet connection.

```
$ /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/hishizuka/pizero_bikecomputer/refs/heads/master/install.sh)"
```

This command will install following ranges and you can at a minimum run the program without sensors.

- [Common](#common)
- [Bluetooth and Cloud](#bluetooth-and-cloud)
- [GPS module](#gps-module)
- [ANT+ USB dongle](#ant-usb-dongle)
- [Display / JDI & SHARP MIP display](#jdi--sharp-mip-display)

After executing the command, reboot and resume from [Quick Start](#quick-start).
Or, if you want to use a specific display/sensor, please read the following sections carefully.

The following are the steps for manual installation.
Here is [my setup guide in Japanese](https://qiita.com/hishi/items/8bdfd9d72fa8fe2e7573).

### Common

Install in the home directory of default user "pi". Also, your Raspberry Pi is connected to internet and updated with `apt update & apt upgrade`.

```
$ cd

$ sudo apt install git cython3 cmake python3.13-venv python3-setuptools python3-numpy sqlite3 libsqlite3-dev python3-pil python3-aiohttp python3-psutil python3-pyqt6 python3-pyqt6.qtsvg qt6-svg-plugins pyqt6-dev-tools

# If there is no python virtual environment.
$ python -m venv --system-site-packages ~/.venv
$ source ~/.venv/bin/activate
$ echo "source ~/.venv/bin/activate" >> ~/.bashrc

$ pip install fitparse oyaml polyline qasync pyqtgraph

$ git clone https://github.com/hishizuka/pizero_bikecomputer.git
$ cd pizero_bikecomputer
```

The RDP implementation from `hishizuka/crdp` is vendored in this repository,
so no separate `crdp` installation is required.

### Bluetooth and Cloud

Gadgetbridge, Strava, Garmin and ThingsBoard

```
$ sudo apt install bluez-obexd
$ pip install bleak pycycling
$ pip install gadgetbridge-rpi-link
$ pip install garminconnect tb-mqtt-client mmh3 timezonefinder
```

### GPS module

`install.sh` asks which GPS path to use. Install only the packages for the
selected hardware path.

For all GPS paths:

```
$ pip install timezonefinder
$ pip uninstall -y flatbuffers
$ PIP_CONFIG_FILE=/dev/null pip install -U --no-cache-dir -i https://pypi.org/simple flatbuffers
```

#### u-blox direct UBX GPS

Use this for u-blox receivers such as MAX-M10S/N when the application talks to
the receiver directly with the UBX protocol. This path does not use `gpsd`.
Enable UART if the receiver is connected by UART, and enable I2C if the
receiver is connected by I2C.

```
$ sudo apt install python3-smbus2
$ pip install pyubx2 pyserial azarashi
```

For u-blox AssistNow Live/Predictive Orbits, add the ZTP token to
`setting.conf`. If `assistnow_token` is empty, AssistNow is skipped.

```
[GPSD_UBLOX_PARAM]
assistnow_token =
use_power_save = False
use_qzss_dcr = False
```

`use_qzss_dcr=True` is ignored when `use_power_save=True`; disable power save
when collecting QZSS DC Report messages.

#### UART GPS through GPSD

Use this for NMEA GPS receivers managed by `gpsd`. Assume Serial interface is
on and login shell is off in raspi-config and the GPS device is connected as
`/dev/ttyS0`. If the GPS device is `/dev/ttyAMA0`, modify gpsd config
file(`/etc/default/gpsd`).

```
$ sudo apt install gpsd python3-gps libffi-dev
$ sudo cp scripts/install/etc/default/gpsd /etc/default/gpsd
$ sudo systemctl enable gpsd
$ sudo systemctl enable gpsd.socket
```

Check with `cgps` or `gpsmon` command.

#### Sony CXD5610 GPS over I2C

Use this for the Sony CXD5610 I2C GPS path.

```
$ sudo apt install python3-smbus2 libgpiod3 libgpiod-dev python3-libgpiod
```


### ANT+ USB dongle

Run the `pip3` command with the virtual environment from [Common](#common)
activated.

```
$ sudo apt install python3-pip python3-usb python3-serial
$ pip3 install --ignore-installed git+https://github.com/hishizuka/openant.git
$ openant_udev_installer="$(command -v openant-install-udev)"
$ sudo "$openant_udev_installer"
$ sudo usermod -aG dialout "$USER"
```

`openant-install-udev` installs openant's udev rules. Log out and back in, or
reboot, before using ANT+ so the udev and group changes are applied.

#### Optional official ANT+ icons

Official ANT+ icon files are not distributed with this project. ANT+ Adopters
who are authorized to use them can manually download the
[ANT+ Brand Tools package](https://www.thisisant.com/developer/ant-plus/certification/#115_tab)
(login required) and place the official PNG files at:

```
img/logos/ant_plus_icon_standard.png
img/logos/ant_plus_icon_reverse.png
```

The files are excluded from Git. Their use remains subject to the ANT+ Adopter
Agreement and ANT Wireless Brand Guidelines. If either file is absent, the
application displays `(ANT+)` instead.
 

### Display

Assume SPI interface is on in raspi-config.

#### JDI & SHARP MIP display

For `MIP_*` displays there are currently three practical paths:

- legacy pigpio backend
- legacy spidev + libgpiod backend
- the newer `sharp-drm` framebuffer driver (`QT_QPA_PLATFORM=linuxfb:fb=/dev/fb1`)

`install.sh` enables SPI and installs libgpiod packages, but it does not install pigpio automatically.
If you want to keep using the legacy pigpio backend on Raspberry Pi OS Trixie, install pigpio manually:

```
$ cd
$ wget https://github.com/joan2937/pigpio/archive/master.zip
$ unzip master.zip
$ cd pigpio-master
$ make
$ sudo make install

$ sudo systemctl enable pigpiod
$ sudo systemctl start pigpiod
```

If you use the newer `sharp-drm` driver, pigpio is not needed.
In that case run the application with `QT_QPA_PLATFORM=linuxfb:fb=/dev/fb1`.

#### Display HAT Mini, Pirate Audio

```
$ pip install st7789
```

#### ST7789 Breakout

```
$ pip install st7789
```

#### PiTFT 2.4

see [hardware_installation_pitft.md](./hardware_installation_pitft.md#display)

#### E-ink Displays

##### PaPiRus ePaper / eInk Screen HAT for Raspberry Pi

Follow [official setup guide](https://github.com/PiSupply/PaPiRus)

##### DFRobot e-ink Display Module for Raspberry Pi 4B/3B+/Zero W

Follow [official setup guide](https://wiki.dfrobot.com/Raspberry_Pi_e-ink_Display_Module_SKU%3A_DFR0591) and install manually.


### I2C sensors

Assume I2C interface is on in raspi-config.

Next, install `smbus2` if not installed.

```
$ sudo apt install python3-smbus2
```

#### Main sensors (pressure, temperature, IMU and light)

Install pip packages of the sensors you own.

Here is an example.
```
$ pip install adafruit-circuitpython-bmp280
```

| Manufacturer+Sensor | Product | Recommend | additional pip package |
|:-|:-|:-|:-|
| [Bosch BMP280](https://www.adafruit.com/product/2651) | [Adafruit](https://www.adafruit.com/product/2651) | | None |
| [Bosch BMP390](https://www.adafruit.com/product/4816) | [Adafruit](https://www.adafruit.com/product/4816) | | None |
| [Bosch BMP581](https://www.sparkfun.com/products/20170) | [SparkFun](https://www.sparkfun.com/products/20170) | o | bundled Cython helper(*1) |
| [Bosch BMI270](https://www.bosch-sensortec.com/products/motion-sensors/imus/bmi270/) | | o | bundled Cython helper(*1) |
| [Bosch BMM150 (Obsolete)](https://www.bosch-sensortec.com/products/motion-sensors/magnetometers/bmm150/) | | o | bundled Cython helper(*1) |
| [Bosch BMM350](https://www.bosch-sensortec.com/products/motion-sensors/magnetometers/bmm350/) | | | bundled Cython helper(*1) |
| [Bosch BHI360 Shuttle Board 3.0](https://www.bosch-sensortec.com/en/products/smart-sensor-systems/bhi360) | | o | bundled Cython helper(*1) |
| [Bosch BHI385 Shuttle Board 3.0](https://www.bosch-sensortec.com/en/products/smart-sensor-systems/bhi385) | | o | bundled Cython helper(*1) |
| [Bosch BNO055](https://www.bosch-sensortec.com/products/smart-sensor-systems/bno055/) | [Adafruit](https://www.adafruit.com/product/4646) | | adafruit-circuitpython-bno055(*2) | 
| [MEMSIC MMC5983MA](https://www.memsic.com/magnetometer-5) | [SparkFun](https://www.sparkfun.com/products/19895) | | None |
| [STMicroelectronics LIS3MDL](https://www.st.com/en/mems-and-sensors/lis3mdl.html) | [Adafruit](https://www.adafruit.com/product/4485) | | adafruit-circuitpython-lis3mdl |
| [STMicroelectronics ISM330DHCX](https://www.st.com/en/mems-and-sensors/ism330dhcx.html) | [SparkFun](https://www.sparkfun.com/products/19895) | | adafruit-circuitpython-lsm6ds |
| [Vishay VCNL4040](https://www.vishay.com/en/product/84274/) | [Adafruit](https://www.adafruit.com/product/4161) | o | None (bundled smbus2 driver) |
| [Lite-On LTR-308ALS-01](https://optoelectronics.liteon.com/upload/download/DS86-2016-0027/LTR-308ALS-01_Final_%20DS_V2.1.PDF) | | | None (bundled smbus2 driver) |
| | [ozzmaker Berry GPS IMU v4](https://ozzmaker.com/product/berrygps-imu/) | | adafruit-circuitpython-lsm6ds adafruit-circuitpython-lis3mdl |
| | [GPS PIE](https://gps-pie.com/) | | adafruit-circuitpython-bno055(*2) |
| | [waveshare Environment Sensor HAT](https://www.waveshare.com/environment-sensor-hat.htm) | | adafruit-circuitpython-bme280 adafruit-circuitpython-icm20x adafruit-circuitpython-tsl2591 adafruit-circuitpython-ltr390 adafruit-circuitpython-sgp40 |
| (Obsolete) Bosch BMX160+BMP388 | [DFRobot](https://www.dfrobot.com/product-1928.html) | | BMX160(*3) | 
| (Obsolete) [STMicroelectronics LPS33HW](https://www.st.com/resource/en/product_presentation/Sensors2018_Water_resistant_Pressure_Sensor_LPS33HW.pdf) | [Adafruit](https://www.adafruit.com/product/4414), [Strawberry Linux](https://strawberry-linux.com/catalog/items?code=12133)| | None |
| (Obsolete) STMicroelectronics LSM6DS33 | [Adafruit](https://www.adafruit.com/product/4485) | | adafruit-circuitpython-lsm6ds |
| (Obsolete) [STMicroelectronics LSM9DS1](https://www.st.com/ja/mems-and-sensors/lsm9ds1.html) | [Adafruit](https://www.adafruit.com/product/4634) | | adafruit-circuitpython-lsm9ds1 | 
| | (Obsolete) [Pimoroni Enviro pHAT](https://learn.pimoroni.com/article/getting-started-with-enviro-phat) | | None |

BHI360 Shuttle Board 3.0 and BHI385 Shuttle Board 3.0 are handled by the same BHI3 Cython helper. The helper reads the chip ID register before loading firmware and selects the BHI360 or BHI385 build target automatically.

*1 It is also possible to use the official BOSCH C library with cython. Create a shared library with the following command and name and place it under LD_LIBRARY_PATH (e.g. /usr/local/lib).
Also, place the header files in LD_INCLUDE_PATH (/usr/local/include, etc.).

- [BMP5_SensorAPI](https://github.com/boschsensortec/BMP5_SensorAPI)
  - 
  ```
  $ gcc -shared -fPIC -O2 -o libbmp5.so bmp5.c
  $ sudo mv libbmp5.so /usr/local/lib/
  $ sudo cp bmp5.h bmp5_defs.h /usr/local/include/
  $ sudo ldconfig
  ```
- [BMI270_SensorAPI](https://github.com/boschsensortec/BMI270_SensorAPI/)
  - 
  ```
  $ gcc -shared -fPIC -O2 -o libbmi270.so bmi270.c bmi2.c
  $ sudo mv libbmi270.so /usr/local/lib/
  $ sudo cp bmi2.h bmi270.h bmi2_defs.h /usr/local/include/
  $ sudo ldconfig
  ```
- [BMM150_SensorAPI](https://github.com/boschsensortec/BMM150_SensorAPI/)
  - 
  ```
  $ gcc -shared -fPIC -O2 -o libbmm150.so bmm150.c
  $ sudo mv libbmm150.so /usr/local/lib/
  $ sudo cp bmm150.h bmm150_defs.h /usr/local/include/
  $ sudo ldconfig
  ```
- [BMM350_SensorAPI](https://github.com/boschsensortec/BMM350_SensorAPI/)
  - 
  ```
  $ gcc -shared -fPIC -O2 -o libbmm350.so bmm350.c
  $ sudo mv libbmm350.so /usr/local/lib/
  $ sudo cp bmm350.h bmm350_defs.h /usr/local/include/
  $ sudo ldconfig
  ```

- [BHI360_SensorAPI](https://github.com/boschsensortec/BHI360_SensorAPI)
  - Use v2.3.1 (latest verified on 2026-09-06). Run these commands from the SDK repository root.
  - Build the SensorAPI core used by the helper. The COINES console parser and API dispatch table are not required.
  ```
  $ git fetch --tags origin
  $ git checkout v2.3.1
  $ gcc -shared -fPIC -O2 -Wl,--no-undefined -o libbhi360.so source/bhi360.c source/bhi360_hif.c source/bhi360_*param.c source/bhi360_event_data.c source/bhi360_logbin.c
  $ sudo install -m 755 libbhi360.so /usr/local/lib/
  $ sudo cp source/bhi*.h /usr/local/include/
  $ sudo cp -a firmware/bhi360 /usr/local/include/
  $ sudo ldconfig
  ```

- [BHI385_SensorAPI](https://github.com/boschsensortec/BHI385_SensorAPI)
  - Use v2.1.1 (latest verified on 2026-09-06). Run these commands from the SDK repository root.
  - Build the SensorAPI core as for BHI360 above.
  ```
  $ git fetch --tags origin
  $ git checkout v2.1.1
  $ gcc -shared -fPIC -O2 -Wl,--no-undefined -o libbhi385.so source/bhi385.c source/bhi385_hif.c source/bhi385_*param.c source/bhi385_event_data.c source/bhi385_logbin.c
  $ sudo install -m 755 libbhi385.so /usr/local/lib/
  $ sudo cp source/bhi*.h /usr/local/include/
  $ sudo cp -a firmware/bhi385 /usr/local/include/
  $ sudo ldconfig
  ```

Update the shared library, headers, and firmware together. After an SDK update,
stop the application and remove the generated `bhi3_s_helper*.so` and
`bhi3_s_helper*.c` files under
`modules/sensor/i2c/cython/bhi3_shuttle_board_3/` (including its `__pycache__/`
directory), as well as matching helper build artifacts under `~/.pyxbld/`.
Then restart to rebuild the Cython helper.
BHI360 v2.3.1 uses the `BMM350_BMP58X_BME688_bsxsam_ndof` firmware and BMP
pressure sensor ID 150. The helper logs the BSX version and magnetic distortion
state changes; it does not configure a product-specific SIC matrix.
BHI360 and BHI385 explicitly enable magnetic distortion events in both FIFOs. Both
magnetometer and orientation outputs are enabled at 50 Hz, including when
running `bhi3_shuttle_board_3/build.py`; that script prints values once per
second and does not print the magnetometer vector.
Both targets were built on a Raspberry Pi Zero 2 W running Raspberry Pi OS
Trixie (Debian 13). I2C acquisition and calibration save/restore were also
verified with BHI360 and BHI385 Shuttle Boards 3.0.

*2 You must enable i2c slowdown. Follow [the adafruit guide](https://learn.adafruit.com/circuitpython-on-raspberrypi-linux/i2c-clock-stretching).

*3 Install manually https://github.com/spacecraft-design-lab-2019/CircuitPython_BMX160


If you want to get a more accurate direction with the geomagnetic sensor, install a package that corrects the geomagnetic declination.

```
$ pip install magnetic-field-calculator
```

#### Button SHIM

```
$ sudo apt install python3-buttonshim
```

#### IO Expander (with MCP23008/MCP23009 and some buttons)

No additional Python package is required by this repository.

#### PiJuice HAT

Follow [official setup guide](https://github.com/PiSupply/PiJuice/tree/master/Software) of PiSupply/PiJuice

#### PiSugar3

No additional Python package is required by this repository.


# Quick Start

If cython is available, it will take a few minutes to run for the first time to compile the program.

## Run on Wayland / X Window

Use Raspberry Pi OS with desktop.

```
$ python3 pizero_bikecomputer.py
```

### PiTFT

see [hardware_installation_pitft.md](./hardware_installation_pitft.md#run-on-x-window)

## Run in console

For legacy MIP / SHARP / E-ink displays in console mode, use `QT_QPA_PLATFORM=offscreen`.
If you use the newer `sharp-drm` driver, use `QT_QPA_PLATFORM=linuxfb:fb=/dev/fb1`.

If your Qt build includes the VNC platform plugin, `QT_QPA_PLATFORM=vnc` can still be used for temporary remote debugging, but it is not a primary workflow for this project.

### Manual execution

#### JDI & SHARP MIP display

For JDI MIP Reflective color LCD module and Adafruit SHARP Memory Display Breakout.

Before running the program, choose one of the following platform plugins:

```
# legacy pigpio / spidev backend
$ QT_QPA_PLATFORM=offscreen python3 pizero_bikecomputer.py

# sharp-drm framebuffer driver
$ QT_QPA_PLATFORM=linuxfb:fb=/dev/fb1 python3 pizero_bikecomputer.py
```

`ctrl + c` to exit the application.

#### PiTFT

see [hardware_installation_pitft.md](./hardware_installation_pitft.md#run-on-console)


### Run as a service

The old `install/` paths and shutdown helper service are no longer used in this repository.
The current service template lives at `scripts/install/etc/systemd/system/pizero_bikecomputer.service`,
and the recommended way is to run `install.sh` and answer `Install services? -> y`.

`install.sh` fills the placeholders in the template, installs `rotate_debug_log.sh`,
and enables `pizero_bikecomputer.service` automatically.

The application log is written to `log/debug.log`.

If you want to manage the service manually, use `scripts/install/etc/systemd/system/pizero_bikecomputer.service`
as a template and fill at least:

- `WorkingDirectory`
- `ExecStartPre`
- `ExecStart`
- `ExecStopPost`
- `User`
- `Group`
- `StandardOutput`

Then reload and start it as usual:

```
$ sudo systemctl daemon-reload
$ sudo systemctl enable pizero_bikecomputer.service
$ sudo systemctl start pizero_bikecomputer.service
```

# Usage

## Button

### Software button

<img width="400" alt="screen01" src="https://user-images.githubusercontent.com/12926652/206077256-f8bda5e5-e4a3-4c39-a7ff-ea343067756c.png">

The buttons at the bottom of the screen are assigned the following functions from left to right. 

| Button | Short press | Long press |
|:-|:-|:-|
| Left (<) | Screen switching(Back) | None |
| LAP | Lap | Reset |
| MENU | Menu | None |
| Start/Stop  | Start/Stop | Quit the program |
| Right (>) | Screen switching(Forward) | None |

### Hardware button

The hardware buttons are designed to roughly match the software screen.
You can change both short and long presses in `modules/button_config.py`.

Button actions are generated from the `ButtonTemplate` definitions and hardware/profile definitions in `button_profile_defs`. The generated result is stored in `button_def`.

For display-attached GPIO buttons, edit `gpio_buttons` only when the BCM GPIO pin assignment differs from the built-in profile. Direct GPIO buttons on supported boards are selected by the board presets in `modules/board_config.py`.

`OVERRIDES` in `button_profile_defs` only needs to contain actions that differ from the selected template. Omitted keys keep the template defaults.

#### PiTFT 2.4

see [hardware_installation_pitft.md](./hardware_installation_pitft.md#hardware-button)

### Button shim

<img src="https://user-images.githubusercontent.com/12926652/91799330-cfc50580-ec61-11ea-9045-e1991aed205c.png" width=240 />

#### Main

From left to right, the button assignments are as follows.

| Button | Short press | Long press |
|:-|:-|:-|
| A | Left (<) | Screenshot |
| B | Lap | Reset |
| C | ANT+ MultiScan | None |
| D | Start/Stop | None |
| E | Right (>) | Menu |

#### Map

| Button | Short press | Long press |
|:-|:-|:-|
| A | Left (<) | Screenshot |
| B | Zoom out | Previous rain/wind time |
| C | Change overlay | Change button mode |
| D | Zoom in | Next rain/wind time |
| E | Right (>) | Change tile mode |

Another button mode

| Button | Short press | Long press |
|:-|:-|:-|
| A | Move left | None |
| B | Move down | Zoom out |
| C | Change overlay | Restore button mode |
| D | Move up | Zoom in |
| E | Move right | Search route(*) |

(*)Search route by Google Routes API. Set your API key in setting.conf.

#### Course Profile

| Button | Short press | Long press |
|:-|:-|:-|
| A | Left (<) | None |
| B | Zoom out | None |
| C | Change button mode | None |
| D | Zoom in | None |
| E | Right (>) | Menu |

Another button mode

| Button | Short press | Long press |
|:-|:-|:-|
| A | Move left | None |
| B | Zoom out | None |
| C | Restore button mode | None |
| D | Zoom in | None |
| E | Move right | None |

#### Menu

In the menu, the button assignments are changed.

| Button | Short press | Long press |
|:-|:-|:-|
| A | Back | None |
| B | Brightness control(*) | None |
| C | Enter | None |
| D | Select items (Back) | None |
| E | Select items (Forward) | None |

(*) If you use the MIP Reflective color LCD with backlight model.

### Garmin Edge Remote (ANT+)

#### Main

The button assignments are as follows.

| Button | Short press | Long press |
|:-|:-|:-|
| PAGE | Left (<) | Right (>) |
| CUSTOM | ANT+ Light ON/OFF | Menu |
| LAP | Lap | None |

#### Map

| Button | Short press | Long press |
|:-|:-|:-|
| PAGE | Left (<-) | Right (->) |
| CUSTOM | Change button mode | Zoom out |
| LAP | Zoom in | None |

Another button mode

| Button | Short press | Long press |
|:-|:-|:-|
| PAGE | None | None  |
| CUSTOM | Restore button mode| Zoom out |
| LAP | Zoom in | None |

#### Course Profile

| Button | Short press | Long press |
|:-|:-|:-|
| PAGE | Left (<-) | Right (->) |
| CUSTOM | Change button mode | Zoom out |
| LAP | Zoom in | None |

Another button mode

| Button | Short press | Long press |
|:-|:-|:-|
| PAGE | None | None  |
| CUSTOM | Restore button mode| Move left |
| LAP | Move right | None |

#### Menu

In the menu, the button assignments are changed.

| Button | Short press | Long press |
|:-|:-|:-|
| PAGE | Select items (Forward) | None |
| CUSTOM | Select items (Back) | Back |
| LAP | Enter | None |

## Map

<img width="400" alt="map-01" src="https://user-images.githubusercontent.com/12926652/206341071-5f9bee00-d959-489b-832a-9b4bf7fe2279.png">

Touch UI:

- left side
  - lock / unlock
  - zoom in
  - zoom out
  - route search by Google Routes API (shown only when token is configured)
- right side
  - overlay selector
  - previous / next time buttons for rain and wind overlays

When unlocked, you can drag the map directly.

## Course profile
<img width="400" alt="map-02" src="https://user-images.githubusercontent.com/12926652/206341086-7935cfbd-8ed3-4068-9f2b-93f676a8932a.png">

Touch UI:

- left side
  - lock / unlock
  - zoom in
  - zoom out

When unlocked, you can drag the profile horizontally.

## Menu screen

<img width="400" alt="menu-01" src="https://github.com/hishizuka/pizero_bikecomputer/assets/12926652/46291e12-9104-4486-a896-aaf7010d7cd2">

### Sensors

<img width="400" alt="menu-02-sensors" src="https://user-images.githubusercontent.com/12926652/206076191-4b8a4084-64a0-443b-a434-f6c6b4d51e2a.png">

- Heart Rate
  - Pair or disconnect an ANT+ heart-rate sensor or a BLE HRS heart-rate sensor.
- Power
  - Pair or disconnect an ANT+ power meter or a BLE CPS power meter.
  - A CPS device can share one BLE connection with the Cadence role when both roles use the same device.
- Cadence
  - Pair or disconnect an ANT+ cadence sensor or a BLE CSCS/CPS cadence sensor.
  - A BLE sensor without crank revolution data is shown as disconnected for this role.
- Light
  - Pair or disconnect an ANT+ bike light.
  - Auto Control automatically controls a paired ANT+ bike light from ambient light and braking hints while recording.
- Control
  - Pair or disconnect an ANT+ remote or a BLE Zwift Click V2 remote.
- Temperature
  - Pair or disconnect an ANT+ temperature sensor.
- Trainer
  - BLE trainer pairing is reserved for the planned BLE cycling-sensor implementation.
  - Fake Trainer for Zwift controls the existing Zwift compatibility helper.
- ANT+ pairing
  - You need to install the ANT+ library and to set [ANT section](#ant-section) of setting.conf with `status = True`.
  - The pairing setting is saved in setting.conf when a sensor is connected, so it will be automatically connected next time you start the program.
- ANT+ ON/OFF
  - The global ANT+ transport switch is under **Connectivity**, separate from sensor roles.
- ANT+ MultiScan
- Speed
  - Pair or disconnect an ANT+ speed sensor or a BLE CSCS speed sensor.
  - Wheel Size
    - Enter the wheel circumference in mm when the ANT+ speed sensor is available.
    - It is used to calculate the distance.
    - The default value is 2,105mm, which is the circumference of 700x25c tire.
    - The value is saved in setting.conf
  - Auto Stop
    - Enable or disable automatic stopwatch start/stop.
  - Auto Stop Cutoff
    - Enter the speed threshold in km/h for automatic stopwatch start/stop.
    - This item is available when Auto Stop is enabled.
  - Gross Ave Speed
    - Enter the target gross average speed in km/h.
- Internal Sensors
  - Map Magnetic Heading
    - Use the internal magnetic heading for the map orientation.
  - Adjust Altitude
    - Enter the current altitude to correct the sea level and increase the accuracy when an internal pressure sensor is connected.
  - Mag Calibration / Pitch/Roll Calibration
    - Calibrate the available internal motion sensors.

### Courses

<img width="400" alt="menu-03-courses" src="https://github.com/hishizuka/pizero_bikecomputer/assets/12926652/35322fa8-e41e-4f8d-a922-fc86c8481cf5">

- Local Storage
  - Select a `.tcx` or `.fit` course file in the `courses` folder.
  - Loading `.fit` files uses the `fitparse` package included by the standard installation.
- Ride with GPS
  - If you [set token in setting.conf](#ridewithgps_api-section), select course from Ride with GPS. Internet access is required. Sample image are shown as belows.
  - Route data is downloaded as JSON together with the map preview and elevation profile images.
  - <img width="400" alt="RidewithGPS-01" src="https://user-images.githubusercontent.com/12926652/206076210-9c50f789-bac3-4bd0-8209-9dea3a61a132.png">
  - <img width="400" alt="RidewithGPS-02" src="https://user-images.githubusercontent.com/12926652/206076212-8696ac34-c9e6-485f-b1ba-687c0d2a0061.png">
- Android Google Maps
  - Receive routes from Google Maps on Android via Bluetooth. The result is parsed using [https://mapstogpx.com](https://mapstogpx.com).
  - `bluez-obexd` must be installed in advance.
  - This entry is available only on Raspberry Pi and only when `/usr/libexec/bluetooth/obexd` exists.
  - If properly paired, Android Google Maps directions can be sent with `Share Directions` > `Bluetooth` > your Raspberry Pi.
    - <img width="320" alt="mapstogpx-01" src="https://github.com/hishizuka/pizero_bikecomputer/assets/12926652/928a8ed5-82e7-4ba2-afc7-6b68150d9043"> <img width="320" alt="mapstogpx-02" src="https://github.com/hishizuka/pizero_bikecomputer/assets/12926652/d6fbfb22-5c93-47e5-920f-8ef4fc9c02de">
- Cancel Course
  - Remove the currently loaded course.
- Course Calc
  - Toggle course indexing and on-course calculation.


### Connectivity
 
<img width="400" alt="livetrack-01" src="https://github.com/hishizuka/pizero_bikecomputer/assets/12926652/9f9660fd-eca4-4b97-a60a-d2ff890bf3f0">

- Auto BT Tethering
  - Provide the network connection used by the ThingsBoard MQTT fallback through a smartphone paired with `bluetoothctl`.
  - The following `Select BT device` must also be specified.
  - Since it operates intermittently once every three minutes by default, the power consumption of the Raspberry Pi and smartphone is much lower than a constant connection via Wifi tethering.
- Select BT device
  - Specify the device to use for bluetooth tethering.
- Live Track
  - Enable real-time data upload to the [ThingsBoard](https://thingsboard.io) dashboard.
  - When Gadgetbridge is connected, telemetry and the course attribute are uploaded through its HTTP bridge.
  - If that HTTP request fails, the program retries through MQTT over Bluetooth tethering.
  - The `tb-mqtt-client` package and a ThingsBoard device access token in [THINGSBOARD_API](#thingsboard_api-section) are required.
  - Import and connect the provided dashboard as described in [thingsboard_setup.md](./thingsboard_setup.md).
- Gadgetbridge
  - Enable BLE UART service for the Android [Gadgetbridge](https://gadgetbridge.org) app.
- Get Location
  - Use Gadgetbridge as a GPS source.


### Upload Activity

Uploads the most recent activity record file(.fit) created by the reset operation after the power is turned on.

- `Auto Upload`
  - Enable or disable the upload confirmation shown after an activity is reset.
  - Select each service toggle to choose the automatic upload destinations.
- The Strava, Garmin, and Ride with GPS upload buttons remain available for manual uploads.

- Strava
  - Direct upload is a legacy, unsupported feature. See the
    [Strava API section](#strava_api-section).
  - For automatic delivery to Strava, upload to Garmin Connect or Ride with GPS
    and configure that service to sync activities to Strava.
- Garmin
  - You need to set the Garmin setting in [GARMINCONNECT_API section](#garminconnect_api-section) of setting.conf.
- Ride with GPS
  - You need to set the Ride with GPS Token in [RIDEWITHGPS_API section](#ridewithgps_api-section) of setting.conf.

### Map and Data

<img width="400" alt="menu-05-map" src="https://user-images.githubusercontent.com/12926652/206076200-383c1d24-ec26-4b79-95e9-a6fd88e161dd.png"> <img width="400" alt="menu-06-map_overlay" src="https://user-images.githubusercontent.com/12926652/206076202-29989a71-34c0-4892-8433-48305868326d.png">

- Select Map
  - Select a standard map.
- Map Overlay
  - Toggle map overlay(heatmap, rain map and wind map) and select an overlay map.
  - Heatmaps are cached, but rain map and wind map require internet connection to fetch the latest images.
- External Data Sources
  - Toggle and configure wind data source and DEM tile source used for calculations.

#### Heatmap

Strava heatmap (bluered)

![map_overlay-strava](https://user-images.githubusercontent.com/12926652/205793586-0b754cde-d1e7-4e57-81d2-2bbd60fc8b11.png)

#### Rain map

RainViewer

![map_overlay_rainviewer](https://user-images.githubusercontent.com/12926652/205876664-ae1b629c-5b3f-4d8a-b789-d3ac24753d7f.png)

気象庁降水ナウキャスト(Japan)

<img src ="https://user-images.githubusercontent.com/12926652/205563333-549cf4dc-abbd-4392-9233-b8391687e0bc.png" width=400/> 

#### Wind map

openportguide

![map_overlay_weather openportguide de](https://user-images.githubusercontent.com/12926652/205876684-253b672f-615d-410c-8496-5eb9a13b2558.png)

#### External Data Sources

- Wind
  - Toggle the external wind data source used for headwind / wind direction calculations.
- Wind Source
  - Select `openmeteo` or a supported SCW source.
- DEM Tile
  - Toggle DEM tile usage.
- DEM Tile source
  - Select the DEM tile source.

### Profile

If ANT+ powermeter is available, set both parameters are used in W'balance (%). They are determined by histrical activity data with bicycle power with [GoldenCheetah](http://www.goldencheetah.org) or [intervals.icu](https://intervals.icu).

<img width="400" alt="menu-07-profile" src="https://user-images.githubusercontent.com/12926652/206076204-197f2454-940b-4267-a626-52740391ddac.png">

### System

<img width="400" alt="menu-08-system" src="https://github.com/hishizuka/pizero_bikecomputer/assets/12926652/402692a5-1612-4bf3-a645-a84ba91b766b">

- Network
  - See below.
- Display
  - Auto Brightness
    - Automatically controls the display backlight from the internal ambient light sensor.
  - Brightness
    - Select a fixed backlight level supported by the current display.
    - Selecting a fixed level disables Auto Brightness.
- Language
  - Reserved menu item. Currently not configurable from this menu.
- Update
  - Execute the application update flow.
- Debug
  - Open the debug submenu described below.
- Power Off
  - Power off the raspberry pi zero when the program is started with the service.

#### Network

<img width="400" alt="menu-09-network" src="https://github.com/hishizuka/pizero_bikecomputer/assets/12926652/48a617c4-73a5-4c4d-ac7b-d2471ed1d404">

- Wifi, Bluetooth
  - Turn Wifi and BT On/Off at the software level using `rfkill`.
- connect Wifi via WPS
  - Try WPS association from the menu.
- Auto Wifi Off
  - Turn Wifi off automatically while recording.
- BT Pairing
  - Scan and pair a Bluetooth device from the menu.
- BT Paired Devices
  - Show and remove paired Bluetooth devices.
- BT Tethering
  - Show available BT PAN devices and optionally start Bluetooth tethering.
- Reset Bluetooth
  - Reset the Bluetooth stack from the menu.

#### Debug

- `Debug Log`
  - View `log/debug.log`.
- `Debug Level Log`
  - Toggle debug log level.
- `Disable Wifi/BT`, `Enable Wifi/BT`
  - Modify `/boot/firmware/config.txt` and require reboot.
- `IP Address`
  - Show current IP address.
- `Restart`
  - Restart the application.
- `Reboot`
  - Reboot Raspberry Pi.

#### Gadgetbridge

- Install [GadgetBridge](https://gadgetbridge.org) on Android and enable the `Connectivity` menu items.
- The `gadgetbridge-rpi-link` package installed in
  [Bluetooth and Cloud](#bluetooth-and-cloud) is required.
- GadgetBridge app settings
  - Enable all permissions. Most Android app permissions are enabled by default when the app is installed.
  - `Settings` > `Discovery and Pairing options` > `Discover unsupported devices`: On.
  - From `Connect new device` in the menu or `+` button, enter `Device discovery`. Select the device (shown as host name), long press, and pair it as `Bangle.js`.
  - Open the device settings in GadgetBridge and enable `Allow Intents`.
- For `Get Location`
  - Open the device settings in GadgetBridge and enable `Use phone gps data`.
  - Set `GPS data update interval` to around `1000-5000` (1s - 5s).
- For Google Maps navigation notifications
  - Gadgetbridge reads Google Maps turn-by-turn instructions from Android notifications.
  - On recent Android versions, Google Maps `Live Updates` notifications can prevent Gadgetbridge from reading the navigation instruction details.
  - If navigation messages are received only as `{"t":"nav"}` or do not include `action` and `distance`, open Android `Settings` > `Apps` > `Maps` > `Notifications` and disable the `Live Updates` notification category for Google Maps.
  - The exact label may vary by Android version and vendor, but it is usually shown as `Live Updates`, `Live info`, or a similar live navigation notification category.

## Settings

There are four runtime configuration files (`setting.conf`, `state.pickle`, `layout.yaml`, `map.yaml`).
`config.py` is code, not a user-edited config file in normal use.

### setting.conf

The settings are dependent on the user environment.

Set the value before starting the program. If the value is set during running, it will not be read.

#### GENERAL section

- `board`
  - Select the board preset, including I2C sensors, GPIO buttons, buzzer, and display mode.
  - `auto`: detect all supported I2C sensors and do not enable custom GPIO buttons.
  - `pizero_bikecomputer`: use the Pi Zero Bikecomputer PCB preset.
  - `bryton_rider_s800`: use the Bryton Rider S800 board preset.
- `display`
  - Set the type of display.
  - There are definitions in `modules/display/display_core.py`.
  - `None`: default (no hardware control)
  - `MIP_JDI_color_400x240`: JDI 2.7 inch MIP reflective color LCD module. (LPM027M128C/LPM027M128B)
  - `MIP_JDI_color_640x480`: JDI 4.4 inch MIP reflective color LCD module. (LPM044M141A)
  - `MIP_Azumo_color_272x451`: Azumo 3.4 inch MIP reflective color LCD module. (14793-06, AUO U340QBN01.1)
  - `MIP_Sharp_mono_400x240`: SHARP 2.7 inch MIP monochrome LCD module. (Sharp LS027B7DH01)
  - `MIP_Sharp_mono_320x240`: SHARP 4.4 inch MIP monochrome LCD module. (Sharp LS044Q7DH01)
  - `Papirus`: PaPiRus ePaper / eInk Screen HAT
  - `DFRobot_RPi_Display`: e-ink Display Module
  - `Pirate_Audio`, `Pirate_Audio_old`: Pirate Audio ("old" assigns the Y button to GPIO 20.)
  - `Display_HAT_Mini`: Display HAT Mini
  - `ST7789_Breakout`: generic ST7789 breakout
  - `PiTFT`: PiTFT2.4 (or a PiTFT2.8 with the same resolution)
- `autostop_status`
  - Enable or disable automatic stopwatch start/stop.
  - If disabled, the stopwatch starts/stops only by button operation.
  - The default value is `True`.
- `autostop_cutoff`
  - Set the threshold for the speed at which the stopwatch will automatically stop/start after it is activated.
  - This value is used only when `autostop_status` is enabled.
  - The default value is `4` [km/h].
- `wheel_circumference`
  - Set the wheel circumference required for ANT+ speed sensor use.
  - It can also be set on the screen.
  - The default value is `2105` (unit is mm) for 700x25c.
- `gross_ave_speed`
  - Set the gross average speed, which is used in the brevet and the like.
  - It is used for cycling long distances with a set time limit.
  - The screen shows the actual gross average and the gained time from this gross average speed.
  - The default value is `15` [km/h].
- `lang`
  - The language setting of the label of items.
  - The default is `EN`.
- `font_file`
  - Set the full path of the font which you want to use.
  - Place the fonts in `fonts/` folder.
- `auto_wifi_off`
  - Turn Wifi off automatically while recording.

#### AUTO_UPLOAD section

- `status`
  - Enable or disable the upload confirmation shown after an activity is reset.
- `strava`, `garmin`, `rwgps`
  - Select the services used by automatic activity upload.
  - These values can also be changed from the Upload Activity menu.

#### BT section

- `bt_pan_device`
  - Default Bluetooth PAN device used by tethering.
- `auto_bt_tethering`
  - Enable automatic Bluetooth tethering.
- `gadgetbridge_status`
  - Enable Gadgetbridge BLE UART service at startup.
- `gadgetbridge_use_gps`
  - Enable GPS acquisition from Gadgetbridge.
#### MAP_AND_DATA section

- `map`
  - Select the base map.
  - Presets are defined in `modules/map_config.py` and can be extended from `map.yaml`.
  - `openstreetmap`, `wikimedia`, and `jpn_kokudo_chiri_in` are built in.
  - You can also add raster mbtiles mapsets generated from [mb-util](https://github.com/mapbox/mbutil). The definition in `map.yaml` is as follows for `maptile/sample_mbtile.mbtiles`.

```
map.yaml entry

  sample_mbtile:
    url: 
    attribution: some attribution.
    use_mbtiles: true
```

- `use_heatmap_overlay_map`, `heatmap_overlay_map`
  - Enable heatmap overlay and select the source.
- `use_rain_overlay_map`, `rain_overlay_map`
  - Enable rain overlay and select the source.
- `use_wind_overlay_map`, `wind_overlay_map`
  - Enable wind overlay and select the source.
- `use_wind_data_source`, `wind_data_source`
  - Enable external wind data and select the source.
- `use_dem_tile`, `dem_map`
  - Enable DEM tile usage and select the source.

#### ANT+ section

- Enable ANT+ with `status = True`.
- Additional setting is not necessary because the settings are written when pairing ANT+ sensors.
- If there are some settings, the program will connect at startup.

#### Power section

Set `cp` as CP and `w_prime` as W prime balance when a power meter is available.
`cda` sets the rider and bicycle drag area used for the wind impact metrics. The
default is `0.40` m². `total_weight` sets the total weight of the rider, bike, and
gear. The default is `80.0` kg. `crr` sets the rolling resistance coefficient used
to calculate `Wind Impact` and `Wind Time`. The default is `0.004`.

#### SENSOR_IMU section
In modules/sensor_i2c.py, use the change_axis method to change the axis direction of the IMU (accelerometer/magnetometer/gyroscope) according to its mounting direction.
The settings are common, so if you use individual sensors, make sure they are all pointing in the same direction.
With `board = auto`, axis values are read from this section. For a specific board,
runtime values are defined by its preset in `modules/board_config.py`, and values
manually entered in `setting.conf` are ignored.

X, Y, and Z printed on the board are set to the following orientations by default.

- X: Forward. Positive value for upward rotation with accelerometer.
- Y: Left. Positive value for upward rotation with accelerometer.
- Z: Downward. Positive value at rest with accelerometer.

Axis conversion is performed with the following variables.

- `axis_swap_xy_status`: Swaps the X and Y axes.
  - The default is `False`, or `True` if you want to apply it.
- `axis_conversion_status`: Inverts the signs of X, Y and Z.
  - Change to `False` by default, or `True` if you want to apply it.
  - `axis_conversion_coef`: Fill in [X, Y, Z] with ±1.

`mag_axis_swap_xy_status`, `mag_axis_conversion_status` and `mag_axis_conversion_coef` can be set if magnetometer axes are different from accelerometer and gyroscope. For example, [SparkFun 9DoF IMU Breakout - ISM330DHCX, MMC5983MA (Qwiic)](https://www.sparkfun.com/products/19895).

`mag_declination` is automatically set by magnetic-field-calculator package.

#### DISPLAY_PARAM section

(experimental)
- `spi_clock`: specify SPI clock of the following displays.
  - applies to legacy `MIP_*` backends
- `use_backlight`
  - Enable backlight control for supported MIP color displays.
- `use_auto_backlight`
  - Enable automatic display backlight control from the ambient light sensor.
- `auto_backlight_cutoff`
  - Threshold for automatic backlight control.
- `manual_backlight_brightness`
  - Store the fixed backlight percentage selected from the System menu.

With `board = auto`, `spi_clock`, `use_backlight`, and `auto_backlight_cutoff`
are read from `setting.conf`. For a specific board, those hardware values are
defined by its preset. `use_auto_backlight` and `manual_backlight_brightness`
are user settings and are read for every board type.

#### STRAVA_API section

Set up for uploading your .fit file to Strava in the "Strava Upload" of the menu. The upload is limited to the most recently reset and exported .fit file.

A paid [Strava subscription](https://developers.strava.com/docs/getting-started/)
is required to set up direct upload because Strava requires a subscription to
create the API application used by this feature.

**Maintenance status (July 2026):** Direct Strava upload is retained temporarily
for existing users, but the project author does not intend to support it after
July 2026. If a future Strava API or authentication change breaks the current
implementation, the feature will be removed rather than updated.

For automatic uploads to Strava, use Garmin Connect or Ride with GPS as the
upload destination in Pi Zero Bikecomputer, then connect that service to Strava:

- [Garmin Connect and Strava automatic sync](https://support.strava.com/en-us/articles/15401903-garmin-and-strava)
- [Ride with GPS Connected Services](https://support.ridewithgps.com/hc/en-us/articles/4419008470299-Connected-Services-Garmin-Connect-Strava-Relive-Wahoo-Hammerhead-and-Coros)

Ride with GPS can forward activity files uploaded directly to it, including
files uploaded by Pi Zero Bikecomputer. It does not forward activities that it
received automatically from another connected service.

To get the Strava token, see "[Trying the Authorization Method (OAuth2) of the Strava V3 API (In Japanese)](https://hhhhhskw.hatenablog.com/entry/2018/11/06/014206)".
Set the `client_id`, `client_secret`, `code`, `access_token` and `refresh_token` as described in the article. Once set, they will be updated automatically.

#### STRAVA_COOKIE section

If you want to use Strava HeatMap, open the Global Heatmap in a browser signed
in to Strava and inspect a `content-a.strava.com` tile request in the browser's
developer tools. Copy the `Key-Pair-Id`, `Policy`, and `Signature` query
parameters and the `_strava_idcf` request cookie to `setting.conf`:

```ini
[STRAVA_COOKIE]
key_pair_id =
policy =
signature =
idcf =
```

The application does not load these values from `.env`; store them in
`setting.conf`. These authentication values can expire; obtain fresh values
when tile requests return 401 or 403. Treat all four values as secrets and do
not commit or share them.
The built-in overlay uses
`https://content-a.strava.com/identified/globalheat/sport_Ride/{style}/{z}/{x}/{y}.png`
at its native 512-pixel tile size. The signed query parameters and cookie are
added automatically. A tile without heatmap data can return 404; this is
expected and its log output is suppressed for the Strava Heatmap only.

#### RIDEWITHGPS_API section

If you want to use heatmap or upload activities to RidewithGPS, set your `token` of the Ride with GPS API.

- Sign up for an account with [RideWithGPS](https://ridewithgps.com/signup).
- Create an API key on [RWGPS API](https://ridewithgps.com/api).
  - Apikey is assumed as `pizero_bikecomputer`.
  - <img width="600" alt="rwgps_api" src="https://github.com/hishizuka/pizero_bikecomputer/assets/12926652/48269f97-04ec-43f8-b0e1-e4f802c42732">
  - If you entered a valid email/password, you will see the auth_token parameter was filled in below.
  - <img width="261" alt="rwgps_get_token" src="https://github.com/hishizuka/pizero_bikecomputer/assets/12926652/fcaf77a8-0531-4e87-a106-6cb3cc1f2c83">
- Set your token.

#### GARMINCONNECT_API section

If you want to upload activities to Garmin Connect, set your `email` and
`password` for the first login. Authentication tokens are stored by
`garminconnect` in `tokenstore` and refreshed automatically. After a successful
tokenstore login, the application clears `email` and `password` from
`setting.conf` when it can write the file.

```ini
[GARMINCONNECT_API]
email =
password =
tokenstore = ~/.garminconnect

# Garmin LiveTrack
livetrack_status = False
livetrack_messages = False
```

`livetrack_status` enables Garmin LiveTrack. `livetrack_messages` enables the
message form on the sharing page and receives its text messages while an
activity is recording. The Messages toggle is selectable while Garmin LiveTrack
is enabled. Its owner-only BTF credential is stored at
`tokenstore/livetrack_btf_credentials.json`; the credential and its internal
messaging device identifier are not `setting.conf` entries.

ThingsBoard and Garmin LiveTrack share the same position sampling window. At
the normal 180-second interval, the state at about 90 seconds and the current
state at 180 seconds are sent together. Each attempted upload closes that
window; failed points are not accumulated into the next interval.

Messages are checked at the same interval as LiveTrack position updates
(`INTERVAL_SEC`, normally 180 seconds), displayed without persistent storage,
then acknowledged as delivered and read. Gadgetbridge responses containing a
`messages` array are accepted as successful; missing, bodyless or malformed
bridge responses are retried at the next interval without disabling the
feature. Changing the Messages toggle synchronizes the sharing-page form when a
session is active. Outside a session it only saves the setting, which is sent at
the next session start. Direct HTTP failures are retried with the next LiveTrack
update. A Gadgetbridge request is sent once per session or setting change because
its HTTP result is unavailable. An expired BTF credential produces one popup
while leaving the setting unchanged; offline and timed-out requests are retried
later.

Garmin LiveTrack is disabled by default and uses an unofficial private API that
may stop working if Garmin changes it.

Tokens saved by versions earlier than 0.3 are incompatible, so the first upload
after upgrading requires a fresh login. If Garmin MFA is enabled, create this
token once with an interactive `garminconnect` login before uploading from the
application.

#### GOOGLE_ROUTES_API section

If you want to search for a route on a map, set your `token` of the Google Routes API.
The `token` value is your Google Maps Platform API key. You usually do not need to
create a new API key when migrating from the legacy route search API, but you must
enable the Routes API in the same Google Cloud project and allow the Routes API in
the API key restrictions if you use them.

#### THINGSBOARD_API section

If you want to use ThingsBoard dashboard, set your `token` of the Thingboard device access token.
The default server is `demo.thingsboard.io`, and `status` stores the current
Live Track on/off state.
The access token is a secret. Do not include it in dashboard exports, logs, or
committed configuration files.


### state.pickle

It stores temporary variables such as values for quick recovery in the event of a power failure and sensor calibration results.
BHI3 calibration profiles are stored separately under `log/bhi3/` as `bhi360_calib_*.bin` or `bhi385_calib_*.bin`.

Most of them are deleted on reset.

### layout.yaml

Set up the placement of each item on the display of a screen consisting only of numerical values.
(Maps and graphs cannot be edited with this setting.)

The following is an example of a top screen.

```
MAIN:
  STATUS: true
  LAYOUT:
    Power: [0, 0, 1, 2]
    HR: [0, 2]
    Speed: [1, 0]
    Cad.: [1, 1]
    Timer: [1, 2]
    Dist.: [2, 0]
    Work: [2, 1]
    Ascent: [2, 2]
```

- `MAIN`: The name is optional. It is not used in the program, but the following `STATUS` and `LAYOUT` are displayed on one screen. The number of screens can be increased or decreased.
- `STATUS`: Show this screen or not.
  - Set the boolean value of `true` or `false` of yaml format.
- `LAYOUT`: Specify the position of each element.
  - Each element is defined in `modules/gui_config.py` under `G_ITEM_DEF`. You can also add your own variables there.
  - The position is set up in the form of [Y, X], with the top left as the origin [0, 0], the right as the positive direction of the X axis, and the bottom as the positive direction of the Y axis. The implementation is the coordinate system of QGridLayout.
  - If you want to merge multiple cells, the third argument should be the bottom Y coordinate + 1, and the fourth argument should be the right X coordinate + 1. For example, `Power: [0, 0, 1, 2]` merges the [0, 0] cell with the right next [0, 1] cell.

### map.yaml

Register custom map names, tile URLs, tile sizes, and attribution in this file.
The following is an example:

```
opentopomap:
  url: https://a.tile.opentopomap.org/{z}/{x}/{y}.png
  attribution: © OpenTopoMap
  tile_size: 256
```

- Entry name: Map name
  - This is the string to be set to [MAP_AND_DATA](#map_and_data-section) -> `map` in `setting.conf`.
- `url`: Tile URL
  - Set the tile URL. Tile coordinates X, Y, and zoom Z should be listed with `{x}`, `{y}`, and `{z}`.
- `attribution`: Copyright
  - Set the copyright required for the map.
- `tile_size`: Tile size in pixels
  - This is optional and defaults to 256.

### config.py

There are some settings which the user doesn't need to care about and some variables defined in the above configuration file.

## Prepare course files and maps

Put `.tcx` or `.fit` course files in the `courses/` folder. They are listed in the `Courses > Local Storage` menu.

To download the map in advance, run the program manually with the --demo option. It will start in demo mode.

```console
$ python3 pizero_bikecomputer.py --demo
```

Press the left button to move to the map screen and leave it for a while. The current position will move along the course and download the required area of the map. 


[Back to README.md](../README.md)
