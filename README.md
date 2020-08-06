![title](https://user-images.githubusercontent.com/12926652/89370669-47178000-d71c-11ea-896f-0d98f4cbd5da.jpg)

# Pi Zero Bikecomputer
a GPS and ANT+ bike computer based on Raspberry Pi Zero (W, WH)

# Table of Contents

- [Abstract](#abstract)
- [Features](#features)
- [Comparison with other bike computers](#comparison)
- [Parts List](#parts-list)
- [Assembly](#assembly)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [Q&A](#qa)


# Abstract

Pi Zero Bikecomputer is a GPS and ANT+ bike computer based on Raspberry Pi Zero(W, WH). This is the first DIY project in the world integrated with necesarry hardwares and softwares for modern bike computer. It measures and records position(GPS), ANT+ sensor(speed/cadence/power) and I2C sensor(pressure/temperature/altitude, etc). It also displays these values, even maps and courses in real-time. In addition, it write out log into .fit format file.

In this project, Pi Zero Bikecomputer got basic functions needed for bike computers. Next target is to add new functions which existing products do not have!

You will enjoy both cycling and the maker movement with Pi Zero Bikecomputer!

Here is detail articles in Japanese.

[I tried to make a bikecomputer, the result was pretty good](https://qiita.com/hishi/items/46619b271daaa9ad41b3)

[Let's make a bikecomputer with Raspberry Pi Zero (W, WH)](https://qiita.com/hishi/items/46619b271daaa9ad41b3)


# Features

- Easy to make
  - use modules available at famous Maker stores.
  - assemble in Raspberry Pi ecosystems.
  - install with basic commands such as `apt-get install`, `pip` and `git` command.

- customization
  - only need modules you want to use. Pi Zero Bikecomputer detects your modules.

- Supports cross platform develop environments
  - Pi Zero Bikecomputer uses [PyQt5](https://pypi.org/project/PyQt5/) GUI library. So, you can run on Raspberry Pi OS, some Linux, macOS and Windows.

# Comparison with other bike computers

- 200km ride with Garmin Edge 830 and Pizero Bikecomputer ([strava activity](https://www.strava.com/activities/2834588492))

![title-03.png](https://qiita-image-store.s3.ap-northeast-1.amazonaws.com/0/100741/b355cb92-8e7f-6b3f-7cd0-98ba8803a56c.png)

| Items | Edge830 | Pi Zero Bikecomputer |
|:-:|:-:|:-:|
| Distance | 193.8 km  | 194.3 km  |
| Work |  3,896 kJ | 3,929 kJ  |
| Moving time | 9:12 | 9:04  |
| Total Ascent | 2,496 m | 2,569 m |


# Parts List

- [Raspberry Pi Zero W / WH](https://www.raspberrypi.org/products/raspberry-pi-zero-w/)
- Display
  - [PiTFT 2.4](https://www.adafruit.com/product/2455) 
    - (good) easy to assemble
    - (bad) hard to see in direct sunshine
  - [MIP Reflective color LCD module 2.7" w/ backlight](https://international.switch-science.com/catalog/5395/) 
      - [Connection board for MIP Reflective color LCD to FRDM-K64F](https://international.switch-science.com/catalog/5393/) is also needed
    - (good) very visible even in direct sunshine
    - (good) ultra-low power consumption
    - (bad) very expensive
    - (bad) 8 colors only
    - recomended if you don't think costs. Commercial products often uses a reflective LCD.
  - [PaPiRus ePaper / eInk Screen HAT for Raspberry Pi](https://uk.pi-supply.com/products/papirus-epaper-eink-screen-hat-for-raspberry-pi) or [DFRobot e-ink Display Module for Raspberry Pi 4B/3B+/Zero W](https://www.dfrobot.com/product-1866.html)
    - (good) very visible
    - (good) ultra-low power consumption
    - (bad) slow drawing
    - (bad) no backlight
    - (bad) 2 colors only
- ANT+ USB dongle
  - available in eBay or aliexpress
  - also need micro USB OTG Adapter : like [adafruit adapter](https://www.adafruit.com/product/2910). 
- GPS module
  - UART with GPSd is recomended. I2C(Sparkfun qwiic or Adafruit STEMMA QT) is experimental.
  - [SparkFun ZOE-M8Q](https://www.sparkfun.com/products/15193)
    - UART, I2C(Sparkfun qwiic) and SPI
    - an [antenna](https://www.sparkfun.com/products/15246) is also needed
    - stable and low power consumption
    - recommended as of 2020/6.
  - [Akizuki Denshi GPS module](http://akizukidenshi.com/catalog/g/gK-09991/)
    - UART
    - easy to get in Tokyo (buy at Akihabara)
    - cheap and low power consumption
  - [Adafruit Mini GPS PA1010D](https://www.adafruit.com/product/4415)
    - UART and I2C(Adafruit STEMMA QT)
  - [Adafruit Ultimate GPS Breakout](https://www.adafruit.com/product/746)
    - UART
- I2C sensors: 
  - Adafuit circuitpython library is required except some sensors(\*1). Refer to learing page of each sensors.
  - pressure, temperature: for altitude, grade, and total ascent/descent
    - [BMP280](https://shop.pimoroni.com/products/enviro-phat) (\*1)
    - [BMP38X](https://www.dfrobot.com/product-1928.html)
    - [LPS33HW](https://www.adafruit.com/product/4414) (\*1)
  - IMU: Accelerometer is required for stop detection when using GPS. Magnetometer sensors are used in compasses. 
    - [LSM303](https://shop.pimoroni.com/products/enviro-phat) (\*1); 
    - [LSM6DS](https://www.adafruit.com/product/4485): Accel / Gyro
    - [LSM9DS1](https://www.sparkfun.com/products/13944): Accel / Gyro / Mag 
    - [LIS3MDL](https://www.adafruit.com/product/4485): Mag 
    - [BMX160](https://www.dfrobot.com/product-1928.html): Accel / Gyro / Mag
  - lux: for auto backlight when using MIP Reflective color LCD
    - [TCS3472](https://shop.pimoroni.com/products/enviro-phat)
    - [VCNL4040](https://www.adafruit.com/product/4161)
  - button: must required for displays which don't have buttons like MIP display
    - [Button SHIM](https://shop.pimoroni.com/products/button-shim)
  - power: if you connected battery HAT.
    - [PiJuice HAT](https://uk.pi-supply.com/products/pijuice-standard) / [PiJuice Zero](https://uk.pi-supply.com/products/pijuice-zero)
- SD card
  - youw own (over 8GB)
  - [SanDisk® High Endurance microSD™ Card](https://shop.westerndigital.com/products/memory-cards/sandisk-high-endurance-uhs-i-microsd#SDSQQNR-032G-AN6IA) is recommended if you use several years.
- Case
  - make a nice case if you can use 3D printer.
  - [Topeak SMARTPHONE DRYBAG 5"](https://www.topeak.com/global/en/products/weatherproof-ridecase-series/1092-smartphone-drybag-5%22) is easy to use. It is waterproof.


# Assembly

Coming soon!


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
Pyqt version 5.15.0 in macOS has [a qpushbutton issue](https://bugreports.qt.io/browse/QTBUG-84852), so installing version 5.14.2 is recommended.


```
$ pip3 install PyQt5==5.14.2
```

## Raspberry Pi OS

Assume Raspberry Pi OS (32-bit) with desktop, not Raspberry Pi OS (32-bit) Lite. I haven't checked the procedure in Lite, but in the future I will try minimum OS such as Lite or buildroot.

Also, your Raspberry Pi is connected to internet and updated with `apt-get update & apt-get upgrade`.

Here is [my setup guide in Japanese](https://qiita.com/hishi/items/8bdfd9d72fa8fe2e7573).

### Common

```
$ git clone https://github.com/hishizuka/pizero_bikecomputer.git
$ sudo apt-get install python3-pip cython3 cmake gawk python3-numpy python3-pyqt5
$ sudo pip3 install oyaml
$ sudo apt-get install wiringpi python3-smbus python3-rpi.gpio python3-psutil python3-pil
$ sudo pip3 install git+https://github.com/hishizuka/pyqtgraph.git
$ cd pizero_bikecomputer
```

### GPS module

#### UART GPS

Assume UART interface is on and login over serial is off in raspi-config.

```
$ sudo apt-get install python3-tz gpsd gpsd-clients python3-dateutil
$ sudo pip3 install gps3 timezonefinder 
$ sudo cp install/etc/default/gpsd /etc/default/gpsd
$ sudo systemctl enable gpsd
```

#### I2C GPS (experimental)

Assume I2C interface is on in raspi-config.

```
$ sudo apt-get install python3-tz python3-dateutil
$ sudo pip3 install timezonefinder adafruit-circuitpython-gps
```


### USB ANT+ dongle

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
$ sudo chmod 755 /usr/local/bin/disable-pitft
$ sudo cp install/usr/local/bin/enable-pitft /usr/local/bin/
$ sudo chmod 755 /usr/local/bin/enable-pitft
```

Install the program which turns off the backlight at shutdown.

```
$ sudo cp install/etc/systemd/system/disable-pitft.service /etc/systemd/system/
$ sudo systemctl daemon-reload
$ sudo systemctl enable disable-pitft.service
```

##### run on X Window

Making launcher menu or desktop icon may be useful.

![lancher menu](https://qiita-user-contents.imgix.net/https%3A%2F%2Fqiita-image-store.s3.ap-northeast-1.amazonaws.com%2F0%2F100741%2Fc466c6f0-ede8-5de2-2061-fbbbcccb93fc.png?ixlib=rb-1.2.2&auto=format&gif-q=60&q=75&w=1400&fit=max&s=864176ddffe3895226a6fd8bf20fb4d0)

##### run on console

You need building Qt5 and PyQt5 because the package python3-pyqt5 provided with Raspbian OS does not include a touchscreen library(tslib).

###### Build Qt

Follow [this article](https://www.tal.org/tutorials/building-qt-512-raspberry-pi) with Raspberry Pi 4 4GB or 8GB. Use the compile option "-platform linux-rpi-g++" for Raspberry Pi 1 or zero, not use options for Raspberry Pi 4 and so on.
Use the same SD card on Raspberry Pi 4.

##### Build PyQt5

Follow [PyQt Reference Guide](https://www.riverbankcomputing.com/static/Docs/PyQt5/installation.html).

```
$ sudo pip3 install sip
$ sudo pip3 install PyQt-builder
$ sip-build --no-make --qmake PATH-TO-YOUR-QMAKE
$ make -j4
$ sudo make install
$ sudo pip3 install PyQt5-sip
```

#### MIP Reflective color LCD module

```
$ sudo apt-get install python3-spidev python3-pigpio
$ sudo pip3 install spidev --upgrade
```

#### E-ink Displays

##### PaPiRus ePaper / eInk Screen HAT for Raspberry Pi

Follow [official setup guide](https://github.com/PiSupply/PaPiRus)

##### DFRobot e-ink Display Module for Raspberry Pi 4B/3B+/Zero W

Follow [official setup guide](https://wiki.dfrobot.com/Raspberry_Pi_e-ink_Display_Module_SKU%3A_DFR0591) and install manually.

### Common

If you use displays in console environment not X Window, install auto-run service and shutdown service.

#### auto-run service

```
$ sudo cp install/etc/systemd/system/pizero_bikecomputer.service /etc/systemd/system/
$ sudo cp install/etc/systemd/system/pizero_bikecomputer_shutdown.service /etc/systemd/system/
$ sudo systemctl daemon-reload
$ sudo systemctl enable pizero_bikecomputer_shutdown.service
```

#### shutdown service

```
$ sudo cp install/usr/local/bin/pizero_bikecomputer_shutdown /usr/local/bin/
$ sudo chmod 755 /usr/local/bin/pizero_bikecomputer_shutdown
$ sudo cp install/etc/systemd/system/pizero_bikecomputer_shutdown.service /etc/systemd/system/
$ sudo systemctl daemon-reload
```

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
| [Adafruit](https://www.adafruit.com) | [VCNL4040](https://www.adafruit.com/product/4161) | adafruit-circuitpython-vcnl4040 |

*1 Install manually https://github.com/spacecraft-design-lab-2019/CircuitPython_BMX160


#### Button SHIM

```
$ sudo apt-get install buttonshim
```

#### PiJuice HAT

Follow [official setup guide](https://github.com/PiSupply/PiJuice/tree/master/Software) of PiSupply/PiJuice


# Quick Start

## normal mode

```
$ python3 pizero_bikecomputer.py
```

## demo mode

```
$ python3 pizero_bikecomputer.py --demo
```

Temporarily use with map downloading. A course file is required(see [Usage](Usage)). After launching the program, go to the map screen.

# Usage


# Q&A


# License

This repository is available under the [GNU General Public License v3.0](https://github.com/hishizuka/pizero_bikecomputer/blob/master/LICENSE)

# Author

[hishizuka](https://github.com/hishizuka/) ([@pi0bikecomputer](https://twitter.com/pi0bikecomputer) at twitter)
