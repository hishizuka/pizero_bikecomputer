#!/bin/bash
#############################################################
# This script installs the Pi Zero Bike Computer service.
#
# It should be run as root and should be run when the device is ready
# to use as a the bike computer. Once installed, the service will
# start automatically on boot.
#############################################################
current_dir=$(pwd)
project_root_dir=$(dirname "$current_dir")
script="$project_root_dir/pizero_bikecomputer.py"

i_service_file="$current_dir/install/etc/systemd/system/pizero_bikecomputer.service"
o_service_file="/etc/systemd/system/pizero_bikecomputer.service"

read -p "Using TFT/XWindow? [y/n] (n): " use_x

# check if venv is set, in that case default to using venv to run the script
#read -p "Use current virtualenv? [y/n] (y): " use_venv

if [[ -n "$VIRTUAL_ENV" ]]; then
  script="$VIRTUAL_ENV/bin/python $script --output_log"
else
  echo "No virtualenv used/activated. Default python will be used"
fi

if [[ "$use_x" == "y" ]]; then
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
    content="${content/WorkingDirectory=/WorkingDirectory=$project_root_dir}"
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
