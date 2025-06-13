#!/bin/bash
set -euo pipefail
#############################################################
# This script sets up the pizero_bikecomputer environment
# and is intended to be run on a fresh Raspberry Pi OS installation.
# 1. Creates a Python virtual environment, installs necessary
#    packages, and prepares the system for running the pizero_bikecomputer
#    application.
# 2. Be aware that this script will not install the bike computer
#    service and it will not install hardware specific packages.
# 3. It is intended to be run once, before the bike computer service
#    is installed.
# 4. It will also remove the default directories in the home directory.
#
# This script is based on the instructions from the pizero_bikecomputer
# foud here: https://qiita.com/hishi/items/46619b271daaa9ad41b3
#
# Usage: ./scripts/initial_setup.sh
#
#############################################################

###
# Function to ask the user for input
# Returns "true" for yes, "false" for no, and exits for quit.
###
ask_user() {
    local prompt="$1"
    while true; do
        read -rp "$prompt [y/n/q(uit)]: " answer
        #answer="${answer,,}"  # lowercase
        answer="$(echo "$answer" | tr 'A-Z' 'a-z')"

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
prompt_and_store "Setup Python virtual environment?" setup_python_venv
if [[ "$setup_python_venv" == "true" ]]; then
    read -rp "📦 Enter virtual environment name (default: .venv): " venv_name
    venv_name="${venv_name:-.venv}"
    venv_path=~/"$venv_name"
fi
prompt_and_store "Install ANT+ dependencies?" install_ant_plus
prompt_and_store "Install GPS dependencies?" install_gps
prompt_and_store "Enable I2C?" enable_i2c
prompt_and_store "Enable SPI?" enable_spi
set -e

# update apt and upgrade the system
sudo apt update
sudo apt upgrade -y

sudo apt install -y python3-venv git python3-yaml cython3 cmake python3-numpy sqlite3 libsqlite3-dev python3-pil python3-aiohttp python3-aiofiles python3-psutil python3-pyqt6 python3-pyqt6.qtsvg pyqt6-dev-tools bluez-obexd
echo "✅ .deb packages installed."

cd

# setup virutal environment
if [[ "$setup_python_venv" == "true" ]]; then
    echo "🔧 Creating virtual environment at: $venv_path"
    python3 -m venv --system-site-packages "$venv_path"
    if ! grep -Fxq "source $venv_path/bin/activate" ~/.bashrc; then
        echo "source $venv_path/bin/activate" >> ~/.bashrc
        echo "🔧 Added 'source $venv_path/bin/activate' to ~/.bashrc"
    fi
    source "$venv_path/bin/activate"
    echo "✅ Virtual environment setup complete. Python location: $(which python3), pip location: $(which pip3)"
else
    echo "⏭️ Skipping Python virtual environment setup."
fi

# Install additional requirements
echo "🔧 Installing the application's core Python requirements..."
sudo apt install -y python3-venv
# essential
pip install oyaml polyline qasync pyqtgraph timezonefinder git+https://github.com/hishizuka/crdp.git
# optional
pip install garminconnect stravacookies dbus-next bluez-peripheral tb-mqtt-client mmh3
echo "✅ Core Python dependencies installed successfully."

if command -v raspi-config >/dev/null 2>&1; then
    has_raspi_config=true
else
    has_raspi_config=false
fi

# Install Ant+ packages
if [[ "$install_ant_plus" == "true" ]]; then
    echo "🔧 Installing the ANT+ dependencies..."
    sudo apt install -y python3-pip libusb-1.0-0 python3-usb
    # install as root to ensure there are no udev_rules permission issues from setuptools
    sudo pip3 install git+https://github.com/hishizuka/openant.git --break-system-packages
    echo "✅ ANT+ dependencies installed successfully."
fi

if [[ "$install_gps" == "true" ]]; then
    echo "🔧 Installing the GPS dependencies..."
    sudo apt install -y gpsd
    pip install gps3
    if [[ "$has_raspi_config" == "true" ]]; then
        sudo raspi-config nonint do_serial_cons 1
        sudo raspi-config nonint do_serial_hw 0
    fi
    sudo systemctl enable gpsd
    sudo systemctl enable gpsd.socket
    #sudo systemctl start gpsd
    echo "✅ GPS dependencies installed successfully."
fi

if [[ "$enable_i2c" == "true" ]]; then
    # Enable I2C on Raspberry Pi
    echo "🔧 Enabling i2c on Raspberry Pi..."
    if [[ "$has_raspi_config" == "true" ]]; then
        sudo raspi-config nonint do_i2c 0
    fi
    # add pi to i2c if not already a member
    #if ! groups $USER | grep -qw i2c; then
    #  sudo adduser $USER i2c
    #fi
    echo "✅ I2C enabled successfully"
fi

if [[ "$enable_spi" == "true" ]]; then
    # Enable SPI on Raspberry Pi
    echo "🔧 Enabling spi on Raspberry Pi..."
    if [[ "$has_raspi_config" == "true" ]]; then
        sudo raspi-config nonint do_spi 0
    fi
    # add pi to i2c if not already a member
    #if ! groups $USER | grep -qw spi; then
    #  sudo adduser $USER spi
    #fi
    
    sudo systemctl enable pigpiod
    echo "ℹ️ pigpio enabled  successfully."

    echo "✅ SPI enabled successfully"

fi

BOOT_CONFIG_FILE="/boot/firmware/config.txt"

if [ -f "$BOOT_CONFIG_FILE" ]; then
    AUDIO_PARAM="dtparam=audio=on"
    # Disable audio on Raspberry Pi
    echo "🔧 Disabling the Raspberry Pi audio..."
    if grep -q "^[^#]*$AUDIO_PARAM" "$BOOT_CONFIG_FILE"; then
        sudo sed -i "/^[^#]*$AUDIO_PARAM/s/^/#/" "$BOOT_CONFIG_FILE"
    else
        echo "ℹ️ Audio is already disabled or line is commented out."
    fi
    echo "✅ Audio disabled successfully in $BOOT_CONFIG_FILE (or already disabled)"
fi

# Disable camera on Raspberry Pi
if [[ "$has_raspi_config" == "true" ]]; then
    echo "🔧 Disabling the Raspberry Pi camera..."
    sudo raspi-config nonint do_camera 1
fi

echo "🔧 Starting pizero_bikecomputer.py in headless mode for verification..."
pgm_dir=~/pizero_bikecomputer
if [ ! -d "$pgm_dir" ]; then
    git clone https://github.com/hishizuka/pizero_bikecomputer.git
fi

cd "$pgm_dir"

# Create a named pipe (FIFO) to monitor output
OUT_PIPE=$(mktemp -u)
mkfifo "$OUT_PIPE"

cleanup() {
    rm -f "$OUT_PIPE"
    kill "$APP_PID" 2>/dev/null || true
}
trap cleanup EXIT

# Start the app and tee its output to both screen and PIPE
export QT_QPA_PLATFORM=offscreen
stdbuf -oL python3 pizero_bikecomputer.py 2>&1 | tee "$OUT_PIPE" &
APP_PID=$!

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
done < "$OUT_PIPE"

# Check if app is still running
if ps -p $APP_PID > /dev/null; then
    echo "✅ Application started successfully (PID $APP_PID)."
else
    echo "❌ Application did not start correctly. Check logs or errors."
    exit 1
fi

cd
echo "✅ Startup test completed successfully."
echo "✅ Pi Zero Bike Computer initial setup completed successfully! Now rebooting"

sudo reboot

