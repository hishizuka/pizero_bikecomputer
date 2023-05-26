![title](https://user-images.githubusercontent.com/12926652/89370669-47178000-d71c-11ea-896f-0d98f4cbd5da.jpg)

# Pi Zero Bikecomputer
An open-source bike computer based on  Raspberry Pi Zero (W, WH, 2 W) with GPS and ANT+.

https://github.com/hishizuka/pizero_bikecomputer

# News

- 2023/5/26 There are so many updates, so you might want to look over [software_installation.md](/doc/software_installation.md)..
- 2023/5/26 Install dbus-next and bluez-peripheral if you want to link your Android smartphone. [GadgetBridge](https://gadgetbridge.org) is also required, which can mirror Android notifications and get location without GPS modules.
- 2023/5/26 Install tb-mqtt-client if you want to send [ThingsBoard](https://thingsboard.io), which is an online dashboard. You can share your location in the map with your course or track.

```
#2023/5/26 update
$ sudo pip3 install dbus-next bluez-peripheral
$ sudo pip3 install tb-mqtt-client
```


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

| Specs | Detail | Note |
|:-|:-|:-|
| Logging | Yes |  |
| Sensors | Yes |  |
| Positioning | Yes | A GPS module is supported. |
| GUI | Yes |  |
| Wifi | Yes | Built-in wifi |
| Battery life(Reference) | 18h | with 3100mAh mobile battery([Garmin Charge Power Pack](https://buy.garmin.com/en-US/US/p/571552)) and MIP Reflective color LCD. |

## Logging

| Specs | Detail | Note |
|:-|:-|:-|
| Stopwatch | Yes | Timer, Lap, Lap timer |
| Lap | Yes | [Total, Lap ave, Pre lap ave] x [HR, Speed, Cadence, Power] |
| Cumulative value | Yes | [Total, Lap, Pre lap] x [Distance, Works, Ascent, Descent] |
| Gross | Yes | Elapsed time, gross average speed(=distance/elapsed time), gained time from average speed 15km/h(for brevet) |
| Auto stop | Yes | Automatic stop at speeds below 4km/h(configurable), or in the state of the acceleration sensor when calculating the speed by GPS alone |
| Recording insterval | 1s |  Smart recording is not supported. |
| Resume | Yes |  |
| Output .fit log file | Yes |  |
| Upload | Yes | Strava, Garmin and Ride with GPS. |
| Live sending | Suspend | I am looking for a good dashboard service like as Garmin LiveTrack |

## Sensors

USB dongle is required if using ANT+ sensors.

| Specs | Detail | Note |
|:-|:-|:-|
| ANT+ Heartrate sensor |  Yes | |
| ANT+ Speed sensor |  Yes | |
| ANT+ Cadence sensor |  Yes | |
| ANT+ Speed&Cadence sensor |  Yes | |
| ANT+ Powermeter |  Yes | Calibration is not supported. |
| ANT+ LIGHT |  Yes | Bontrager Flare RT only. |
| ANT+ Control |  Yes | Garmin Edge Remote only. |
| ANT+ Environment |  Yes | Garmin tempe (temperature sensor) |
| Bluetooth sensors |  No |  |
| Barometric altimeter | Yes | I2c sensor(pressure, temperature) |
| Accelerometer | Yes | I2c sensor |
| Magnetometer | Yes | I2c sensor |
| Light sensor | Yes | I2c sensor. Use for auto backlight and lighting. |

## Positioning

| Specs | Detail | Note |
|:-|:-|:-|
| Map | Yes | Support raster map tile format like OSM (z/x/y.png or jpg). So, offline map is available with local caches. Also, raster .mbtile format is supported. |
| Course on the map| Yes | Local file(.tcx), Ride with GPS. |
| Search route | Yes | Google Directions API |
| Course profile | Yes |  |
| Detect climbs | Yes |  |
| Cuesheet | Yes | Use course points included in course files. |
| Map overlay | Yes | Heatmap (Strava / Ride with GPS) and weather(rain / wind). |

### Map example


#### Map and Course Profile with climb segments

<img width="400" alt="map-01" src="https://user-images.githubusercontent.com/12926652/206341071-5f9bee00-d959-489b-832a-9b4bf7fe2279.png"> <img width="400" alt="map-02" src="https://user-images.githubusercontent.com/12926652/206341086-7935cfbd-8ed3-4068-9f2b-93f676a8932a.png">

#### Heatmap overlay

Strava heatmap.

![map_overlay-strava](https://user-images.githubusercontent.com/12926652/205793586-0b754cde-d1e7-4e57-81d2-2bbd60fc8b11.png)

#### Weather map overlay

[RainViewer](https://www.rainviewer.com/weather-radar-map-live.html) and [openportguide](http://weather.openportguide.de/map.html) are available worldwide.

In Japan, [気象庁降水ナウキャスト](https://www.jma.go.jp/bosai/nowc/)(rain) and [SCW](https://supercweather.com)(wind) are available.

![map_overlay_rainviewer](https://user-images.githubusercontent.com/12926652/205876664-ae1b629c-5b3f-4d8a-b789-d3ac24753d7f.png) ![map_overlay_weather openportguide de](https://user-images.githubusercontent.com/12926652/205876684-253b672f-615d-410c-8496-5eb9a13b2558.png)

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
| Select map | Yes | map and overlay(heatmap and weather) |
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

- <img src="https://camo.qiitausercontent.com/97904ae429c191677e9ece3cd113e07dfe8eefb2/68747470733a2f2f71696974612d696d6167652d73746f72652e73332e61702d6e6f727468656173742d312e616d617a6f6e6177732e636f6d2f302f3130303734312f33383765663432332d346631642d623332352d666235642d6638623434646332396564362e6a706567" width=320 />


# Comparison with other bike computers

- 200km ride with Garmin Edge 830 and Pizero Bikecomputer ([strava activity](https://www.strava.com/activities/2834588492))

- ![title-03.png](https://qiita-image-store.s3.ap-northeast-1.amazonaws.com/0/100741/b355cb92-8e7f-6b3f-7cd0-98ba8803a56c.png)

| Items | Edge830 | Pi Zero Bikecomputer |
|:-:|:-:|:-:|
| Distance | 193.8 km  | 194.3 km  |
| Work |  3,896 kJ | 3,929 kJ  |
| Moving time | 9:12 | 9:04  |
| Total Ascent | 2,496 m | 2,569 m |

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