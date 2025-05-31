![title](https://user-images.githubusercontent.com/12926652/89370669-47178000-d71c-11ea-896f-0d98f4cbd5da.jpg)

# Pi Zero Bikecomputer
An open-source bike computer based on  Raspberry Pi Zero (W, WH, 2 W) with GPS and ANT+.

https://github.com/hishizuka/pizero_bikecomputer

# News
- 2025/3/17 PCBs are under development.
  - <img width="320" alt="4inch-01" src="https://github.com/user-attachments/assets/d31f1cd3-5472-47b1-8995-1efe8fb5ef97" /> <img width="320" alt="4inch-02" src="https://github.com/user-attachments/assets/87afa6c3-ba28-4dbc-970b-e3c7c9a55806" /> <img width="320" alt="4inch-03" src="https://github.com/user-attachments/assets/3b9528d5-9e02-437a-a13f-2607aac2f90d" />
- 2024/6/21 Changed the value for `display` in `setting.conf` when using JDI/Sharp MIP LCD. See `modules/display/display_core.py` for setting values.
  - `MIP_JDI_color_400x240`
  - `MIP_JDI_color_640x480`
  - `MIP_Azumo_color_272x451` (WIP)
  - `MIP_Sharp_mono_400x240`
  - `MIP_Sharp_mono_320x240`
- 2024/6/21 Vertical layouts is available. Set from the initial display resolution at startup. If you want to try it in a desktop environment, change `DEFAULT_RESOLUTION` in `modules/display/display_core.py`. For individual hardware displays, specify the appropriate value.
  - ![verticai-layout-01](https://github.com/hishizuka/pizero_bikecomputer/assets/12926652/ac7f2000-68ec-4f89-a1f5-afd71aacd173) ![verticai-layout-02](https://github.com/hishizuka/pizero_bikecomputer/assets/12926652/e4b67398-455c-40cd-80fd-f8ec05c155a0)

## Stargazers over time
[![Stargazers over time](https://starchart.cc/hishizuka/pizero_bikecomputer.svg?variant=adaptive)](https://starchart.cc/hishizuka/pizero_bikecomputer)

# Table of Contents

- [Abstract](#abstract)
- [Features](#features)
- [Specs](#Specs)
- [Comparison with other bike computers](#comparison)
- [Hardware Installation](#hardware-installation)
- [Software Installation](#software-installation)
- [Q&A](#qa)
- [License](#License)
- [Author](#Author)
- [Link](#Link)


# Abstract

Pi Zero Bikecomputer is a GPS and ANT+ bike computer based on Raspberry Pi Zero(W, WH, 2 W). This is the first DIY project in the world integrated with necessary hardwares and software for modern bike computer. It measures and records position(GPS), ANT+ sensor(speed/cadence/power) and I2C sensor(pressure/temperature/accelerometer, etc). It also displays these values, even maps and courses in real-time. In addition, it write out log into .fit format file.

In this project, Pi Zero Bikecomputer got basic functions needed for bike computers. Next target is to add new functions which existing products do not have!

You will enjoy both cycling and the maker movement with Pi Zero Bikecomputer!

Here is detail articles in Japanese.

- [I tried to make a bikecomputer, the result was pretty good](https://qiita.com/hishi/items/46619b271daaa9ad41b3)
- [Let's make a bikecomputer with Raspberry Pi Zero (W, WH)](https://qiita.com/hishi/items/46619b271daaa9ad41b3)

Daily update [at twitter (@pi0bikecomputer)](https://twitter.com/pi0bikecomputer), and [my cycling activity at STRAVA](https://www.strava.com/athletes/40248693).


<img width="836" alt="system-01-202106" src="https://user-images.githubusercontent.com/12926652/120964687-a6ac4500-c79e-11eb-8598-98ab2e612cd6.png">


<img width="836" alt="system-02" src="https://user-images.githubusercontent.com/12926652/97240633-23069f00-1832-11eb-8e8b-8312997b4710.png">

![hardware_top](https://user-images.githubusercontent.com/12926652/205796409-f0ef443a-d1d1-4daa-abdd-4f20748c83e9.png)


# Features

- Easy to make
  - Use modules available at famous Maker stores.
  - Assemble in Raspberry Pi ecosystems.
  - Install with basic commands such as `apt-get install`, `pip` and `git` command.

- Customization
  - Need only modules you want to use. Pi Zero Bikecomputer detects your modules.

- Easy to develop
  - Pi Zero Bikecomputer uses same libraries as for standard Linux.
    - [Python](https://www.python.org)
    - [numpy](https://numpy.org)
    - [PyQt5](https://pypi.org/project/PyQt5/) and [PyQtGraph](http://www.pyqtgraph.org)
    - [GPSd](https://gpsd.gitlab.io/gpsd/index.html) for GPS modules.
    - [CircuitPython](https://learn.adafruit.com/welcome-to-circuitpython/what-is-circuitpython) libraries for some I2C sensors. 
  - So, you can run in cross platform environments such as Raspberry Pi OS, some Linux, macOS and Windows.

- Good balance between battery life and performance


# Specs

Some functions depend on your parts.

## Summary

| Specs | Support | Detail |
|:-|:-|:-|
| Logging | Yes | See below. |
| Sensors | Yes | ANT+ sensors and I2C sensors. See below. |
| Maps and navigations | Yes | A GPS module or the Android app [GadgetBridge](https://gadgetbridge.org) is required. See below. |
| GUI | Yes | Implemented using PyQt. See below. |
| Wifi & Bluetooth | Yes | Using built-in modules.|
| Smartphone connections | Yes | Android only. Mirroring notifications and getting locations via [GadgetBridge](https://gadgetbridge.org).|
| Battery life(Reference) | 18h | with 3100mAh mobile battery([Garmin Charge Power Pack](https://buy.garmin.com/en-US/US/p/571552)) and MIP Reflective color LCD. |

## Logging

| Specs | Support | Detail |
|:-|:-|:-|
| Stopwatch | Yes | Timer, Lap, Lap timer |
| Average value | Yes | [Total, Lap ave, Pre lap ave] x [HR, Speed, Cadence, Power], [3s, 30s, 60s] x [HR, Power] |
| Cumulative value | Yes | [Total, Lap, Pre lap] x [Distance, Works, Ascent, Descent] |
| Gross | Yes | Elapsed time, gross average speed(=distance/elapsed time), gained time from average speed 15km/h(for brevet) |
| Auto stop | Yes | Automatic stop at speeds below 4km/h(configurable), or in the state of the acceleration sensor when calculating the speed by GPS alone |
| Recording insterval | 1s |  Smart recording is not supported. |
| Resume | Yes | Recording continues even if the power is suddenly turned off and restored. |
| Output .fit log file | Yes | The standard format used by famous services as Strava and Garmin Connect. Also .csv format output is supported. |
| Upload | Yes | Strava, Garmin and Ride with GPS. |
| Live Track | Yes | Track data is uploaded in real time to [ThingsBoard.io](http://thingsboard.io) dashboard service, so you can share your activity with friends and family. |

### Dashboard(ThingsBoard) example

<img alt="thingsboard-01" src="https://github.com/hishizuka/pizero_bikecomputer/assets/12926652/c3df419f-4392-4d83-96ab-1f15508b3605"> <img alt="thingsboard-02" src="https://github.com/hishizuka/pizero_bikecomputer/assets/12926652/a72ffb58-2fa8-4a87-b9d7-0ba67aa3cfde">


## Sensors

USB dongle is required if using ANT+ sensors.

| Specs | Support | Detail                                           |
|:-|:-|:-------------------------------------------------|
| ANT+ Heartrate sensor |  Yes |                                                  |
| ANT+ Speed sensor |  Yes |                                                  |
| ANT+ Cadence sensor |  Yes |                                                  |
| ANT+ Speed&Cadence sensor |  Yes |                                                  |
| ANT+ Powermeter |  Yes | Calibration is not supported.                    |
| ANT+ Light |  Yes | Bontrager Flare RT only.                         |
| ANT+ Control |  Yes | Garmin Edge Remote only.                         |
| ANT+ Environment |  Yes | Garmin tempe (temperature sensor)                |
| Bluetooth sensors |  No | developing now...                                |
| Barometric altimeter | Yes | I2C sensor(pressure, temperature)                |
| Accelerometer | Yes | I2C sensor                                       |
| Magnetometer | Yes | I2C sensor                                       |
| Light sensor | Yes | I2C sensor. Use for auto backlight and lighting. |

## Maps and navigations

| Specs | Support | Detail |
|:-|:-|:-|
| GPS module | Yes | UART GPS module(via GPSd) and I2C GPS are supported. |
| Positioning from smartphones | Yes | Using the Android app [GadgetBridge](https://gadgetbridge.org). |
| Map | Yes | Support raster map tile format like OSM (z/x/y.png or jpg). So, offline map is available with local caches. Also, raster .mbtile format is supported. |
| Course on the map| Yes | Local file(.tcx), or cloud course from Ride with GPS with internet connection. |
| Search route | Yes | Google Directions API |
| Course profile | Yes |  |
| Detect climbs | Yes | Like Garmin ClimbPro. Only climbs on the course, not detect nearby climbs. |
| Cuesheet | Yes | Use course points included in course files(.tcx). |
| Map overlay | Yes | Heatmap (Strava / Ride with GPS) and weather(rain / wind). |

### Map example

#### Map and Course Profile with detecting climbs.

<img width="400" alt="map-01" src="https://user-images.githubusercontent.com/12926652/206341071-5f9bee00-d959-489b-832a-9b4bf7fe2279.png"> <img width="400" alt="map-02" src="https://user-images.githubusercontent.com/12926652/206341086-7935cfbd-8ed3-4068-9f2b-93f676a8932a.png">

#### Heatmap overlay

Strava heatmap.

![map_overlay-strava](https://user-images.githubusercontent.com/12926652/205793586-0b754cde-d1e7-4e57-81d2-2bbd60fc8b11.png)

#### Weather map overlay

[RainViewer](https://www.rainviewer.com/weather-radar-map-live.html) and [openportguide](http://weather.openportguide.de/map.html) are available worldwide.

![map_overlay_rainviewer](https://user-images.githubusercontent.com/12926652/205876664-ae1b629c-5b3f-4d8a-b789-d3ac24753d7f.png) ![map_overlay_weather openportguide de](https://user-images.githubusercontent.com/12926652/205876684-253b672f-615d-410c-8496-5eb9a13b2558.png)

In Japan, [気象庁降水ナウキャスト](https://www.jma.go.jp/bosai/nowc/)(rain) and [SCW](https://supercweather.com)(wind) are available.

<img src ="https://user-images.githubusercontent.com/12926652/205563333-549cf4dc-abbd-4392-9233-b8391687e0bc.png" width=400/> 


## GUI

| Specs | Detail | Note |
|:-|:-|:-|
| Basic page(values only) | Yes |  |
| Graph | Yes | Altitude and performance(HR, PWR, W prime balance) |
| Customize data pages | Yes | With layout.yaml |
| ANT+ pairing | Yes |  |
| Select course | Yes | local .tcx file and Ride with GPS. |
| Upload activity | Yes | Strava, Garmin and Ride with GPS. |
| Select map | Yes | maps and overlays(heatmap and weather) |
| Adjust parameter | Yes | wheel size, altitude, CP and W prime balance |
| Network setting | Yes | Toggle wifi and BT, BT tethering. |
| Language localization | Yes | Font and translation file of items are required. |
| No GUI option | Yes | headless mode |


### Performance graph
![performance_graph-01](https://user-images.githubusercontent.com/12926652/205787731-6a249ccf-8115-433d-a4d1-7f068a804972.jpeg)

### Language localization（Japanese)
![language-ja](https://user-images.githubusercontent.com/12926652/205787136-ed87e959-ff54-48ac-835f-a1b337b77b87.png)


## Experimental functions

### ANT+ multiscan

it displays three of the people around you in the order in which you caught sensors using ANT+ continuous scanning mode.

- <img src="https://qiita-user-contents.imgix.net/https%3A%2F%2Fqiita-image-store.s3.ap-northeast-1.amazonaws.com%2F0%2F100741%2F387ef423-4f1d-b325-fb5d-f8b44dc29ed6.jpeg?ixlib=rb-4.0.0&auto=format&gif-q=60&q=75&s=3460d1b3a5a96ac9b4effd7c4fd7767e" width=320 />


# Comparison with other bike computers

- 314km ride with GARMIN Edge Explore 2 and Pizero Bikecomputer ([strava activity](https://www.strava.com/activities/9618771273))

- ![2023_TOJ_compare](https://github.com/hishizuka/pizero_bikecomputer/assets/12926652/9fa9a34f-b153-44a6-a718-30c61be84b41)

| Items | Edge830 | Pi Zero Bikecomputer |
|:-:|:-:|:-:|
| Distance | 313.7 km  | 314.3 km  |
| Work |  3,889 kJ | 3,926 kJ  |
| Moving time | 12:03 | 12:04  |
| Total Ascent | 2,271 m | 1,958 m |

# Hardware Installation

See [hardware_installation.md](/doc/hardware_installation.md).

# Software Installation

See [software_installation.md](/doc/software_installation.md).

# Q&A


# License

This repository is available under the [GNU General Public License v3.0](https://github.com/hishizuka/pizero_bikecomputer/blob/master/LICENSE)

# Author

[hishizuka](https://github.com/hishizuka/) ([@pi0bikecomputer](https://twitter.com/pi0bikecomputer) at twitter, [pizero bikecomputer](https://www.strava.com/athletes/40248693) at STRAVA)

# Link

[Maker Faire Tokyo 2020 - Raspberry Pi Zero Cyclecomputer](https://makezine.jp/event/makers-mft2020/m0016/)

[HACKADAY - DEVELOPING AN OPEN SOURCE BIKE COMPUTER](https://hackaday.com/2023/01/06/developing-an-open-source-bike-computer/)
