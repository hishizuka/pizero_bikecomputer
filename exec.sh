#!/bin/bash

PGMDIR=/home/pi/pizero_bikecomputer

export QT_QPA_PLATFORM=xcb

cd /home/pi/pizero_bikecomputer/

/usr/bin/python3 pizero_bikecomputer.py -f
