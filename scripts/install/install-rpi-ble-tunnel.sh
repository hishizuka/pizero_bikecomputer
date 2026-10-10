#!/bin/bash
# Install the generic caller-managed rpi-ble-tunnel service from its own repository.
set -euo pipefail
task_root=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
task_repository=${1:-"$task_root/tmp/ref/rpi-ble-tunnel"}
if [[ $# == 1 && ( "$1" == --help || "$1" == -h ) ]]; then
    printf 'Usage: bash %s [rpi-ble-tunnel checkout]\n' "$0"
    exit 0
fi
if [[ $# -gt 1 ]]; then
    printf 'Usage: bash %s [rpi-ble-tunnel checkout]\n' "$0" >&2
    exit 2
fi
if [[ ! -d "$task_repository" ]]; then
    git clone https://github.com/hishizuka/rpi-ble-tunnel.git "$task_repository"
fi
if [[ ! -f "$task_repository/pi/rpi-ble-tunnel-service-control.py" ]]; then
    printf 'This checkout does not support caller-managed rpi-ble-tunnel. Update rpi-ble-tunnel first.\n' >&2
    exit 2
fi
bash "$task_repository/scripts/install-pi-network.sh" --caller-managed
