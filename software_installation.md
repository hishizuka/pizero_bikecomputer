[Back to README.md](/README.md)

# Table of Contents

- [Installation](#installation)
  - [macOS or Linux](#macOS-or-Linux)
  - [Raspberry Pi OS](#Raspberry-Pi-OS)
    - [common](#common)
    - [GPS module](#gps-module)
    - [ANT+ USB dongle](#ant+-usb-dongle)
    - [Display](#display)
    - [I2C sensors](#i2c-sensors)
- [Quick Start](#quick-start)
  - [Run on X Window](#Run-on-X-Window)
    - [Run from the lancher menu](#run-from-the-lancher-menu)
    - [Run with autostart](#run-with-autostart)
  - [Run in a console](#Run-in-a-console)
    - [Manual execution](#manual-execution)
    - [Run as a service](#run-as-a-service)
- [Usage](#usage)
  - [Button](#button)
    - [Software button](#Software-button)
    - [Hardware button](#Hardware-button)
  - [Menu screen](#menu-screen)
  - [Settings](#settings)
    - [setting.conf](#setting_conf)
    - [setting.pickle](#setting_pickle)
    - [layout.yaml](#layout_yaml)
    - [map.yaml](#map_yaml)
    - [config.py](#config_py)
  - [Prepare course files and maps](#prepare-course-files-and-maps)

# Installation

Assume Python version 3 environment. Version 2 is not supported.

## macOS or Linux

```
$ git clone https://github.com/hishizuka/pizero_bikecomputer.git
$ pip3 install PyQt5 numpy oyaml pillow
$ pip3 install git+https://github.com/hishizuka/pyqtgraph.git
$ cd pizero_bikecomputer
```

Note:
Pyqt version 5.15.0 in macOS has [a qpushbutton issue](https://bugreports.qt.io/browse/QTBUG-84852), so installing newest version(5.15.1~) is recommended.

## Raspberry Pi OS

Assume Raspberry Pi OS (32-bit) with desktop, not Raspberry Pi OS (32-bit) Lite. I haven't checked the procedure in Lite, but in the future I will try minimum OS such as Lite or buildroot.

Also, your Raspberry Pi is connected to internet and updated with `apt-get update & apt-get upgrade`.

Here is [my setup guide in Japanese](https://qiita.com/hishi/items/8bdfd9d72fa8fe2e7573).

### Common

Install in the home directory of default user "pi".

```
$ cd
$ git clone https://github.com/hishizuka/pizero_bikecomputer.git
$ sudo apt-get install python3-pip cython3 cmake gawk python3-numpy python3-pyqt5
$ sudo pip3 install oyaml
$ sudo apt-get install wiringpi python3-smbus python3-rpi.gpio python3-psutil python3-pil
$ sudo pip3 install git+https://github.com/hishizuka/pyqtgraph.git
$ cd pizero_bikecomputer
```

### GPS module

#### UART GPS

Assume Serial interface is on and login shell is off in raspi-config and GPS device is connected as /dev/ttyS0. If GPS device is /dev/ttyAMA0, modify gpsd config file(/etc/default/gpsd).

```
$ sudo apt-get install gpsd gpsd-clients python3-dateutil
$ sudo pip3 install gps3 timezonefinder 
$ sudo cp install/etc/default/gpsd /etc/default/gpsd
$ sudo systemctl enable gpsd
```

Check with `cgps` or `gpsmon` command.

#### I2C GPS

Assume I2C interface is on in raspi-config.

```
$ sudo apt-get install python3-dateutil
$ sudo pip3 install timezonefinder pa1010d
```

Check with [pa1010d example program](https://github.com/pimoroni/pa1010d-python/blob/master/examples/latlon.py)


### ANT+ USB dongle

```
$ sudo apt-get install libusb-1.0-0 python3-usb
$ sudo pip3 install git+https://github.com/hishizuka/openant.git
$ sudo systemctl enable pigpiod
```
 

### Display

Assume SPI interface is on in raspi-config.

#### PiTFT 2.4

Follow [official setup guide](https://learn.adafruit.com/adafruit-2-4-pitft-hat-with-resistive-touchscreen-mini-kit/overview) of Adafruit, or [my setup guide (Japanese)](https://qiita.com/hishi/items/bdd630666277e4f8162a).

Additionally, install programs which to turn the PiTFT 2.4 backlight on and off.

```
$ sudo cp install/usr/local/bin/disable-pitft /usr/local/bin/
$ sudo cp install/usr/local/bin/enable-pitft /usr/local/bin/
```

Install the program which turns off the backlight at shutdown.

```
$ sudo cp install/etc/systemd/system/disable-pitft.service /etc/systemd/system/
$ sudo systemctl daemon-reload
$ sudo systemctl enable disable-pitft.service
```

If you run the program in a console, you need to build Qt5 and PyQt5 because the package python3-pyqt5 provided with Raspbian OS does not include a touchscreen library(tslib).

Note:

The touchscreen does not work properly in Raspbian OS(Buster) + Qt　5.14(or higher) + PyQt 5.14(or higher) from some issues. So, if you use PiTFT, I recomand to run on X Window at present.
In Raspbian OS(Stretch) + Qt　5.12.3 + PyQt 5.12.3, the touchscreen works.

##### Build Qt

Follow ["Building Qt 5.12 LTS for Raspberry Pi on Raspbian"](https://www.tal.org/tutorials/building-qt-512-raspberry-pi) with Raspberry Pi 4 4GB or 8GB. Use the compile option "-platform linux-rpi-g++" for Raspberry Pi 1 or zero, not use options for Raspberry Pi 4 and so on.
Use the same SD card on Raspberry Pi 4.

You will need libts-dev package before configure of Qt. (from [RaspberryPi2EGLFS](https://wiki.qt.io/RaspberryPi2EGLFS))

```
sudo apt-get install libudev-dev libinput-dev libts-dev libxcb-xinerama0-dev libxcb-xinerama0
```

##### Build PyQt5

Follow [PyQt Reference Guide](https://www.riverbankcomputing.com/static/Docs/PyQt5/installation.html).
The source is avaiable [here](https://pypi.org/project/PyQt5/#files)

```
$ cd
$ mkdir work; cd work
$ wget NEWEST-PYQT5-PACKAGE-SOURCE-FILE
$ sudo pip3 install PyQt-builder
$ sip-build --no-make --qmake PATH-TO-YOUR-QMAKE
$ cd build
$ make -j4
$ sudo make install
$ sudo pip3 install PyQt5-sip
```

#### MIP Reflective color LCD module and Adafruit SHARP Memory Display Breakout

You can use python3-pyqt5 package. Don't need building Qt.

```
$ sudo apt-get install python3-spidev python3-pigpio
$ sudo pip3 install spidev --upgrade
$ sudo systemctl enable pigpiod
$ sudo systemctl start pigpiod
```

#### E-ink Displays

You can use python3-pyqt5 package too.

##### PaPiRus ePaper / eInk Screen HAT for Raspberry Pi

Follow [official setup guide](https://github.com/PiSupply/PaPiRus)

##### DFRobot e-ink Display Module for Raspberry Pi 4B/3B+/Zero W

Follow [official setup guide](https://wiki.dfrobot.com/Raspberry_Pi_e-ink_Display_Module_SKU%3A_DFR0591) and install manually.


### I2C sensors

Assume I2C interface is on in raspi-config.

#### Main sensors (pressure, temperature, IMU and light)

Install pip packages of the sensors you own.

Here is an example.
```
$ sudo pip3 install adafruit-circuitpython-bmp280
```

| Manufacturer | Sensor | additional pip package |
|:-|:-|:-|
| [Pimoroni](https://shop.pimoroni.com) | [Enviro pHAT](https://shop.pimoroni.com/products/enviro-phat) | None |
| [Adafruit](https://www.adafruit.com) | [BMP280](https://www.adafruit.com/product/2651) | None |
| [Adafruit](https://www.adafruit.com) | [BMP390](https://www.adafruit.com/product/4816) | None |
| [Adafruit](https://www.adafruit.com) | [LPS33HW](https://www.adafruit.com/product/4414) | adafruit-circuitpython-lps35hw |
| [Strawberry Linux](https://strawberry-linux.com) | [LPS33HW](https://strawberry-linux.com/catalog/items?code=12133) | None |
| [DFRobot](https://www.dfrobot.com) | [BMX160+BMP388](https://www.dfrobot.com/product-1928.html) | BMX160(*1) | 
| [Adafruit](https://www.adafruit.com) | [LSM6DS33 + LIS3MDL](https://www.adafruit.com/product/4485) | adafruit-circuitpython-lsm6ds adafruit-circuitpython-lis3mdl |
| [Adafruit](https://www.adafruit.com) | [LSM9DS1](https://www.adafruit.com/product/4634) | adafruit-circuitpython-lsm9ds1 | 
| [Adafruit](https://www.adafruit.com) | [BNO055](https://www.adafruit.com/product/4646) | adafruit-circuitpython-bno055 (*2) | 
| [Adafruit](https://www.adafruit.com) | [VCNL4040](https://www.adafruit.com/product/4161) | adafruit-circuitpython-vcnl4040 |

*1 Install manually https://github.com/spacecraft-design-lab-2019/CircuitPython_BMX160

*2 You must enable i2c slowdown. Follow [the adafruit guide](https://learn.adafruit.com/circuitpython-on-raspberrypi-linux/i2c-clock-stretching).


#### Button SHIM

```
$ sudo apt-get install python3-buttonshim
```

#### PiJuice HAT

Follow [official setup guide](https://github.com/PiSupply/PiJuice/tree/master/Software) of PiSupply/PiJuice


# Quick Start

## Run on X Window

If you run the program from the SSH login shell, add the following environment variable.

```
export DISPLAY=:0.0
```

Then, run the program.

```
$ python3 pizero_bikecomputer.py -f
```

### Run from the lancher menu.

Making launcher menu or desktop icon may be useful.

![lancher menu](https://qiita-user-contents.imgix.net/https%3A%2F%2Fqiita-image-store.s3.ap-northeast-1.amazonaws.com%2F0%2F100741%2Fc466c6f0-ede8-5de2-2061-fbbbcccb93fc.png?ixlib=rb-1.2.2&auto=format&gif-q=60&q=75&w=1400&fit=max&s=864176ddffe3895226a6fd8bf20fb4d0)

Make "New Item" in Main Menu Editor, and set "/home/pi/pizero_bikecomputer/exec.sh" in "Command:" field.

![short cut](https://qiita-user-contents.imgix.net/https%3A%2F%2Fqiita-image-store.s3.ap-northeast-1.amazonaws.com%2F0%2F100741%2Fe318acf1-3c89-0537-956c-9e64738b8f81.png?ixlib=rb-1.2.2&auto=format&gif-q=60&q=75&w=1400&fit=max&s=fedb51b245af88bffc2e090031cf10a3)

### Run with autostart

If you are using the autologin option, you can run the program automatically using the following procedure。

```
$ mkdir -p ~/.config/lxsession/LXDE-pi
$ cp /etc/xdg/lxsession/LXDE-pi/autostart ~/.config/lxsession/LXDE-pi/
$ echo "@/home/pi/pizero_bikecomputer/exec.sh" >> ~/.config/lxsession/LXDE-pi/autostart
```

## Run in a console

### Manual execution

#### PiTFT

Before run the program, add the following environment variables.

```
$ export QT_QPA_PLATFORM=linuxfb:fb=/dev/fb1
$ export QT_QPA_EVDEV_TOUCHSCREEN_PARAMETERS=/dev/input/event0:rotate=270
$ export QT_QPA_FB_TSLIB=1
$ export TSLIB_FBDEVICE=/dev/fb1
$ export TSLIB_TSDEVICE=/dev/input/event0
$ python3 pizero_bikecomputer.py
```

Note: Works with Raspbian Stretch. No further versions have been confirmed to work. It seems that the touch screen axis is not set.

#### MIP Reflective color LCD module, SHARP Memory Display or E-Ink displays

Before run the program, add the following environment variable.

```
$ QT_QPA_PLATFORM=offscreen python3 pizero_bikecomputer.py
```

### Run as a service

If you use displays in console environment not X Window, install auto-run service and shutdown service.

#### auto-run setting

If you use MIP Reflective color LCD module, SHARP Memory Display or E-Ink displays, modify install/etc/systemd/system/pizero_bikecomputer.service.

```
ExecStart=/home/pi/pizero_bikecomputer/exec-mip.sh
```

Install servece scripts.

```
$ sudo cp install/etc/systemd/system/pizero_bikecomputer.service /etc/systemd/system/
$ sudo cp install/usr/local/bin/pizero_bikecomputer_shutdown /usr/local/bin/
$ sudo cp install/etc/systemd/system/pizero_bikecomputer_shutdown.service /etc/systemd/system/
$ sudo systemctl daemon-reload
$ sudo systemctl enable pizero_bikecomputer.service
$ sudo systemctl enable pizero_bikecomputer_shutdown.service
```

#### start the service

The output of the log file will be in "/home/pi/pizero_bikecomputer/log/debug.txt".

```
$ sudo systemctl start pizero_bikecomputer.service
```


# Usage

## Button

### Software button

![app-01.png](https://qiita-image-store.s3.ap-northeast-1.amazonaws.com/0/100741/f8eeed99-878d-817e-21e7-543c985f0009.png)

The buttons at the bottom of the screen are assigned the following functions from left to right. 

| Button | Short press | Long press |
|:-|:-|:-|
| Left (<-) | Screen switching(Back) | None |
| LAP | LAP | Reset |
| MENU | Enter the menu | None |
| Start/Stop  | Start/Stop | Quit the program |
| Right (->) | Screen switching(Forward) | None |

### Hardware button

The hardware buttons are designed to roughly match the software screen.
You can change both short and long presses in "modules/config.py".

#### PiTFT 2.4

<img width="300" alt="pitft_button" src="https://user-images.githubusercontent.com/12926652/100878687-da579b00-34ed-11eb-987f-e15bf488f1f3.png">

From left to right, the button assignments are as follows.

| GPIO NUM | Short press | Long press |
|:-|:-|:-|
| 5 | Screen switching(Back) | None |
| 6 | LAP | Reset |
| 12 | Screen brightness On/Off | None |
| 13 | Start/Stop | Quit the program |
| 16 | Screen switching(Forward) | Entering the menu |

In the menu, the button has different assignments. From left to right, the button assignments are as follows.

| GPIO NUM | Short press | Long press |
|:-|:-|:-|
| 5 | Back | None |
| 6 | None | None |
| 12 | Enter | None |
| 13 | Select items (Back) | None |
| 16 | Select items (Forward) | None |

Both short press and long press can be changed. And only the GPIO number of PiTFT 2.4 is supported. For other models, you need to change it in modules/config.py.

### Button shim

<img src="https://user-images.githubusercontent.com/12926652/91799330-cfc50580-ec61-11ea-9045-e1991aed205c.png" width=240 />

From left to right, the button assignments are as follows.

| GPIO NUM | Short press | Long press |
|:-|:-|:-|
| A | Screen switching(Back) | None |
| B | LAP | Reset |
| C | Change mode(*) | None |
| D | Start/Stop | None |
| E | Screen switching(Forward) | Entering the menu |

(*)In the map, change button assignments.
- A: left / zoom out(long press), B: down / zoom in(long press), C:Change mode, D: up, E: right
- A: zoom down, B: zoom up, C: Change mode, D: none, E: Search route by Google DIrections API

In the menu, the button has different assignments. From left to right, the button assignments are as follows.

| GPIO NUM | Short press | Long press |
|:-|:-|:-|
| A | Back | None |
| B | brightness control(*) | None |
| C | Enter | None |
| D | Select items (Back) | None |
| E | Select items (Forward) | None |

(*) If you use the MIP Reflective color LCD with backlight model.

## Menu screen

![app-02.png](https://qiita-image-store.s3.ap-northeast-1.amazonaws.com/0/100741/43df2bd6-2af9-16cd-f356-a30ede21d63a.png)

- ANT+ Sensors
  - Pairing with ANT+ sensors. 
  - You need to install the ANT+ library and to set [ANT section](#ant-section) of [setting.conf](#settingconf) with `status = True`.
  - The pairing setting is saved in setting.conf when a sensor is connected, so it will be automatically connected next time you start the program.
- Wifi BT
  - Wifi and BT are switched on and off.
- Update
  - Update the program.
  - It just does a `git pull origin master` in update.sh.
- Strava Upload
  - Upload the log file(.fit) to Strava.
  - You need to set the Strava Token in [Strava API section](#strava_api-section) of [setting.conf](#settingconf).
- Wheel Size
  - Enter the wheel circumference in mm when the ANT+ speed sensor is available.
  - It is used to calculate the distance.
  - The default value is 2,105mm, which is the circumference of 700x25c tire.
  - The value is saved in setting.conf.
- Adjust Altitude
  - Enter the current altitude to correct the sea level and increase the accuracy when an I2C pressure sensor is connected.
- Power Off
  - Power off the raspberry pi zero when the program is started with the service.
- Debug log
  - View "log/debug.log". But The viewer is created temporarily and not properly implemented. So, this will be removed in the future.

## Settings

There are five different configuration files. You need to edit at the first "setting.conf" and don't need to care about the other files.

### setting.conf

The settings are dependent on the user environment.
GENERAL -> display must be set.

#### ANT+ section

- Enable ANT+ with `status = True`.
- Additional setting is not necessary because the settings are written when pairing ANT+ sensors.
- If there are some settings, the program will connect at startup.

#### GENERAL section

- `display`
  - Set the type of display.
  - There are definitions in `modules/config.py` for the resolution and availability of the touchscreen.
  - `PiTFT`: PiTFT2.4 (or a PiTFT2.8 with the same resolution)
  - `MIP`: MIP color reflective LCD module 2.7 inch.
  - `MIP_Sharp`: SHARP Memory Display Breakout
  - `Papirus`: PaPiRus ePaper / eInk Screen HAT
  - `DFRobot_RPi_Display`: e-ink Display Module
- `autostop_cutoff`
  - Set the threshold for the speed at which the stopwatch will automatically stop/start after it is activated.
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
  - You can set other languages with `G_LANG` in modules/gui_config.py. Samples of `JA` are available.
- `font_file`
  - Set the the full path of the font which you want to use.
  - Place the fonts in `fonts/` folder.
- `map`
  - Set the map.
  - The `G_MAP_CONFIG` in modules/config.py provides some preset definitions.
  - `toner`: A map for monochrome colors. [http://maps.stamen.com/toner/](http://maps.stamen.com/toner/)
  - `wikimedia`: An example map of a full-color map. [https://maps.wikimedia.org/](https://maps.wikimedia.org/)
  - `jpn_kokudo_chiri_in`: A map from Japan GSI. [https://cyberjapandata.gsi.go.jp](https://cyberjapandata.gsi.go.jp)
  - You can add a map URL to map.yaml. Specify the URL in tile format (tile coordinates by [x, y] and zoom level by [z]). And The map name is set to this setting `map`.

#### STRAVA_API section

Set up for uploading your .fit file to Strava in the "Strava Upload" of the menu. The upload is limited to the most recently reset and exported .fit file.

To get the Strava token, see "[Trying the Authorization Method (OAuth2) of the Strava V3 API (In Japanese)](https://hhhhhskw.hatenablog.com/entry/2018/11/06/014206)".
Set the `client_id`, `client_secret`, `code`, `access_token` and `refresh_token` as described in the article. Once set, they will be updated automatically.

#### STRAVA_COOKIE section

Set the variables of Strava cookie if you want to use Strava HeatMap.
Log in to Strava, get the `key_pair_id`, `policy` and `signature` from the cookie from Strava and set these variables. 
After that, set the URL of Strava heatmap in map.yaml.

#### SENSOR_IMU section
In modules/sensor_i2c.py, use the change_axis method to change the axis direction of the IMU (accelerometer/magnetometer/gyroscope) according to its mounting direction.
The settings are common, so if you use individual sensors, make sure they are all pointing in the same direction.

X, Y, and Z printed on the board are set to the following orientations by default.

- X: Forward is positive.
- Y: Left is positive.
- Z: Downward is positive.

Axis conversion is performed with the following variables.

- `axis_swap_xy_status`: Swaps the X and Y axes.
  - The default is `False`, or `True` if you want to apply it.
- `axis_conversion_status`: Inverts the signs of X, Y and Z.
  - Change to `False` by default, or `True` if you want to apply it.
  - `axis_conversion_coef`: Fill in [X, Y, Z] with ±1.

#### GOOGLE_DIRECTION_API section

Set your token of the Google Directions API. 

#### BT_ADDRESS section

Unused.

### setting.pickle

It stores temporary variables such as values for quick recovery in the event of a power failure and sensor calibration results.

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
  - Each element is defined in modules/gui_congig.py under `G_ITEM_DEF`. You can also add your own variables to the modules/gui_congig.py file.
  - The position is set up in the form of [Y, X], with the top left as the origin [0, 0], the right as the positive direction of the X axis, and the bottom as the positive direction of the Y axis. The implementation is the coordinate system of QGridLayout.
  - If you want to merge multiple cells, the third argument should be the bottom Y coordinate + 1, and the fourth argument should be the right X coordinate + 1. For example, `Power: [0, 0, 1, 2]` merges the [0, 0] cell with the right next [0, 1] cell.

### map.yaml

Register the map name, tile URL and copyright in this file.
An example of Strava HeatMap is shown below.

```
strava_heatmap_hot:
  url: https://heatmap-external-b.strava.com/tiles-auth/ride/hot/{z}/{x}/{y}.png?px=256
  attribution: strava
```

- Line 1: Map name
  - This is the string to be set to [GENERAL](#general-section) -> map in setting.conf.
- Second line: tile URL
  - Set the tile URL. Tile coordinates X, Y, and zoom Z should be listed with `{x}`, `{y}`, and `{z}`.
- Line 3: Copyright.
  - Set the copyright required for the map.

### config.py

There are some settings which the user doesn't need to care about and some variables defined in the above configuration file.

## Prepare course files and maps

Put course.tcx file in course folder. The file name is fixed for now. If the file exists, it will be loaded when it starts up.

To download the map in advance, run the program manually with the --demo option. It will start in demo mode.

```console
$ python3 pizero_bikecomputer.py --demo
```

Press the left button to move to the map screen and leave it for a while. The current position will move along the course and download the required area of the map. 


[Back to README.md](/README.md)
