#!/bin/bash
set -euo pipefail
#############################################################
# This script sets up the Pi Zero Bike Computer environment
# and is intended to be run on a fresh Raspberry Pi OS installation.
# 1. It should be run as root.
# 2. Creates a Python virtual environment, installs necessary
#    packages, and prepares the system for running the bike computer
#    application.
# 3. Be aware that this script will not install the bike computer
#    service and it will not install hardware specific packages.
# 4. It is intended to be run once, before the bike computer service
#    is installed.
# 5. It will also remove the default directories in the home directory.
#
# This script is based on the instructions from the Pi Zero Bike Computer
# foud here: https://qiita.com/hishi/items/46619b271daaa9ad41b3
#
# Usage: sudo ./scripts/initial_setup.sh
#
#############################################################

if [ "$EUID" -eq 0 ]; then
  if [ -n "$SUDO_USER" ]; then
    echo "✅ Running with sudo as user: $SUDO_USER"
  else
    echo "✅ Running directly as root"
  fi
else
  echo "❌ Not running as root. Please use sudo."
  exit 1
fi

USER_HOME="$(eval echo "~$SUDO_USER")"
USER="$SUDO_USER"
# update apt and upgrade the system
apt update && apt upgrade -y

# setup virutal environment
cd "$USER_HOME"
echo "Setting up Python virtual environment in $USER_HOME/.venv"
sudo -u "$USER" python -m venv "$USER_HOME/.venv"
echo "source ~/.venv/bin/activate" >> "$USER_HOME/.bashrc"
echo "source $USER_HOME/.venv/bin/activate" >> ~/.bashrc
source ~/.bashrc

# install wiringpi
mkdir -p "$USER_HOME/wiringPi" && cd "$USER_HOME/wiringPi"
WIRINGPI_DEB="$USER_HOME/wiringPi/wiringpi_3.14_arm64.deb"
wget -O "$WIRINGPI_DEB" https://github.com/WiringPi/WiringPi/releases/download/3.14/wiringpi_3.14_arm64.deb
dpkg -i "$WIRINGPI_DEB"
rm -rf "$USER_HOME/wiringPi"

# remove default directories for pi user.
rm -rf "$USER_HOME/Bookshelf"
rm -rf "$USER_HOME/Documents"
rm -rf "$USER_HOME/Downloads"
rm -rf "$USER_HOME/Music"
rm -rf "$USER_HOME/Pictures"
rm -rf "$USER_HOME/Public"
rm -rf "$USER_HOME/Templates"
rm -rf "$USER_HOME/Videos"

cd "$USER_HOME"

# apt install python3-pip cython3 cmake gawk python3-numpy python3-pyqt5 python3-pyqtgraph sqlite3 libsqlite3-dev libatlas-base-dev python3-aiohttp python3-aiofiles python3-smbus python3-rpi.gpio python3-psutil python3-pil
apt install -y python3-pip cython3 cmake python3-numpy python3-pyqt5 python3-pyqtgraph sqlite3 libsqlite3-dev libatlas-base-dev python3-aiohttp python3-aiofiles python3-smbus python3-rpi.gpio python3-psutil python3-pil bluez-obexd dbus-x11
pip install oyaml sip polyline garminconnect stravacookies qasync dbus-next bluez-peripheral tb-mqtt-client timezonefinder
pip install git+https://github.com/hishizuka/crdp.git

apt install -y python3-pigpio
# This script checks and optionally disables pigpiod's default startup line.
# By default, pigpiod can use around 10% CPU. If that's not acceptable,
# it can be disabled by commenting out its ExecStart line in the systemd unit file.
FILE="/lib/systemd/system/pigpiod.service"
LINE="ExecStart=/usr/bin/pigpiod -l"

echo "Checking pigpiod service configuration in $FILE..."

if grep -q "^[[:space:]]*#.*$LINE" "$FILE"; then
    echo "✔ The line is already commented out. No action needed."

elif grep -q "^[[:space:]]*$LINE" "$FILE"; then
    echo "⚠ Found active line: $LINE"
    read -p "Do you want to comment it out? (y/n): " -r
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        sed -i "s|^[[:space:]]*$LINE|# $LINE|" "$FILE"
        echo "✅ Line has been commented out in $FILE."
    else
        echo "ℹ No changes made to $FILE."
    fi

else
    echo "❌ The line was not found in $FILE."
fi
systemctl enable pigpiod
systemctl start pigpiod

# Start the bike computer then kill it. This will create the necessary directories and files.
APP_PATH="$USER_HOME/pizero_bikecomputer/pizero_bikecomputer.py"
PID_FILE="$USER_HOME/tmp/bikecomputer_install_test.pid"

mkdir -p "$USER_HOME/tmp" && touch "$PID_FILE"

echo "🔧 Starting pizero_bikecomputer.py in headless mode for verification..."

# Start app in background with offscreen rendering
QT_QPA_PLATFORM=offscreen python3 "$APP_PATH" &
APP_PID=$!
echo $APP_PID > "$PID_FILE"

# Wait a few seconds for it to run
echo "⏳ Waiting for the application to start..."
sleep 10

# Check if it's still running
if ps -p $APP_PID > /dev/null; then
    echo "✅ Application started successfully (PID $APP_PID). Shutting it down..."
    kill "$APP_PID"
    rm -f "$PID_FILE"
else
    echo "❌ Application did not start correctly. Check logs or errors."
    rm -f "$PID_FILE"
    exit 1
fi

echo "✅ Startup test completed successfully."

# update the settings.conf if the user intends to use ANT+
SETTINGS_FILE="$USER_HOME/pizero_bikecomputer/settings.conf"
read -p "Do you intend to use ANT+? (y/n): " -r
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Installing ANT+ dependencies..."

    # Install system packages
    apt install -y libusb-1.0-0 python3-usb

    # Install openant from GitHub
    pip install git+https://github.com/hishizuka/openant.git

    # Update settings.conf
    if [ -f "$SETTINGS_FILE" ]; then
        sed -i 's/^ANT[[:space:]]*=[[:space:]]*false/ANT = true/' "$SETTINGS_FILE"
        echo "✅ Updated ANT setting to true in $SETTINGS_FILE."
    else
        echo "⚠ settings.conf not found at $SETTINGS_FILE. Skipping config update."
    fi
else
    echo "ANT+ support will not be installed."
fi

# Install additional requirements
pip install -r "$USER_HOME/pizero_bikecomputer/reqs/full.txt"

echo "✅ Pi Zero Bike Computer initial setup completed successfully! Now rebooting"
reboot