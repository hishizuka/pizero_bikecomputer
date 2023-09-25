#!/bin/bash

trap 'kill $sub_pid' 1 2 3 15
trap 'kill $sub_pid' EXIT

PGMDIR=/home/pi/pizero_bikecomputer

export QT_QPA_PLATFORM=linuxfb:fb=/dev/fb1
#export QT_QPA_PLATFORM=eglfs

export QT_QPA_EVDEV_TOUCHSCREEN_PARAMETERS=/dev/input/event0:rotate=270
export QT_QPA_FB_TSLIB=1
export TSLIB_FBDEVICE=/dev/fb1
export TSLIB_TSDEVICE=/dev/input/event0

cd $PGMDIR

/usr/bin/python3 pizero_bikecomputer.py

sub_pid=$!
echo $$ $sub_pid
wait
