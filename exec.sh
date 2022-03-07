#!/bin/bash

PGMDIR=/home/pi/pizero_bikecomputer

export QT_QPA_PLATFORM=xcb

cd /home/pi/pizero_bikecomputer/

if [ -e ./log/debug.txt ]; then
/bin/cp ./log/debug.txt ./log/debug.txt-`date "+%Y%m%d_%H%M%S" -r ./log/debug.txt`
else
mkdir ./log
fi
#if [ -e $PGMDIR/log/debug.txt ]; then
#/bin/cp $PGMDIR/log/debug.txt $PGMDIR/log/debug.txt-`date "+%Y%m%d_%H%M%S" -r $PGMDIR/log/debug.txt`
#fi

# O: optimize
# u: directly output to logging text
/usr/bin/python3 -u pizero_bikecomputer.py -f > ./log/debug.txt 2> >(grep --line-buffered -v 'Operation timed out' | gawk '{print "[ERROR]", $0; fflush()}')

