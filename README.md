![title](https://user-images.githubusercontent.com/12926652/73185921-4c3eb580-4162-11ea-863a-d7d973150ecf.png)

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

![image](https://qiita-user-contents.imgix.net/https%3A%2F%2Fqiita-image-store.s3.ap-northeast-1.amazonaws.com%2F0%2F100741%2Fa6746d2f-bae0-a511-f6e7-972d4c6bc592.png?ixlib=rb-1.2.2&auto=format&gif-q=60&q=75&w=1400&fit=max&s=a8197e8537ebdd4fcd490776442855c7)


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
  - [PaPiRus ePaper / eInk Screen HAT for Raspberry Pi](https://uk.pi-supply.com/products/papirus-epaper-eink-screen-hat-for-raspberry-pi) or [e-ink Display Module for Raspberry Pi 4B/3B+/Zero W](https://www.dfrobot.com/product-1866.html)
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
  - pressure: need for altitude, grade, and total ascent/descent
    - [BMP280](https://shop.pimoroni.com/products/enviro-phat) (\*1)
    - [BMP38X](https://www.dfrobot.com/product-1928.html)
    - [LPS33HW](https://www.adafruit.com/product/4414) (\*1)
  - IMU: need for start and stop detection when using GPS.
    - [LSM303](https://shop.pimoroni.com/products/enviro-phat) (\*1); 
    - [LSM6DS](https://www.adafruit.com/product/4485): Accel / Gyro
    - [LSM9DS1](https://www.sparkfun.com/products/13944): Accel / Gyro / Mag 
    - [LIS3MDL](https://www.adafruit.com/product/4485): Mag 
    - [BMX160](https://www.dfrobot.com/product-1928.html): Accel / Gyro / Mag
  - lux: need for auto backlight when using MIP Reflective color LCD
    - [TCS3472](https://shop.pimoroni.com/products/enviro-phat)
    - [VCNL4040](https://www.adafruit.com/product/4161)
  - button: need for displays which don't have buttons like MIP display.
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


# Installation

Assume python3 environment.

Also, Raspberry Pi is connected to internet and updated with `apt-get update & apt-get upgrade`.

```
$ git clone https://github.com/hishizuka/pizero_bikecomputer.git
$ pip3 install PyQt5 numpy oyaml pillow
$ pip3 install git+https://github.com/hishizuka/pyqtgraph.git
```

# Quick Start

## normal mode

```
$ python3 pizero_bikecomputer.py
```

## demo mode

```
$ python3 pizero_bikecomputer.py --demo
```

Temporarily use with map downloading. Course file is required(see [Usage](Usage)). After launching the program, go to the map screen.

# Usage


# Q&A


# License

This repository is available under the [GNU General Public License v3.0](https://github.com/hishizuka/pizero_bikecomputer/blob/master/LICENSE)

# Author

[hishizuka](https://github.com/hishizuka/) ([@pi0bikecomputer](https://twitter.com/pi0bikecomputer) at twitter)
