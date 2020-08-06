#!/bin/bash

PGMDIR=/home/pi/pizero_bikecomputer

cd /home/pi/pizero_bikecomputer/

if [ -e ./log/debug.txt ]; then
/bin/cp ./log/debug.txt ./log/debug.txt-`date "+%Y%m%d_%H%M%S"`
else
mkdir ./log
fi

# u: directly output to logging text
#QT_QPA_PLATFORM=offscreen /usr/bin/python3 -u pizero_bikecomputer.py > ./log/debug.txt 2>&1
QT_QPA_PLATFORM=offscreen /usr/bin/python3 -u pizero_bikecomputer.py > ./log/debug.txt 2> >(grep --line-buffered -v 'Operation timed out' | gawk '{print "[ERROR]", $0; fflush()}')

