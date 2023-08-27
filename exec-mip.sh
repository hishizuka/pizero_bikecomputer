#!/bin/bash

PGMDIR=/home/pi/pizero_bikecomputer

cd /home/pi/pizero_bikecomputer/

export QT_QPA_PLATFORM=offscreen
#error, warning, info, debug
export PYUSB_DEBUG=critical
#export PYUSB_LOG_FILENAME=/dev/null
/usr/bin/python3 pizero_bikecomputer.py

