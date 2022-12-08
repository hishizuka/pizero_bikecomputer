[Back to README.md](../README.md)

# Table of Contents

- [Parts List](#parts-list)
  - [Display](#display)
  - [GPS module](#gps-module)
  - [I2C sensors](#i2c-sensors)
  - [ANT+ USB dongle](#ant+-usb-dongle)
  - [SD card](#sd-card)
  - [Case](#case)
- [Hardware Assembly](#hardware-assembly)
  - [Displays with headers](#displays-with-headers-pitft-or-e-ink-displays)
  - [Displays with non headers](#displays-without-headers-mip-reflective-color-lcd-and-sharp-memory-display)
- [Bicycle mounting](#bicycle-mounting)


# Parts List

## [Raspberry Pi Zero W / WH](https://www.raspberrypi.org/products/raspberry-pi-zero-w/), [Raspberry Pi Zero 2 W](https://www.raspberrypi.com/products/raspberry-pi-zero-2-w/)

<img src ="https://qiita-user-contents.imgix.net/https%3A%2F%2Fqiita-image-store.s3.amazonaws.com%2F0%2F100741%2F41773d64-fc33-cc2a-190a-ce14b7b6b24c.png?ixlib=rb-1.2.2&auto=format&gif-q=60&q=75&w=1400&fit=max&s=393a8049c6f10a90dc8cc1f6e2030426" height=360 />

## Display

### [MIP Reflective color LCD module 2.7" w/ backlight (LPM027M128C)](https://international.switch-science.com/catalog/5395/) 

[Connection board for MIP Reflective color LCD to FRDM-K64F](https://international.switch-science.com/catalog/5393/) (MIP Interface Board) is also needed

Pros&Cons

- (good) very visible even in direct sunshine
- (good) ultra-low power consumption
- (good) backlight
- (bad) very expensive ($170, Alternatives: $100~)
- (bad) 8 colors only (but can use more colors with dithering)
- Recommend if you don't think costs. Commercial products often uses a reflective LCD.

- <img src="https://user-images.githubusercontent.com/12926652/206317535-71345000-8dfa-4051-a674-15e21afb4203.jpeg" width=480 />

Alternatives: 
- [Aliexpress New LPM027M128B LPM027M128C LTPS TFT-LCD, LCM 2.7 inch 400X240 display](https://ja.aliexpress.com/item/1005002351792191.html?spm=a2g0o.productlist.0.0.52452576NqqM6z&algo_pvid=ba698ed0-3580-48fa-8fdc-b7774c4c9cf0&algo_expid=ba698ed0-3580-48fa-8fdc-b7774c4c9cf0-0&btsid=0bb0623116212468747683928ed47e&ws_ab_test=searchweb0_0,searchweb201602_,searchweb201603_)
- [WAHOO ELEMNT ROAM screen replacement](https://ja.aliexpress.com/item/1005002276498187.html?spm=a2g0o.productlist.0.0.75631bcfeHZvG1&algo_pvid=15c33af1-273e-4fac-a224-6dff903b6f43&algo_expid=15c33af1-273e-4fac-a224-6dff903b6f43-0&btsid=0b0a555416212467903751350ef791&ws_ab_test=searchweb0_0,searchweb201602_,searchweb201603_): Protector panel is included.
  - <img src="https://user-images.githubusercontent.com/12926652/206317870-dfb424bf-f16f-49bc-a39f-3310ae243257.png" width=320 />
- [Digikey LPM027M128B](https://www.digikey.com/en/products/detail/azumo/12380-06-T2/9602620): backlight cable is different from original
- [LPM044M141](https://www.digikey.com/en/products/detail/azumo/12567-06-T3/10492348): 4.4" color LCD
- [Adafruit SHARP Memory Display Breakout](https://www.adafruit.com/product/4694): Alternative for MIP Interface Board. Replace monochrome LCD panel. Backlight control is not included.

### [Adafruit SHARP Memory Display Breakout (LS027B7DH01)](https://www.adafruit.com/product/4694)

Pros&Cons

- (good) very visible
- (good) ultra-low power consumption
- (good) not expensive ($45)
- (good) fast drawing
- (bad) no backlight
- (bad) 2 colors only
- Recommend if you think costs. I think it's better than PiTFT and E-ink displays.
- <img src="https://user-images.githubusercontent.com/12926652/91795951-fe3ee280-ec59-11ea-8fc1-b5ae35a7306f.png" width=360 />

### [PiTFT 2.4](https://www.adafruit.com/product/2455)  (OBSOLETE)

Pros&Cons

- (good) easy to assemble and test
- (bad) hard to see in direct sunshine
- <img src ="https://qiita-user-contents.imgix.net/https%3A%2F%2Fqiita-image-store.s3.ap-northeast-1.amazonaws.com%2F0%2F100741%2Fe16fc94e-7449-80df-c044-b8705789345e.png?ixlib=rb-1.2.2&auto=format&gif-q=60&q=75&w=1400&fit=max&s=ca5f5dcbdbe33f473187a50c2b585b81" width=240 height=180 />

### E-ink display (OBSOLETE)

Pros&Cons

- (good) very visible
- (good) ultra-low power consumption
- (bad) slow drawing
- (bad) no backlight
- (bad) 2 colors only
- [PaPiRus ePaper / eInk Screen HAT for Raspberry Pi](https://uk.pi-supply.com/products/papirus-epaper-eink-screen-hat-for-raspberry-pi) 
- <img src="https://qiita-user-contents.imgix.net/https%3A%2F%2Fpbs.twimg.com%2Fmedia%2FEWcpqIRVcAECnhm%3Fformat%3Dpng%26name%3Dmedium?ixlib=rb-1.2.2&auto=format&gif-q=60&q=75&w=1400&fit=max&s=e63859ff88d76213591bfaab25111aca" width=240 height=180 /> ![eink-01-mini](https://user-images.githubusercontent.com/12926652/205788235-34bbf557-a395-4094-a2b3-10c052f6f743.jpg)
- [DFRobot e-ink Display Module for Raspberry Pi 4B/3B+/Zero W](https://www.dfrobot.com/product-1866.html)
- <img src="https://qiita-user-contents.imgix.net/https%3A%2F%2Fpbs.twimg.com%2Fmedia%2FEWvezNTXgAATZuN%3Fformat%3Dpng%26name%3Dmedium?ixlib=rb-1.2.2&auto=format&gif-q=60&q=75&w=1400&fit=max&s=5c0e572fce9492179d347bfb58e312fc" width=240 height=180 /> ![eink-02-mini](https://user-images.githubusercontent.com/12926652/205788573-4ea31e88-7714-4300-96f8-4fa98a4103e8.jpg)


## GPS module

UART modules with GPSd are recomended. I2C(Sparkfun qwiic or Adafruit STEMMA QT) modules are supported experimentally.

### [SparkFun ZOE-M8Q](https://www.sparkfun.com/products/15193)

- UART, I2C(Sparkfun qwiic) and SPI
- an [antenna](https://www.sparkfun.com/products/15246) is also needed
- stable and low power consumption
- recommended as of 2020/6.

### [Berry GPS IMU v4](https://ozzmaker.com/product/berrygps-imu/)

- UART and I2C
- an [antenna](https://www.sparkfun.com/products/15246) is also needed
- BMP390 and IMU(LSM6DS/LIS3MDL) are included
- best replacement for Enviro pHAT
- magnetic sensor is broken...? (All the two modules I have are not working properly.)

### [GPS-PIE](https://gps-pie.com)

- UART and I2C
- an [antenna](https://www.sparkfun.com/products/15246) is also needed with Gmm slice model. L80 slice model can use an internal or external antenna.
- MS5637(pressure) and IMU(BNO055) are included

### [Akizuki Denshi GPS module](http://akizukidenshi.com/catalog/g/gK-09991/)

- UART
- easy to get in Tokyo (buy at Akihabara)
- cheap and low power consumption

### PA1010D GPS

- [Adafruit Mini GPS PA1010D](https://www.adafruit.com/product/4415)
  - UART and I2C(Adafruit STEMMA QT)
- [PIMORONI PA1010D GPS Breakout](https://shop.pimoroni.com/products/pa1010d-gps-breakout)
  - UART and I2C

### [Adafruit Ultimate GPS Breakout](https://www.adafruit.com/product/746)
- UART

## I2C sensors

Adafuit circuitpython library is required or original drivers are available. Refer to learing page of each sensors.

If you use Sparkfun Qwiic or Adafruit STEMMA QT sensors, [SparkFun Qwiic SHIM for Raspberry Pi](https://www.sparkfun.com/products/15794) is very useful for connecting sensors.

<img src="https://user-images.githubusercontent.com/12926652/91799338-d2bff600-ec61-11ea-8c23-b1ed3a40277a.png" width=160 />

### Pressure, temperature

for altitude, grade, and total ascent/descent

- [BMP280](https://shop.pimoroni.com/products/enviro-phat)
- [BMP388](https://www.dfrobot.com/product-1928.html)
- [BMP390](https://www.adafruit.com/product/4816)
- [LPS33HW](https://www.adafruit.com/product/4414)
- [BMP581](https://www.sparkfun.com/products/20170)

### IMU

The accelerometer is used for stop detection when using GPS. The magnetometer is used in compasses. 

- [LSM303](https://shop.pimoroni.com/products/enviro-phat)
- [LSM6DS](https://www.adafruit.com/product/4485): Accel / Gyro
- [LSM9DS1](https://www.sparkfun.com/products/13944): Accel / Gyro / Mag 
- [LIS3MDL](https://www.adafruit.com/product/4485): Mag 
- [BMX160](https://www.dfrobot.com/product-1928.html): Accel / Gyro / Mag
- [BNO055](https://www.adafruit.com/product/4646): Accel / Gyro / Mag / Euler / Quatenrion
- [ISM330DHCX and ](https://www.sparkfun.com/products/19895): Accel / Gyro
- [MMC5983MA](https://www.sparkfun.com/products/19895): Mag

### Light

for auto backlight when using MIP Reflective color LCD

- [TCS3472](https://shop.pimoroni.com/products/enviro-phat)
- [VCNL4040](https://www.adafruit.com/product/4161)

### Multi sensors

- [Environment Sensor HAT](https://www.waveshare.com/environment-sensor-hat.htm)
  - BME280 (Pressure, temperature and humidity)
  - ICM20948 (Accel / Gyro / Mag)
  - TSL25911FN (Light)
  - LTR390 (UV)
  - SGP40 (VOC:volatile organic compounds)

### Button

This is essential for displays without buttons, like MIP displays.

- [Button SHIM](https://shop.pimoroni.com/products/button-shim)
- <img src="https://user-images.githubusercontent.com/12926652/91799330-cfc50580-ec61-11ea-9045-e1991aed205c.png" width=240 />

### Battery

get battery percent, etc.

- [PiJuice HAT](https://uk.pi-supply.com/products/pijuice-standard) / [PiJuice Zero](https://uk.pi-supply.com/products/pijuice-zero)
- <img src="https://user-images.githubusercontent.com/12926652/91799334-d0f63280-ec61-11ea-9a96-429991011b08.png" width=240 />

## ANT+ USB dongle
- available in eBay or aliexpress
- also need micro USB OTG Adapter : like [adafruit adapter](https://www.adafruit.com/product/2910). 
- ![ANT+ USB dongle + USB OTG Adapter](https://qiita-user-contents.imgix.net/https%3A%2F%2Fqiita-image-store.s3.ap-northeast-1.amazonaws.com%2F0%2F100741%2F2a2639eb-7515-4dff-33d1-864a274a4919.png?ixlib=rb-1.2.2&auto=format&gif-q=60&q=75&w=1400&fit=max&s=348720e6c0bc82111195ac699fdc04b6)

## SD card
- youw own (over 8GB)
- [SanDisk MAX ENDURANCE microSD™ Card](https://www.westerndigital.com/products/memory-cards/sandisk-max-endurance-uhs-i-microsd#SDSQQVR-032G-GN6IA) is recommended if you use several years.
- [SanDisk® High Endurance microSD™ Card](https://shop.westerndigital.com/products/memory-cards/sandisk-high-endurance-uhs-i-microsd#SDSQQNR-032G-AN6IA) is not compatible with  Raspberry Pi OS Bullseye. See [post1](https://forums.raspberrypi.com/viewtopic.php?p=2021511) and [post2](https://forums.raspberrypi.com/viewtopic.php?p=2006250)

## Case

- make a nice case if you can use 3D printer.
- [Topeak SMARTPHONE DRYBAG 5"](https://www.topeak.com/global/en/products/weatherproof-ridecase-series/1092-smartphone-drybag-5%22) is easy to use. It is waterproof.
  - If you attach the PiTFT directly to the Raspberry Pi Zero, you can use Topeak SMARTPHONE DRYBAG for iPhone 5 which is smaller than Topeak SMARTPHONE DRYBAG 5".
  - On the other hand, if you want to put some sensors in, Topeak SMARTPHONE DRYBAG 6" is better.


# Hardware Assembly

Using many pHATs can be bulky, so it's best to use one pHat only. It's essential to make it compact.

Here are two assembly examples.

## Displays with pHAT headers (PiTFT or E-ink displays)

see [hardware_installation_pitft.md](./hardware_installation_pitft.md) as PiTFT(obsolete) example.

## Displays without pHAT headers (MIP Reflective color LCD and SHARP Memory Display)

It's quite difficult, but the hardware configuration is better than PiTFT.

### Adafruit SHARP Memory Display

<img src="https://user-images.githubusercontent.com/12926652/91796767-f6803d80-ec5b-11ea-9bde-19940a951588.png" width=360 />

- top left: Raspberry Pi Zero WH
- top right: PiJuice Zero
- central left: Adafruit SHARP Memory Display
- center: GPS module
- central right: DFRobot BMP160(IMU) and BMP388(pressure and temperature)
- bottom left: Button SHIM
- bottom right: SparkFun Qwiic SHIM for Raspberry Pi

Connect the Raspberry Pi Zero to the display.
Note that the connection between Raspberry Pi and SHARP Memory Display is different from the Adafruit tutorial.

| Name | Raspberry Pi | SHARP Memory Display Breakout | MIP Interface Board |
|:-|:-:|:-:|:-:|
| GND      | IO25 | GND   | CN1-4 |
| VCOMSEL  | IO11 | EXTIN | CN2-3 |
| DISP     | IO13 | DISP  | CN1-9 |
| CS       | IO16 | CS    | CN1-8 |
| 3.3V     | IO17 | VIN   | CN1-6 |
| SPI MOSI | IO19 | MOSI  | CN1-7 |
| SPI SCLK | IO23 | SCLK  | CN1-5 |


for backlight (MIP Interface Board)

| Name | Raspberry Pi | MIP Interface Board |
|:-|:-:|:-:|
| LEDPWM   | IO12 | CN2-1 |
| VBUS-5V  | IO02/04 | CN3-5 |
| BL2-CTRL | IO06/09/14/20/25/34/39 | CN4-3 |


Reference:
- https://pinout.xyz/pinout/io_pi_zero
- https://docid81hrs3j1.cloudfront.net/medialibrary/2019/03/JDI_MIP_LCD.pdf
- https://qiita.com/hishi/items/669ce474fcd76bdce1f1

<img src="https://user-images.githubusercontent.com/12926652/91796771-f7b16a80-ec5b-11ea-9b24-113049fd5998.png" width=360 />

Every time you connect, it is good idea to check the module with the sample program to make sure it works.

<img src="https://user-images.githubusercontent.com/12926652/91796772-f84a0100-ec5b-11ea-8610-508f64692c9e.png" width=360 />

Connect the GPS module and Qwiic SHIM for Raspberry Pi.

<img src="https://user-images.githubusercontent.com/12926652/91796775-f97b2e00-ec5b-11ea-8fea-52658208261f.png" width=360 />

Fix the parts with screws.

<img src="https://user-images.githubusercontent.com/12926652/91796778-fb44f180-ec5b-11ea-91a3-2d929107cfc2.png" width=360 />

Finally, connect the battery for the PiJuice Zero.

<img src="https://user-images.githubusercontent.com/12926652/91796781-fd0eb500-ec5b-11ea-8451-593858d32b17.png" width=360 />


### MIP Reflective color LCD module 2.7" w/ backlight (LPM027M128C)

Here is another example.

<img src="https://user-images.githubusercontent.com/12926652/205553726-3e2cca72-7a52-49e1-ba2b-931d9e210425.jpg" width=360 /> <img src="https://user-images.githubusercontent.com/12926652/205553732-3a2d8a87-af90-44c1-ace8-228eb3751017.jpg" width=287 />

- Raspberry Pi Zero WH
- MIP Reflective color LCD module 2.7" w/ backlight (LPM027M128C)
- Adafruit SHARP Memory Display Breakout
- [MAX-M10S Ultra Low Power GNSS receiver with SMA connector](https://gnss.store/max-m10s-gnss-modules/170-elt0151.html)
- SparkFun 9DoF IMU Breakout
  - ISM330DHCX(Accel / Gyro)
  - MMC5983MA(Mag)
- SparkFun BMP581
- SparkFun Qwiic SHIM for Raspberry Pi
- Pimoroni Button SHIM
- ANT+ USB dongle


# Bicycle mounting

Attach the case to the handlebar and connect it to a battery in a top tube bag. There is no switch, so the pizero_bikecomputer will start the moment you connect the battery.

![bike-01.png](https://qiita-image-store.s3.ap-northeast-1.amazonaws.com/0/100741/5157c02c-0fe2-c6bb-ab7b-d1e1965f10c2.png)



[Back to README.md](/README.md)
