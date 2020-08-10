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

if [ -e $PGMDIR/log/debug.txt ]; then
/bin/cp $PGMDIR/log/debug.txt $PGMDIR/log/debug.txt-`date "+%Y%m%d_%H%M%S"`
fi

cd $PGMDIR

# O: optimize
# u: directly output to logging text
#/usr/bin/python3 -u $PGMDIR/pizero_bikecomputer.py > $PGMDIR/log/debug.txt 2>&1 &
/usr/bin/python3 -u pizero_bikecomputer.py > ./log/debug.txt 2> >(grep --line-buffered -v 'Operation timed out' | gawk '{print "[ERROR]", $0; fflush()}')

sub_pid=$!
echo $$ $sub_pid
wait


