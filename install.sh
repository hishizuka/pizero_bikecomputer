#!/bin/bash
set -euo pipefail
#############################################################
# This script sets up pizero_bikecomputer environment
# and is intended to be run on a fresh Raspberry Pi OS installation.
# 1. Creates a Python virtual environment, installs necessary
#    packages, and prepares the system for running pizero_bikecomputer
#    application.
# 2. Optionally installs pizero_bikecomputer.service and sensor packages.
#
# This script is based on the instructions from the pizero_bikecomputer
# foud here: https://qiita.com/hishi/items/46619b271daaa9ad41b3
#
# Usage: ./install.sh
#
#############################################################

###
# Function to ask user for input
# Returns "true" for yes, "false" for no, and exits for quit.
###
ask_user() {
    local prompt="$1"
    local answer
    while true; do
        read -rp "$prompt [y/n/q(uit)]: " answer || return 2
        answer="$(echo "$answer" | tr 'A-Z' 'a-z')"

        case "$answer" in
            y|yes) return 0 ;;
            n|no) return 1 ;;
            q|quit) return 2 ;;
            *) echo "Invalid input. Please answer with y, n, or q." ;;
        esac
    done
}

choose_number() {
    local prompt="$1" maximum="$2" default="$3" target="$4"
    local choice
    while true; do
        if ! read -rp "$prompt: " choice; then
            echo "Input closed. Exiting installer."
            exit 1
        fi
        choice="${choice:-$default}"
        case "$choice" in
            [0-9])
                if (( choice <= maximum )); then
                    printf -v "$target" '%s' "$choice"
                    return 0
                fi
                ;;
            q|Q|quit|QUIT) echo "👋 Quitting...bye!"; exit 0 ;;
        esac
        echo "Invalid input. Choose one of the displayed options."
    done
}

prompt_and_store() {
    local prompt="$1"
    local var_name="$2"
    local task_prompt_result=0
    ask_user "$prompt" || task_prompt_result=$?
    case "$task_prompt_result" in
        0) printf -v "$var_name" '%s' true ;;
        1) printf -v "$var_name" '%s' false ;;
        2) echo "👋 Quitting...bye!"; exit 0 ;;
    esac
}

install_timezonefinder_and_flatbuffers() {
    if [[ "${INSTALL_TZ_DEPS_DONE:-false}" == "true" ]]; then
        return 0
    fi
    local pip_tmp_dir
    pip_tmp_dir="$HOME/tmp/pip"
    mkdir -p "$pip_tmp_dir"
    TMPDIR="$pip_tmp_dir" pip install timezonefinder
    rm -rf "$pip_tmp_dir"
    # Force PyPI to avoid legacy versions from extra index settings.
    pip uninstall -y flatbuffers
    PIP_CONFIG_FILE=/dev/null pip install -U --no-cache-dir -i https://pypi.org/simple flatbuffers
    INSTALL_TZ_DEPS_DONE=true
}

install_i2c_support_packages() {
    if [[ "${INSTALL_I2C_SUPPORT_DONE:-false}" == "true" ]]; then
        return 0
    fi
    sudo apt install -y python3-smbus2 libgpiod3 libgpiod-dev python3-libgpiod
    INSTALL_I2C_SUPPORT_DONE=true
}

enable_i2c_interface() {
    if [[ "${ENABLE_I2C_DONE:-false}" == "true" ]]; then
        return 0
    fi
    if [[ "${has_raspi_config:-false}" == "true" ]]; then
        # raspi-config replaces the entire i2c_arm line; preserve its baudrate.
        sudo sed -i -E \
            '/^[[:space:]]*dtparam=i2c_arm=/s/,i2c_arm_baudrate=([^,#[:space:]]+)/\ndtparam=i2c_arm_baudrate=\1/' \
            "$BOOT_CONFIG_FILE"
        sudo raspi-config nonint do_i2c 0
        if [[ "$use_i2c_400khz" == "true" ]]; then
            if grep -Eq '^[[:space:]]*dtparam=i2c_arm_baudrate=' "$BOOT_CONFIG_FILE"; then
                sudo sed -i -E \
                    's/^([[:space:]]*dtparam=i2c_arm_baudrate=)[^,#[:space:]]*/\1400000/' \
                    "$BOOT_CONFIG_FILE"
            else
                sudo sed -i '/^dtparam=i2c_arm=on$/a dtparam=i2c_arm_baudrate=400000' "$BOOT_CONFIG_FILE"
            fi
        fi
    fi
    ENABLE_I2C_DONE=true
}

enable_uart_interface() {
    if [[ "${ENABLE_UART_DONE:-false}" == "true" ]]; then
        return 0
    fi
    if [[ "${has_raspi_config:-false}" == "true" ]]; then
        sudo raspi-config nonint do_serial_cons 1
        sudo raspi-config nonint do_serial_hw 0
    fi
    ENABLE_UART_DONE=true
}

install_mip_pwm_backlight() {
    sudo apt install -y device-tree-compiler
    sudo dtc -@ -I dts -O dtb -o "${BOOT_CONFIG_FILE%/*}/overlays/mip-pwm-backlight.dtbo" \
        scripts/install/boot/overlays/mip-pwm-backlight.dts
    sudo install -m 644 scripts/install/etc/udev/rules.d/99-mip-pwm-backlight.rules /etc/udev/rules.d/
    sudo usermod -aG video "$TARGET_USER"
}

install_memory_lcd_support() {
    local driver_dir="$HOME/memory-lcd-drm"
    sudo apt install -y build-essential
    if [[ "$display_profile" == "drm" ]]; then
        local kernel_release kernel_flavour
        kernel_release="$(uname -r)"
        case "$kernel_release" in
            *-rpi-2712) kernel_flavour=2712 ;;
            *-rpi-v8) kernel_flavour=v8 ;;
            *-rpi-v6) kernel_flavour=v6 ;;
            *-rpi-v7) kernel_flavour=v7 ;;
            *-rpi-v7l) kernel_flavour=v7l ;;
            *) echo "❌ Unsupported kernel: $kernel_release. See memory-lcd-drm's installation guide."; return 1 ;;
        esac
        sudo apt install -y device-tree-compiler dkms \
            "linux-image-rpi-$kernel_flavour" "linux-headers-rpi-$kernel_flavour"
        if [[ ! -f "/lib/modules/$kernel_release/build/Makefile" ]]; then
            echo "❌ Headers for $kernel_release are missing. Reboot into the updated kernel and rerun the installer."
            return 1
        fi
    fi

    if [[ ! -d "$driver_dir" ]]; then
        git clone https://github.com/hishizuka/memory-lcd-drm.git "$driver_dir"
    fi
    if [[ "$display_profile" == "drm" ]]; then
        sudo make -C "$driver_dir" install_dkms
        sudo usermod -aG video "$TARGET_USER"
        echo "✅ memory-lcd-drm installed (module and overlay: sharp-drm)."
    fi
    if [[ "$install_dmabuf_presenter" == "true" ]]; then
        sudo apt install -y pkg-config libdrm-dev libgbm-dev libegl-dev libgles-dev
        make -C "$driver_dir" presenter
        sudo make -C "$driver_dir" install_presenter
        sudo usermod -aG video,render "$TARGET_USER"
        echo "✅ memory-lcd-drm DMA-BUF presenter installed; GUI selection unchanged."
        echo "   Enable VC4 KMS before using the presenter."
    fi
}

set_bluez_config_value() {
    local bluez_config="$1"
    local section="$2"
    local key="$3"
    local value="$4"

    if grep -Eq "^[#[:space:]]*${key}[[:space:]]*=" "$bluez_config"; then
        sudo sed -i -E \
            "s|^[#[:space:]]*${key}[[:space:]]*=.*|${key} = ${value}|" \
            "$bluez_config"
    elif grep -Fxq "[$section]" "$bluez_config"; then
        sudo sed -i "/^\[$section\]$/a${key} = ${value}" "$bluez_config"
    else
        printf '\n[%s]\n%s = %s\n' "$section" "$key" "$value" |
            sudo tee -a "$bluez_config" >/dev/null
    fi
    grep -Fxq "${key} = ${value}" "$bluez_config"
}

configure_bluez_ble_compatibility() {
    local bluez_config=/etc/bluetooth/main.conf

    # Insert in reverse order so missing keys retain the documented order.
    set_bluez_config_value "$bluez_config" LE ScanWindowDiscovery 48
    set_bluez_config_value "$bluez_config" LE ScanIntervalDiscovery 96
    set_bluez_config_value "$bluez_config" GATT ExchangeMTU 247
}

configure_cm0_bt_coexistence() {
    # firmware-brcm80211 ships the CYW43439 NVRAM with btc_mode=0, while other Raspberry
    # Pi Wi-Fi chips use btc_mode=1. With btc_mode=0, BLE sensor connections failed on
    # CM0 while Wi-Fi was associated in power save. The diversion survives package updates.
    local base_nvram=/usr/lib/firmware/cypress/cyfmac43439-sdio.txt
    local board_nvram=/usr/lib/firmware/brcm/brcmfmac43439-sdio.raspberrypi,0-compute-module.txt
    [[ -r /proc/device-tree/compatible ]] || return 0
    tr '\0' '\n' < /proc/device-tree/compatible | grep -Fxq 'raspberrypi,0-compute-module' || return 0
    [[ -f "$base_nvram" ]] || return 1
    sudo dpkg-divert --local --rename --divert "${board_nvram}.distrib" --add "$board_nvram"
    sed -E 's/^btc_mode=0$/btc_mode=1/' "$base_nvram" | sudo tee "$board_nvram" > /dev/null
    grep -Fxq 'btc_mode=1' "$board_nvram"
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
echo "Select GPS:"
echo "  0) No GPS"
echo "  1) u-blox direct UBX (pyubx2; MAX-M10S/N etc., UART or I2C)"
echo "  2) UART GPS through GPSD (NMEA receivers)"
echo "  3) Sony CXD56xx GNSS over I2C"
echo "  q) Quit installer"
choose_number "Choose GPS [0/1/2/3/q]" 3 "" gps_choice
gps_backends=(none ublox gpsd cxd56xx)
gps_backend="${gps_backends[gps_choice]}"
prompt_and_store "Install Bluetooth packages?" install_bluetooth
prompt_and_store "Install rpi-ble-tunnel integration?" install_rpi_ble_tunnel
prompt_and_store "Enable I2C?" enable_i2c
use_i2c_400khz=false
if [[ "$gps_backend" == "cxd56xx" ]]; then
    echo "ℹ️ Sony CXD56xx requires I2C at 400kHz; configuring it automatically."
    use_i2c_400khz=true
elif [[ "$enable_i2c" == "true" ]]; then
    echo "ℹ️ BHI360/BHI385 require I2C at 400kHz."
    prompt_and_store "Configure I2C at 400kHz?" use_i2c_400khz
fi
echo "Select display boot settings:"
echo "  0) Keep existing display settings (including non-MIP displays)"
echo "  1) MIP with Memory LCD DRM (recommended)"
echo "  2) MIP with spidev (active-high SPI0 CE0; CE1 unused)"
echo "  3) PWM1 buzzer only (no installer-managed MIP display)"
echo "  q) Quit installer"
choose_number "Choose display settings [0-3/q, default 0]" 3 0 display_choice
enable_spi=false
use_bryton_rider_s800_display=false
use_pwm_backlight=false
use_pwm_buzzer=false
mip_only_framebuffer=false
install_dmabuf_presenter=false
display_name=""
service_display_default=""
case "$display_choice" in
    0) display_profile=existing ;;
    1) display_profile=drm; service_display_default=0 ;;
    2) display_profile=spidev; service_display_default=1 ;;
    3) display_profile=buzzer; use_pwm_buzzer=true ;;
esac
if [[ "$display_profile" == "drm" || "$display_profile" == "spidev" ]]; then
    enable_spi=true
    echo "Select MIP panel:"
    echo "  1) JDI 400x240, 8 colors (LPM027M128B/C)"
    echo "  2) JDI 640x480, 8 colors (LPM044M141A)"
    echo "  3) AUO/Azumo 272x451, 64 colors"
    echo "  4) Sharp 400x240 monochrome (LS027B7DH01)"
    echo "  5) Sharp 320x240 monochrome (LS044Q7DH01)"
    last_panel=5
    if [[ "$display_profile" == "drm" ]]; then
        echo "  6) Two AUO/Azumo 272x451 panels, 64 colors (CE0 and CE1)"
        last_panel=6
    fi
    echo "  0/q) Quit installer"
    choose_number "Choose panel [0-$last_panel/q]" "$last_panel" "" panel_choice
    case "$panel_choice" in
        0) echo "👋 Quitting...bye!"; exit 0 ;;
        1) display_name=MIP_JDI_color_400x240; panel_params=width=400,height=240,colors=8 ;;
        2) display_name=MIP_JDI_color_640x480; panel_params=width=640,height=480,colors=8 ;;
        3) display_name=MIP_Azumo_color_272x451; panel_params=width=272,height=451,colors=64 ;;
        4) display_name=MIP_Sharp_mono_400x240; panel_params=panel_type=sharp_mono,width=400,height=240,colors=2 ;;
        5) display_name=MIP_Sharp_mono_320x240; panel_params=panel_type=sharp_mono,width=320,height=240,colors=2 ;;
        6) display_name=MIP_Azumo_color_272x451; panel_params=width=272,height=451,colors=64,dual_panel=1 ;;
    esac
    prompt_and_store "Use the Bryton Rider S800 Sitronix touchscreen?" use_bryton_rider_s800_display
    prompt_and_store "Use PWM0 (GPIO18) for the MIP backlight?" use_pwm_backlight
    prompt_and_store "Use PWM1 (GPIO13) for the buzzer?" use_pwm_buzzer
    if [[ "$display_profile" == "drm" ]]; then
        prompt_and_store "Disable the firmware framebuffer for MIP (max_framebuffers=0)?" mip_only_framebuffer
    fi
else
    prompt_and_store "Enable SPI for other hardware?" enable_spi
fi
if [[ "$install_pyqt6" == "true" && "$display_profile" != "spidev" ]]; then
    prompt_and_store "Install optional memory-lcd-drm DMA-BUF presenter (experimental; GUI unchanged)?" install_dmabuf_presenter
fi
prompt_and_store "Install services?" install_services
if [[ "$install_services" == "true" ]]; then
    echo "Select service display:"
    echo "  0) linuxfb (/dev/fb0; memory-lcd-drm or PiTFT)"
    echo "  1) Offscreen"
    echo "  2) X Window (xcb)"
    echo "  q) Quit installer"
    service_display_prompt="Choose service display [0/1/2/q"
    if [[ -n "$service_display_default" ]]; then
        service_display_prompt+=", default $service_display_default"
    fi
    choose_number "$service_display_prompt]" 2 "$service_display_default" service_display
fi
set -e
TARGET_USER="${SUDO_USER:-${LOGNAME:-$USER}}"
BOOT_CONFIG_FILE="/boot/firmware/config.txt"
DISPLAY_CONFIG_SCRIPT="scripts/install/display_config.py"

pgm_dir="$HOME/pizero_bikecomputer"
if [[ -f "${BASH_SOURCE[0]:-}" ]] && [[ -f "$(dirname -- "${BASH_SOURCE[0]}")/pizero_bikecomputer.py" ]]; then
    pgm_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
fi

# Keep the order required by the SPI and PWM consumers.
boot_display_options=()
if [[ "$enable_spi" == "true" ]]; then
    boot_display_options+=(dtparam=spi=on)
fi
if [[ "$display_profile" == "drm" ]]; then
    if [[ "$use_pwm_backlight" == "true" ]]; then
        panel_params+=,backlight_pwm
    fi
    boot_display_options+=("dtoverlay=sharp-drm,$panel_params")
elif [[ "$display_profile" == "spidev" ]]; then
    boot_display_options+=(dtoverlay=spi0-1cs-inverted)
fi
if [[ "$use_pwm_backlight" == "true" && "$use_pwm_buzzer" == "true" ]]; then
    boot_display_options+=(dtoverlay=pwm-2chan,pin=18,func=2,pin2=13,func2=4)
elif [[ "$use_pwm_buzzer" == "true" ]]; then
    boot_display_options+=(dtoverlay=pwm,pin=13,func=4)
elif [[ "$use_pwm_backlight" == "true" && "$display_profile" == "spidev" ]]; then
    boot_display_options+=(dtoverlay=pwm,pin=18,func=2)
fi
if [[ "$use_pwm_backlight" == "true" && "$display_profile" == "spidev" ]]; then
    boot_display_options+=(dtoverlay=mip-pwm-backlight)
fi
if [[ "$use_bryton_rider_s800_display" == "true" ]]; then
    boot_display_options+=(dtoverlay=sitronix-touch)
fi
if [[ "$use_pwm_backlight" == "true" || "$use_pwm_buzzer" == "true" ]]; then
    # End overlay scope so audio=off applies to the base tree, not VC4 HDMI audio.
    boot_display_options+=(dtoverlay= dtparam=audio=off)
fi
if [[ "$mip_only_framebuffer" == "true" ]]; then
    boot_display_options+=(max_framebuffers=0)
fi

#############################################################
# install packages
#############################################################

# system update
sudo apt update
sudo apt upgrade -y

# install essential packages
echo "🔧 Installing core packages..."
# trixie
sudo apt install -y git cython3 cmake python3-setuptools python3.13-venv python3-numpy sqlite3 libsqlite3-dev python3-pil python3-aiohttp python3-psutil
echo "✅ Core packages installed."

if [[ ! -d "$pgm_dir" ]]; then
    git clone https://github.com/hishizuka/pizero_bikecomputer.git "$pgm_dir"
fi
if [[ "$display_profile" != "existing" ]]; then
    if [[ ! -f "$pgm_dir/$DISPLAY_CONFIG_SCRIPT" ]]; then
        echo "Update the Pi Zero Bikecomputer checkout at $pgm_dir and rerun the installer." >&2
        exit 1
    fi
    python3 "$pgm_dir/$DISPLAY_CONFIG_SCRIPT" boot "$BOOT_CONFIG_FILE" "$display_profile" "${boot_display_options[@]}"
fi

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
pip install fitparse oyaml polyline requests
echo "✅ Core pip packages installed successfully."

if command -v raspi-config >/dev/null 2>&1; then
    has_raspi_config=true
else
    has_raspi_config=false
fi

# Install PyQt6 packages
if [[ "$install_pyqt6" == "true" ]]; then
    echo "🔧 Installing PyQt6 packages..."
    sudo apt install -y python3-pyqt6 python3-pyqt6.qtsvg qt6-svg-plugins pyqt6-dev-tools
    pip install qasync pyqtgraph
    # sudo apt install -y python3-pyside6.qtlocation
    echo "✅ PyQt6 packages installed successfully."
    gui_option=()
else
    gui_option=(--gui None)
fi

# Install ANT+ packages
if [[ "$install_ant_plus" == "true" ]]; then
    echo "🔧 Installing ANT+ packages..."
    # trixie
    sudo apt install -y python3-pip python3-usb python3-serial
    pip3 install --ignore-installed git+https://github.com/hishizuka/openant.git
    openant_udev_installer="$(command -v openant-install-udev || true)"
    if [[ -z "$openant_udev_installer" ]]; then
        echo "❌ openant-install-udev was not found in PATH after openant install."
        exit 1
    fi
    sudo "$openant_udev_installer"
    sudo usermod -aG dialout "$TARGET_USER"
    echo "✅ ANT+ packages installed successfully."
fi

# Install GPS packages
if [[ "$gps_backend" != "none" ]]; then
    echo "🔧 Installing GPS packages..."

    install_timezonefinder_and_flatbuffers

    if [[ "$gps_backend" == "ublox" ]]; then
        echo "🔧 Installing u-blox direct UBX GPS packages..."
        # pyserial is required for UART; smbus2 keeps MAX-M10S I2C usable.
        sudo apt install -y python3-smbus2 python3-serial
        pip install pyubx2 azarashi
        enable_uart_interface
        enable_i2c_interface
        echo "✅ u-blox direct UBX GPS packages installed successfully."
    fi

    if [[ "$gps_backend" == "gpsd" ]]; then
        echo "🔧 Installing GPSD UART GPS packages..."
        sudo apt install -y gpsd python3-gps libffi-dev
        enable_uart_interface
        sudo systemctl enable gpsd
        sudo systemctl enable gpsd.socket
        echo "✅ GPSD UART GPS packages installed successfully."
    fi

    if [[ "$gps_backend" == "cxd56xx" ]]; then
        echo "🔧 Installing Sony CXD56xx GNSS packages..."
        install_i2c_support_packages
        sudo apt install -y build-essential python3-dev gpiod
        pip install --no-cache-dir rpi-cxd56xx-gnss azarashi
        sudo usermod -aG i2c,gpio "$TARGET_USER"
        enable_i2c_interface
        echo "✅ Sony CXD56xx GNSS packages installed successfully."
        echo "ℹ️ Check the GPIO settings before starting the application."
        echo "   See the Sony CXD56xx section in doc/software_installation.md, then reboot."
    fi

    echo "✅ GPS packages installed successfully."
fi

# Install Bluetooth packages
if [[ "$install_bluetooth" == "true" ]]; then
    echo "🔧 Installing Bluetooth packages..."
    # for trixie
    sudo usermod -aG bluetooth "$TARGET_USER"
    sudo rfkill unblock bluetooth
    # install packages
    sudo apt install -y bluez-obexd libffi-dev
    # for raspberry pi zero (building with pip is extremely heavy.)
    sudo apt install -y python3-pydantic python3-orjson
    configure_bluez_ble_compatibility
    configure_cm0_bt_coexistence
    pip install bleak pycycling
    pip install gadgetbridge-rpi-link
    pip install garminconnect tb-mqtt-client mmh3
    install_timezonefinder_and_flatbuffers

    echo "✅ Bluetooth packages installed successfully."
fi

# Enable I2C
if [[ "$enable_i2c" == "true" ]]; then
    install_i2c_support_packages
    pip install magnetic-field-calculator
    # Enable I2C on Raspberry Pi
    echo "🔧 Enabling i2c on Raspberry Pi..."
    enable_i2c_interface
    # add pi to i2c if not already a member
    #if ! groups "$TARGET_USER" | grep -qw i2c; then
    #  sudo adduser "$TARGET_USER" i2c
    #fi
    echo "✅ I2C enabled successfully"
fi

# Enable SPI
if [[ "$enable_spi" == "true" ]]; then
    sudo apt install -y libgpiod3 libgpiod-dev python3-libgpiod python3-spidev
    sudo usermod -aG spi,gpio "$TARGET_USER"
    if [[ "$display_profile" == "existing" && "$has_raspi_config" == "true" ]] &&
        [[ "$(raspi-config nonint get_spi)" != "0" ]]; then
        sudo raspi-config nonint do_spi 0
    fi
fi

if [[ "$display_profile" == "drm" || "$install_dmabuf_presenter" == "true" ]]; then
    install_memory_lcd_support
fi

#############################################################
# disable raspberry pi specific hardware
#############################################################

cd "$pgm_dir"

if [[ "$display_profile" == "spidev" && "$use_pwm_backlight" == "true" ]]; then
    install_mip_pwm_backlight
fi

if [[ "$use_bryton_rider_s800_display" == "true" ]]; then
    sudo usermod -aG input "$TARGET_USER"
    sudo install -m 644 scripts/install/etc/udev/rules.d/99-sitronix-touch.rules /etc/udev/rules.d/
fi

# Disable LED
if [ -f "$BOOT_CONFIG_FILE" ]; then
    # Append LED trigger settings if missing to keep LEDs off during normal operation
    if ! grep -q "^dtparam=pwr_led_trigger=none" "$BOOT_CONFIG_FILE"; then
        echo "dtparam=pwr_led_trigger=none" | sudo tee -a "$BOOT_CONFIG_FILE" >/dev/null
    fi
    if ! grep -q "^dtparam=act_led_trigger=none" "$BOOT_CONFIG_FILE"; then
        echo "dtparam=act_led_trigger=none" | sudo tee -a "$BOOT_CONFIG_FILE" >/dev/null
    fi
fi

# Disable camera on Raspberry Pi
if [[ "$has_raspi_config" == "true" ]]; then
    echo "🔧 Disabling Raspberry Pi camera..."
    sudo raspi-config nonint do_camera 1
fi

#############################################################
# test run
#############################################################

if [[ "$install_rpi_ble_tunnel" == "true" ]]; then
    bash scripts/install/install-rpi-ble-tunnel.sh
fi

if [[ "$install_ant_plus" == "true" ]] && \
    { [[ ! -f img/logos/ant_plus_icon_standard.png ]] || \
      [[ ! -f img/logos/ant_plus_icon_reverse.png ]]; }; then
    echo "ℹ️ Official ANT+ icons are not included in this repository."
    echo "   ANT+ Adopters can download the ANT+ Brand Tools package here:"
    echo "   https://www.thisisant.com/developer/ant-plus/certification/#115_tab"
    echo "   Place the official PNG files at:"
    echo "   $pgm_dir/img/logos/ant_plus_icon_standard.png"
    echo "   $pgm_dir/img/logos/ant_plus_icon_reverse.png"
    echo "   The application uses (ANT+) text until both files are installed."
fi

# A configured MIP display may be unavailable until the new boot settings take effect.
if [[ -z "$display_name" || ! -f setting.conf ]]; then
    echo "🔧 Initializing pizero_bikecomputer.py..."
    if QT_QPA_PLATFORM=offscreen python3 -u pizero_bikecomputer.py --init "${gui_option[@]}" &&
        [[ -f setting.conf ]]; then
        echo "✅ Startup test completed successfully."
    else
        echo "❌ Application did not start correctly. Check logs or errors."
    fi
fi

if [[ -n "$display_name" ]]; then
    # A running service saves its old settings when stopped.
    if systemctl is-active --quiet pizero_bikecomputer.service; then
        sudo systemctl stop pizero_bikecomputer.service
        echo "The bike computer service was stopped. Reboot to use the new display settings."
    fi
    python3 "$DISPLAY_CONFIG_SCRIPT" settings setting.conf "$display_name" "$use_pwm_backlight"
fi
if [[ "$display_profile" != "existing" ]]; then
    sudo python3 "$DISPLAY_CONFIG_SCRIPT" boot --apply "$BOOT_CONFIG_FILE" "$display_profile" "${boot_display_options[@]}"
fi

#############################################################
# Install Services
#############################################################

if [[ "$install_services" == "true" ]]; then

    # GPS service configuration
    if [[ "$gps_backend" == "gpsd" ]]; then
        sudo cp scripts/install/etc/default/gpsd /etc/default/gpsd
        sudo systemctl start gpsd
    fi

    # install pizero_bikecomputer.service
    current_dir=$(pwd)
    script="$current_dir/pizero_bikecomputer.py"

    i_service_file="scripts/install/etc/systemd/system/pizero_bikecomputer.service"
    o_service_file="/etc/systemd/system/pizero_bikecomputer.service"

    log_file="$current_dir/log/debug.log"
    i_post_exec_file="scripts/install/usr/local/bin/rotate_debug_log.sh"
    o_post_exec_file="/usr/local/bin/rotate_debug_log.sh"

    # check if venv is set, in that case default to using venv to run the script
    #read -p "Use current virtualenv? [y/n] (y): " use_venv
    if [[ -n "${VIRTUAL_ENV:-}" ]]; then
        script="$VIRTUAL_ENV/bin/python $script"
    else
        echo "No virtualenv used/activated. Default python will be used"
    fi

    after=""
    case "$service_display" in
        2)
            script="$script -f"
            after="After=display-manager.service"
            service_envs=(
                'Environment="QT_QPA_PLATFORM=xcb"'
                'Environment="DISPLAY=:0"'
                "Environment=\"XAUTHORITY=/home/$TARGET_USER/.Xauthority\""
            )
            ;;
        0)
            service_envs=(
                'Environment="QT_QPA_PLATFORM=linuxfb:fb=/dev/fb0"'
                'Environment="QT_QPA_FB_HIDECURSOR=1"'
            )
            ;;
        1)
            service_envs=('Environment="QT_QPA_PLATFORM=offscreen"')
            ;;
    esac

    touch_env='Environment="QT_QPA_EVDEV_TOUCHSCREEN_PARAMETERS=/dev/input/touchscreen"'
    if [[ "$use_bryton_rider_s800_display" == "true" ]] ||
        { [[ "$display_profile" == "existing" ]] &&
          grep -Fxq "$touch_env" "$o_service_file" 2>/dev/null; }; then
        service_envs+=("$touch_env")
    fi
    printf -v envs '%s\n' "${service_envs[@]}"
    envs="${envs%$'\n'}"

    if [ -f "$i_service_file" ]; then
        content=$(<"$i_service_file")
        content="${content/WorkingDirectory=/WorkingDirectory=$current_dir}"
        content="${content/ExecStartPre=/ExecStartPre=$o_post_exec_file}"
        content="${content/ExecStart=/ExecStart=$script}"
        content="${content/ExecStopPost=/ExecStopPost=$o_post_exec_file}"
        content="${content/User=/User=$TARGET_USER}"
        content="${content/Group=/Group=$TARGET_USER}"
        content="${content/StandardOutput=/StandardOutput=append:$log_file}"

        content="${content/@AFTER@/$after}"
        content="${content/@ENVIRONMENT@/$envs}"
        printf '%s\n' "$content" | sudo tee "$o_service_file" > /dev/null
        sudo systemctl daemon-reload
        sudo systemctl enable pizero_bikecomputer
    fi

    if [ -f "$i_post_exec_file" ]; then
        content=$(<"$i_post_exec_file")
        content="${content/LOG=/LOG=$log_file}"

        printf '%s\n' "$content" | sudo tee "$o_post_exec_file" > /dev/null
        sudo chmod 755 "$o_post_exec_file"
    fi

fi

echo "✅ pizero_bikecomputer initial setup completed successfully! Please reboot."  # or "Now rebooting"
#sudo reboot
