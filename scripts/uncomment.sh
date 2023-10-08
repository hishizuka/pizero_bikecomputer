#!/bin/sh
sudo sed -i -e "s/^DEVICES\=\"\/dev\/ttyS0\"/\#DEVICES\=\"\/dev\/ttyS0\"/" /etc/default/gpsd
sudo sed -i -e "s/^\#DEVICES\=\"\/dev\/ttyAMA0\"/DEVICES\=\"\/dev\/ttyAMA0\"/" /etc/default/gpsd
