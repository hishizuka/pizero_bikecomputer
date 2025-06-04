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

###
# Function to ask the user for input
# Returns "true" for yes, "false" for no, and exits for quit.
###
ask_user() {
    local prompt="$1"
    while true; do
        read -rp "$prompt [y/n/q(uit)]: " answer
        answer="${answer,,}"  # lowercase

        case "$answer" in
            y|yes) return 0 ;;
            n|no) return 1 ;;
            q|quit) return 2 ;;
            *) echo "Invalid input. Please answer with y, n, or q." ;;
        esac
    done
}

prompt_and_store() {
    local prompt="$1"
    local var_name="$2"
    ask_user "$prompt"
    case $? in
      0) eval "$var_name=true" ;;
      1) eval "$var_name=false" ;;
      2) echo "👋 Quitting...bye!"; exit 0 ;;
    esac
}

# temporarily disable error checking to allow for user input
set +e
prompt_and_store "Install ANT+ dependencies?" install_ant_plus
prompt_and_store "Install GPS dependencies?" install_gps
prompt_and_store "Install Dev dependencies?" install_dev
prompt_and_store "Install GPIO dependencies?" install_gpio
prompt_and_store "Install I2C dependencies?" install_i2c
set -e

PI_USER_HOME="$(eval echo "~$SUDO_USER")"
PI_USER="$SUDO_USER"
# update apt and upgrade the system
apt update && apt upgrade -y

# setup virutal environment
cd "$PI_USER_HOME"
echo "🔧Setting up Python virtual environment in $PI_USER_HOME/.venv"
sudo -u "$PI_USER" python3 -m venv --system-site-packages "$PI_USER_HOME/.venv"
grep -qxF "source ~/.venv/bin/activate" "$PI_USER_HOME/.bashrc" || echo "source ~/.venv/bin/activate" >> "$PI_USER_HOME/.bashrc"
grep -qxF "source $PI_USER_HOME/.venv/bin/activate" ~/.bashrc || echo "source $PI_USER_HOME/.venv/bin/activate" >> ~/.bashrc
echo "🔧 Adding virtual environment to PATH in $PI_USER_HOME/.bashrc"
echo "🔧 Sourcing ~/.bashrc"
source ~/.bashrc
echo "✅ Virtual environment setup complete. Python location: $(which python3), pip location: $(which pip3)"

cd "$PI_USER_HOME"
echo "🔧 Running pip install. Python location: $(which python3), pip location: $(which pip3)"
apt install -y python3-pip cython3 cmake python3-numpy python3-pyqt5 python3-pyqtgraph sqlite3 libsqlite3-dev libatlas-base-dev python3-aiohttp python3-aiofiles python3-smbus python3-rpi.gpio python3-psutil python3-pil bluez-obexd dbus-x11
echo "✅ .deb packages installed."
# Install additional requirements
echo "🔧 Installing the application's core Python requirements..."
sudo -u "$PI_USER" "$PI_USER_HOME/.venv/bin/pip3" install -r "$PI_USER_HOME/pizero_bikecomputer/reqs/full.txt"
sudo -u "$PI_USER" "$PI_USER_HOME/.venv/bin/pip3" install git+https://github.com/hishizuka/openant.git
echo "✅ Core Python dependencies installed successfully."

# Install Ant+ packages
if [[ "$install_ant_plus" == "true" ]]; then
  echo "🔧 Installing the ANT+ dependencies..."
  apt install -y python3-setuptools libusb-1.0-0 python3-usb
  # install as root to ensure there are no udev_rules permission issues fro setuptools
  "$PI_USER_HOME/.venv/bin/pip3" install git+https://github.com/hishizuka/openant.git
  echo "✅ ANT+ dependencies installed successfully."
fi

if [[ "$install_gps" == "true" ]]; then
  echo "🔧 Installing the GPS dependencies..."
  sudo -u "$PI_USER" "$PI_USER_HOME/.venv/bin/pip3" install -r "$PI_USER_HOME/pizero_bikecomputer/reqs/sensors/gps/gpsd.txt"
  sudo -u "$PI_USER" "$PI_USER_HOME/.venv/bin/pip3" install -r "$PI_USER_HOME/pizero_bikecomputer/reqs/sensors/gps/i2c.txt"
  echo "✅ GPS dependencies installed successfully."
fi

if [[ "$install_dev" == "true" ]]; then
  echo "🔧 Installing the development dependencies..."
  sudo -u "$PI_USER" "$PI_USER_HOME/.venv/bin/pip3" install -r "$PI_USER_HOME/pizero_bikecomputer/reqs/dev.txt"
  echo "✅ Development dependencies installed successfully."
fi

if [[ "$install_gpio" == "true" ]]; then
  echo "🔧 Installing the GPIO dependencies..."
  apt install -y python3-pigpio
  systemctl enable pigpiod
  systemctl start pigpiod
  echo "ℹ️ python3-pigpio installed, enabled and started successfully."
  echo "✅ GPIO dependencies installed successfully."
fi

BOOT_CONFIG_FILE="/boot/firmware/config.txt"

if [[ "$install_i2c" == "true" ]]; then
  echo "🔧 Installing the i2c dependencies..."
  sudo -u "$PI_USER" "$PI_USER_HOME/.venv/bin/pip3" install -r "$PI_USER_HOME/pizero_bikecomputer/reqs/sensors/gps/i2c.txt"
  echo "✅ i2c dependencies installed successfully."

  # Enable I2C on Raspberry Pi
  echo "🔧 Enabling i2c on Raspberry Pi..."
  I2C_PARAM="dtparam=i2c_arm=on"

  # Check if the line exists (commented or uncommented)
  if grep -q -E "^\s*#?\s*${I2C_PARAM}" "$BOOT_CONFIG_FILE"; then
      # Uncomment if commented
      sudo sed -i "s|^\s*#\s*\(${I2C_PARAM}\)|\1|" "$BOOT_CONFIG_FILE"
  else
      # Add the line at the end if not found
      echo "$I2C_PARAM" | sudo tee -a "$BOOT_CONFIG_FILE" > /dev/null
  fi
  # add pi to i2c if not already a member
  if ! groups pi | grep -qw i2c; then
    sudo adduser pi i2c
  fi
  echo "✅ I2C enabled successfully in $BOOT_CONFIG_FILE (or already enabled)"

fi

AUDIO_PARAM="dtparam=audio=on"
# Disable audio on Raspberry Pi
echo "🔧 Disabling the Raspberry Pi audio..."
if grep -q "^[^#]*$AUDIO_PARAM" "$BOOT_CONFIG_FILE"; then
  sudo sed -i "/^[^#]*$AUDIO_PARAM/s/^/#/" "$BOOT_CONFIG_FILE"
else
  echo "ℹ️ Audio is already disabled or line is commented out."
fi
echo "✅ Audio disabled successfully in $BOOT_CONFIG_FILE (or already disabled)"

CAMERA_PARAM="camera_auto_detect=1"
# Disable audio on Raspberry Pi
echo "🔧 Disabling the Raspberry Pi camera..."
if grep -q "^[^#]*$CAMERA_PARAM" "$BOOT_CONFIG_FILE"; then
  sudo sed -i "/^[^#]*$CAMERA_PARAM/s/^/#/" "$BOOT_CONFIG_FILE"
else
  echo "ℹ️ Camera is already disabled or line is commented out."
fi
echo "✅ Camera disabled successfully in $BOOT_CONFIG_FILE (or already disabled)"


echo "🔧 Starting pizero_bikecomputer.py in headless mode for verification..."

PID_FILE="$PI_USER_HOME/tmp/bikecomputer_install_test.pid"
mkdir -p "$PI_USER_HOME/tmp" && touch "$PID_FILE"

cd "$PI_USER_HOME"/pizero_bikecomputer

# Create a named pipe (FIFO) to monitor output
PIPE=$(mktemp -u)
mkfifo "$PIPE"

# Start the app and tee its output to both screen and PIPE
stdbuf -oL sudo -u "$PI_USER" QT_QPA_PLATFORM=offscreen "$PI_USER_HOME/.venv/bin/python3" pizero_bikecomputer.py \
  2>&1 | tee "$PIPE" &
APP_PID=$!
echo $APP_PID > "$PID_FILE"

# Monitor the output for readiness
ready=0
while IFS= read -r line; do
    if [[ $ready -eq 0 && "$line" == *"Drawing components:"* ]]; then
        echo "ℹ️ 'Drawing components:' detected. Waiting 10s..."
        ready=1
    fi

    if [[ $ready -eq 1 && "$line" == *"total :"* ]]; then
        sleep 10
        break
    fi
done < "$PIPE"

# Check if app is still running
if ps -p $APP_PID > /dev/null; then
    echo "✅ Application started successfully (PID $APP_PID). Shutting it down..."
    kill "$APP_PID"
    rm -f "$PID_FILE" "$PIPE"
else
    echo "❌ Application did not start correctly. Check logs or errors."
    rm -f "$PID_FILE" "$PIPE"
    exit 1
fi


cd "$PI_USER_HOME"
sudo chown --recursive pi:pi pizero_bikecomputer

echo "✅ Startup test completed successfully."

echo "✅ Pi Zero Bike Computer initial setup completed successfully! Now rebooting"
reboot