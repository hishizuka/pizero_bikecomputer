#!/bin/bash

cd /home/pi/pizero_bikecomputer/

/bin/rm ./log/log.db
/usr/bin/git pull origin master > ./log/update.txt 2>&1

