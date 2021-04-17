![title](https://user-images.githubusercontent.com/12926652/89370669-47178000-d71c-11ea-896f-0d98f4cbd5da.jpg)

# Pi Zero Bikecomputer
An open-source bike computer based on  Raspberry Pi Zero (W, WH) with GPS and ANT+

# News

- 2021/4/3 Please reinstall openant and pyqtgraph because both libraries are re-forked.

```
$ sudo pip3 uninstall pyqtgraph
$ sudo pip3 install git+https://github.com/hishizuka/pyqtgraph.git
$ sudo pip3 uninstall openant
$ sudo pip3 install git+https://github.com/hishizuka/openant.git
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


# Abstract

Pi Zero Bikecomputer is a GPS and ANT+ bike computer based on Raspberry Pi Zero(W, WH). This is the first DIY project in the world integrated with necesarry hardwares and softwares for modern bike computer. It measures and records position(GPS), ANT+ sensor(speed/cadence/power) and I2C sensor(pressure/temperature/accelerometer, etc). It also displays these values, even maps and courses in real-time. In addition, it write out log into .fit format file.

In this project, Pi Zero Bikecomputer got basic functions needed for bike computers. Next target is to add new functions which existing products do not have!

You will enjoy both cycling and the maker movement with Pi Zero Bikecomputer!

Here is detail articles in Japanese.

- [I tried to make a bikecomputer, the result was pretty good](https://qiita.com/hishi/items/46619b271daaa9ad41b3)
- [Let's make a bikecomputer with Raspberry Pi Zero (W, WH)](https://qiita.com/hishi/items/46619b271daaa9ad41b3)

Daily update [at twitter (@pi0bikecomputer)](https://twitter.com/pi0bikecomputer), and [my cycling activity at STRAVA](https://www.strava.com/athletes/40248693).


<img width="836" alt="system-01" src="https://user-images.githubusercontent.com/12926652/97240630-1d10be00-1832-11eb-9ce2-762d23419152.png">

<img width="836" alt="system-02" src="https://user-images.githubusercontent.com/12926652/97240633-23069f00-1832-11eb-8e8b-8312997b4710.png">


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

## General

| Specs | Detail | Note |
|:-|:-|:-|
| Logging | Yes | See as below |
| Sensors | Yes | See as below |
| Positioning | Yes | A GPS module is required. See as below. |
| GUI | Yes | See as below |
| Wifi | Yes | Built-in wifi |
| Battery life(Reference) | 18h | with 3100mAh mobile battery([Garmin Charge Power Pack](https://buy.garmin.com/en-US/US/p/571552)) and MIP Reflective color LCD. |

## Logging

| Specs | Detail | Note |
|:-|:-|:-|
| Stopwatch | Yes | Timer, Lap, Lap timer |
| Lap | Yes | [Total, Lap ave, Pre lap ave] x [HR, Speed, Cadence, Power] |
| Cumulative value | Yes | [Total, Lap, Pre lap] x [Distance, Works, Ascent, Descent] |
| Elapsed time | Yes | Elapsed time, average speed(=distance/elapsed time), gained time from average speed 15km/h(for brevet) |
| Auto stop | Yes | Automatic stop at speeds below 4km/h(configurable), or in the state of the acceleration sensor when calculating the speed by GPS alone |
| Recording insterval | 1s |  Smart recording is not supported. |
| Resume | Yes |  |
| Output .fit log file | Yes |  |
| Upload to STRAVA | Yes |  |
| Live sending | Yes | But I can't find a good dashboard service like as Garmin LiveTrack |

## Sensors

USB dongle is required if using ANT+ sensors.

| Specs | Detail | Note |
|:-|:-|:-|
| ANT+ heartrate sensor |  Yes | |
| ANT+ speed sensor |  Yes | |
| ANT+ cadence sensor |  Yes | |
| ANT+ speed&cadence sensor |  Yes | |
| ANT+ powermeter |  Yes | Calibration is not supported. |
| ANT+ LIGHT |  Yes | Bontrager Flare RT only. |
| ANT+ Control |  Yes | Garmin Edge Remote only. |
| Bluetooth sensors |  No |  |
| Barometric altimeter | Yes | An I2c sensor(pressure, temperature) is required. |
| Accelerometer | Yes | An I2c sensor is required. |
| Magnetometer | Yes | An I2c sensor is required. |
| Light sensor | Yes | An I2c sensor is required. |

## Positioning

| Specs | Detail | Note |
|:-|:-|:-|
| Map | Yes | Support map tile format like OSM. So, offline map is available with local caches. |
| Course on the map| Yes | A course file(.tcx) is required. |
| Course profile | Yes | A course file(.tcx) is required. |
| Cuesheet | Yes | Use course points included in course files. |
| Search Route | Yes | Google Directions API |

- Map with [Toner Map](http://maps.stamen.com/)
  - Very useful with 2 colors displays (black and white).
  - <img src ="https://camo.qiitausercontent.com/0c2cf8d528b613a4665aa62170e2e9ee4a8ab90a/68747470733a2f2f71696974612d696d6167652d73746f72652e73332e61702d6e6f727468656173742d312e616d617a6f6e6177732e636f6d2f302f3130303734312f38623335636566652d663836302d643662662d396366642d3963633336643561313863622e706e67" width=320 height=240 />
- Map with custimized [Mapbox](https://www.mapbox.com)
  - Use 8 colors suitable for MIP Reflective color LCD.
  - <img src ="https://camo.qiitausercontent.com/3dde7fcb864f8226c23332a30c33ab743b0b2b06/68747470733a2f2f71696974612d696d6167652d73746f72652e73332e61702d6e6f727468656173742d312e616d617a6f6e6177732e636f6d2f302f3130303734312f66663366353439362d373266642d353831352d656533332d3437303862623364323565392e706e67" width=320 height=240 />
- Course profile
  -  <img src ="https://camo.qiitausercontent.com/e2d197a1cb6fea4341a8bc7dfd89be86dab3d784/68747470733a2f2f71696974612d696d6167652d73746f72652e73332e61702d6e6f727468656173742d312e616d617a6f6e6177732e636f6d2f302f3130303734312f33393064333061652d653765632d623738652d346365322d3036303232313433663566612e706e67" width=320 height=240 />


## GUI

| Specs | Detail | Note |
|:-|:-|:-|
| Basic page(values only) | Yes |  |
| Graph | Yes | Altitude and performance(HR, PWR) |
| Customize data pages | Yes | With layout.yaml |
| ANT+ pairing | Yes |  |
| Adjust wheel size | Yes | Set once, store values |
| Adjust altitude | Yes | Auto adjustments can be made only once, if on the course. |
| Language localization | Yes | Font and translation file of items are required. |
| No GUI option | Yes | headless mode |


- Performance graph
  - <img src ="https://camo.qiitausercontent.com/05c8c8facf076fbc3faf6abe848493ac0e82ffc1/68747470733a2f2f71696974612d696d6167652d73746f72652e73332e61702d6e6f727468656173742d312e616d617a6f6e6177732e636f6d2f302f3130303734312f39316336643837382d666436632d383262652d663638642d6533303531323832356631662e706e67" width=320 height=240 />
- Language localization（Japanese)
  - <img src ="https://user-images.githubusercontent.com/12926652/90345269-3808ca00-e05a-11ea-91fe-42efbcd6040b.png" width=320 height=310 />


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

See [hardware_installation.md](/hardware_installation.md).

# Software Installation

See [software_installation.md](/software_installation.md).

# Q&A


# License

This repository is available under the [GNU General Public License v3.0](https://github.com/hishizuka/pizero_bikecomputer/blob/master/LICENSE)

# Author

[hishizuka](https://github.com/hishizuka/) ([@pi0bikecomputer](https://twitter.com/pi0bikecomputer) at twitter, [pizero bikecomputer](https://www.strava.com/athletes/40248693) at STRAVA)
