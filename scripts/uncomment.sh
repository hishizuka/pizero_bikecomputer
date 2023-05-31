#!/bin/sh

sudo sed -i -e "s/^\#dtoverlay\=disable\-bt/dtoverlay\=disable\-bt/" /boot/config.txt
sudo sed -i -e "s/^\#dtoverlay\=disable\-wifi/dtoverlay\=disable\-wifi/" /boot/config.txt

sudo sed -i -e "s/^DEVICES\=\"\/dev\/ttyS0\"/\#DEVICES\=\"\/dev\/ttyS0\"/" /etc/default/gpsd
sudo sed -i -e "s/^\#DEVICES\=\"\/dev\/ttyAMA0\"/DEVICES\=\"\/dev\/ttyAMA0\"/" /etc/default/gpsd

