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
echo "🔧Setting up Python virtual environment in $USER_HOME/.venv"
sudo -u "$USER" python3 -m venv --system-site-packages "$USER_HOME/.venv"
grep -qxF "source ~/.venv/bin/activate" "$USER_HOME/.bashrc" || echo "source ~/.venv/bin/activate" >> "$USER_HOME/.bashrc"
grep -qxF "source $USER_HOME/.venv/bin/activate" ~/.bashrc || echo "source $USER_HOME/.venv/bin/activate" >> ~/.bashrc
echo "🔧 Adding virtual environment to PATH in $USER_HOME/.bashrc"
echo "🔧 Sourcing ~/.bashrc"
source ~/.bashrc
echo "✅ Virtual environment setup complete. Python location: $(which python3), pip location: $(which pip3)"

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

echo "ℹ️ Running pip install. Python location: $(which python3), pip location: $(which pip3)"
apt install -y python3-pip cython3 cmake python3-numpy python3-pyqt5 python3-pyqtgraph sqlite3 libsqlite3-dev libatlas-base-dev python3-aiohttp python3-aiofiles python3-smbus python3-rpi.gpio python3-psutil python3-pil bluez-obexd dbus-x11
echo "ℹ️ .deb packages installed."
# Install additional requirements
echo "🔧 Installing the application's core Python requirements..."
sudo -u "$USER" "$USER_HOME/.venv/bin/pip3" install -r "$USER_HOME/pizero_bikecomputer/reqs/full.txt"
echo "✅ Core Python dependencies installed successfully."

apt install -y python3-pigpio
systemctl enable pigpiod
systemctl start pigpiod
echo "✅ python3-pigpio installed, enabled and started."

# Start the bike computer then kill it. This will create the necessary directories and files.
PID_FILE="$USER_HOME/tmp/bikecomputer_install_test.pid"
mkdir -p "$USER_HOME/tmp" && touch "$PID_FILE"

echo "ℹ️ Starting pizero_bikecomputer.py in headless mode for verification..."
cd "$USER_HOME"/pizero_bikecomputer
# Start app in background with offscreen rendering
sudo -u "$USER" QT_QPA_PLATFORM=offscreen "$USER_HOME/.venv/bin/python3" pizero_bikecomputer.py &
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

cd "$USER_HOME"
sudo chown --recursive pi:pi pizero_bikecomputer

echo "✅ Startup test completed successfully."

echo "✅ Pi Zero Bike Computer initial setup completed successfully! Now rebooting"
reboot