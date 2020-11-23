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

#### I2C GPS (experimental)

Assume I2C interface is on in raspi-config.

```
$ sudo apt-get install python3-dateutil
$ sudo pip3 install timezonefinder adafruit-circuitpython-gps
```


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

| Maker | Sensor | additional pip package |
|:-|:-|:-|
| [Pimoroni](https://shop.pimoroni.com) | [Enviro pHAT](https://shop.pimoroni.com/products/enviro-phat) | None |
| [Adafruit](https://www.adafruit.com) | [BMP280](https://www.adafruit.com/product/2651) | adafruit-circuitpython-bmp280 |
| [Adafruit](https://www.adafruit.com) | [LPS33HW](https://www.adafruit.com/product/4414) | adafruit-circuitpython-lps35hw |
| [Strawberry Linux](https://strawberry-linux.com) | [LPS33HW](https://strawberry-linux.com/catalog/items?code=12133) | None |
| [DFRobot](https://www.dfrobot.com) | [BMX160+BMP388](https://www.dfrobot.com/product-1928.html) | adafruit-circuitpython-bmp3xx, BMX160(*1) | 
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

The output of the log file will be in "./log/debug.txt".

```
$ sudo systemctl start pizero_bikecomputer.service
```


# Usage

Comming soon!

```
$ python3 pizero_bikecomputer.py --demo
```

Temporarily use with map downloading. A course file is required. After launching the program, go to the map screen.


[Back to README.md](/README.md)
