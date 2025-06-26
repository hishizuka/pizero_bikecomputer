#!/bin/bash
set -euo pipefail
#############################################################
# This script sets up pizero_bikecomputer environment
# and is intended to be run on a fresh Raspberry Pi OS installation.
# 1. Creates a Python virtual environment, installs necessary
#    packages, and prepares the system for running pizero_bikecomputer
#    application.
# 2. Be aware that this script will not install pizero_bikecomputer_service
#    and it will not install sensor specific packages.
# 3. It is intended to be run once, before pizero_bikecomputer_service
#    is installed.
#
# This script is based on the instructions from the pizero_bikecomputer
# foud here: https://qiita.com/hishi/items/46619b271daaa9ad41b3
#
# Usage: ./scripts/initial_setup.sh
#
#############################################################

###
# Function to ask user for input
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

#############################################################
# get user input
#############################################################

# temporarily disable error checking to allow for user input
set +e
prompt_and_store "Setup Python virtual environment?" setup_python_venv
if [[ "$setup_python_venv" == "true" ]]; then
    read -rp "📦 Enter virtual environment name (default: .venv): " venv_name
    venv_name="${venv_name:-.venv}"
    venv_path=~/"$venv_name"
fi
prompt_and_store "Install GUI(PyQt6) packages?" install_pyqt6
prompt_and_store "Install ANT+ packages?" install_ant_plus
prompt_and_store "Install GPS packages?" install_gps
prompt_and_store "Install Bluetooth packages?" install_bluetooth
prompt_and_store "Enable I2C?" enable_i2c
prompt_and_store "Enable SPI?" enable_spi
prompt_and_store "Install services?" install_services
if [[ "$install_services" == "true" ]]; then
    prompt_and_store "Using TFT/XWindow to start pizero_bikecomputer.service?" install_services_use_x
fi
set -e

#############################################################
# install packages
#############################################################

# system update
sudo apt update
sudo apt upgrade -y

# install essential packages
echo "🔧 Installing core packages..."
sudo apt install -y git python3-venv python3-yaml cython3 cmake python3-numpy sqlite3 libsqlite3-dev python3-pil python3-aiohttp python3-aiofiles python3-psutil
echo "✅ Core packages installed."

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
echo "🔧 Installing core pip packages..."
# essential
pip install oyaml polyline qasync pyqtgraph git+https://github.com/hishizuka/crdp.git
echo "✅ Core pip packages installed successfully."

if command -v raspi-config >/dev/null 2>&1; then
    has_raspi_config=true
else
    has_raspi_config=false
fi

# Install PyQt6 packages
if [[ "$install_pyqt6" == "true" ]]; then
    echo "🔧 Installing PyQt6 packages..."
    sudo apt install -y python3-pyqt6 python3-pyqt6.qtsvg pyqt6-dev-tools
    echo "✅ PyQt6 packages installed successfully."
    gui_option=""
else
    gui_option="--gui None"
fi

# Install ANT+ packages
if [[ "$install_ant_plus" == "true" ]]; then
    echo "🔧 Installing ANT+ packages..."
    sudo apt install -y python3-pip libusb-1.0-0 python3-usb
    # install as root to ensure there are no udev_rules permission issues from setuptools
    sudo pip3 install git+https://github.com/hishizuka/openant.git --break-system-packages
    echo "✅ ANT+ packages installed successfully."
fi

# Install GPS packages
if [[ "$install_gps" == "true" ]]; then
    echo "🔧 Installing GPS packages..."
    sudo apt install -y gpsd
    pip install gps3 timezonefinder
    if [[ "$has_raspi_config" == "true" ]]; then
        sudo raspi-config nonint do_serial_cons 1
        sudo raspi-config nonint do_serial_hw 0
    fi
    sudo systemctl enable gpsd
    sudo systemctl enable gpsd.socket
    #sudo systemctl start gpsd
    echo "✅ GPS packages installed successfully."
fi

# Install Bluetooth packages
if [[ "$install_bluetooth" == "true" ]]; then
    echo "🔧 Installing Bluetooth packages..."
    sudo apt install -y bluez-obexd
    pip install garminconnect stravacookies bluez-peripheral==0.2.0a3 tb-mqtt-client mmh3 timezonefinder
    echo "✅ Bluetooth packages installed successfully."
fi

# Enable SPI
if [[ "$enable_i2c" == "true" ]]; then
    pip install magnetic-field-calculator
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

# Enable SPI
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

#############################################################
# disable raspberry pi specific hardware
#############################################################

BOOT_CONFIG_FILE="/boot/firmware/config.txt"

# Disable audio on Raspberry Pi
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
    echo "🔧 Disabling Raspberry Pi camera..."
    sudo raspi-config nonint do_camera 1
fi

#############################################################
# test run
#############################################################

echo "🔧 Starting pizero_bikecomputer.py for initialize..."
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
stdbuf -oL python3 pizero_bikecomputer.py --init "$gui_option" 2>&1 | tee "$OUT_PIPE" &
APP_PID=$!

# Monitor the output for readiness
ready=0
while IFS= read -r line; do
    if [[ $ready -eq 0 && "$line" == *"quit"* ]]; then
        echo "ℹ️ 'quit' detected. Waiting 10s..."
        ready=1
    fi
    if [[ $ready -eq 1 && "$line" == *"quit done"* ]]; then
        sleep 10
        break
    fi
done < "$OUT_PIPE"

# check setting.conf
if [ -f setting.conf ]; then
    echo "✅ Startup test completed successfully."
else
    echo "❌ Application did not start correctly. Check logs or errors."
fi

#############################################################
# Install Services
#############################################################

if [[ "$install_services" == "true" ]]; then

    # GPS service configuration
    if [[ "$install_gps" == "true" ]]; then
        sudo cp scripts/install/etc/default/gpsd /etc/default/gpsd
    fi

    # install pizero_bikecomputer.service
    current_dir=$(pwd)
    script="$current_dir/pizero_bikecomputer.py"

    i_service_file="scripts/install/etc/systemd/system/pizero_bikecomputer.service"
    o_service_file="/etc/systemd/system/pizero_bikecomputer.service"

    # check if venv is set, in that case default to using venv to run the script
    #read -p "Use current virtualenv? [y/n] (y): " use_venv
    if [[ -n "$VIRTUAL_ENV" ]]; then
        script="$VIRTUAL_ENV/bin/python $script --output_log"
    else
    echo "No virtualenv used/activated. Default python will be used"
    fi

    if [[ "$install_services_use_x" == "true" ]]; then
        # add fullscreen option
        script="$script -f"
        envs="Environment=\"QT_QPA_PLATFORM=xcb\"\\nEnvironment=\"DISPLAY=:0\"\\nEnvironment=\"XAUTHORITY=/home/$USER/.Xauthority\"\\n"
        after="After=display-manager.service\\n"
    else
        envs="Environment=\"QT_QPA_PLATFORM=offscreen\"\\n"
        after=""
    fi

    if [ -f "$i_service_file" ]; then
        content=$(<"$i_service_file")
        content="${content/WorkingDirectory=/WorkingDirectory=$current_dir}"
        content="${content/ExecStart=/ExecStart=$script}"
        content="${content/User=/User=$USER}"
        content="${content/Group=/Group=$USER}"

        # inject environment variables
        content=$(echo "$content" | sed "/\[Install\]/i $envs")

        if [[ -n "$after" ]]; then
            content=$(echo "$content" | sed "/\[Service\]/i $after")
        fi
        echo "$content" | sudo tee $o_service_file > /dev/null
        sudo systemctl enable pizero_bikecomputer
    fi
fi

echo "✅ pizero_bikecomputer initial setup completed successfully! Please reboot."  # or "Now rebooting"
#sudo reboot

