#!/bin/bash
#
# buzzer.sh - Bike computer buzzer sound reproduction
#
# Reproduces Pioneer SGX-CA600 buzzer sounds and utility notifications
# using PKLCS1212E4001-R1 piezoelectric buzzer via kernel sysfs PWM.
#
# Hardware:
#   - PKLCS1212E4001-R1 on PWM1 (GPIO 13, physical pin 33)
#
# Setup (/boot/firmware/config.txt):
#   dtoverlay=pwm,pin=13,func=4
#   (reboot required after adding)
#
# Usage:
#   ./buzzer.sh <sound-name> [options]
#   ./buzzer.sh --list
#   ./buzzer.sh --test
#
# Options:
#   --shifted       Shift frequencies toward 4kHz resonance for louder output
#   --list          List all available sounds
#   --test          Play all sounds sequentially
#   --help          Show this help

set -euo pipefail

# ============================================================
# Configuration
# ============================================================

SHIFTED=false

# ============================================================
# Utility functions
# ============================================================

usage() {
    cat <<'USAGE'
Usage: buzzer.sh <sound-name> [options]

Sounds (SGX-CA600 - Pioneer):
  sgx-ca600-poweron     Ascending 3-tone scale
  sgx-ca600-poweroff    Descending 3-tone scale
  sgx-ca600-start       Two beeps at same pitch
  sgx-ca600-stop        Short + long beep
  sgx-ca600-lap         Low short + high long
  sgx-ca600-cancel      Two short beeps
  sgx-ca600-save        4-tone confirmation

Utility sounds:
  beep              Simple single beep at 4kHz
  beep-double       Double beep at 4kHz
  beep-triple       Triple beep at 4kHz
  alert             Urgent alert pattern
  navi-turn         Navigation turn notification

Options:
  --shifted         Shift frequencies toward 4kHz for max volume
  --list            List available sounds (names only)
  --test            Play all sounds with 1s interval
  --help            Show this help

Setup:
  Add to /boot/firmware/config.txt:
    dtoverlay=pwm,pin=13,func=4
  Then reboot.
USAGE
}

list_sounds() {
    echo "sgx-ca600-poweron"
    echo "sgx-ca600-poweroff"
    echo "sgx-ca600-start"
    echo "sgx-ca600-stop"
    echo "sgx-ca600-lap"
    echo "sgx-ca600-cancel"
    echo "sgx-ca600-save"
    echo "beep"
    echo "beep-double"
    echo "beep-triple"
    echo "alert"
    echo "navi-turn"
}

# ============================================================
# Kernel sysfs PWM control
# ============================================================

PWM_CHIP=""
PWM_PATH=""

# PWM1 channel index (GPIO 13 = PWM1 on BCM2835)
PWM_CHANNEL=1

detect_pwm() {
    # Find the pwmchip sysfs path
    local chip
    for chip in /sys/class/pwm/pwmchip*; do
        if [ -d "$chip" ]; then
            PWM_CHIP="$chip"
            break
        fi
    done

    if [ -z "$PWM_CHIP" ]; then
        echo "Error: No PWM chip found in /sys/class/pwm/" >&2
        echo "Add to /boot/firmware/config.txt:" >&2
        echo "  dtoverlay=pwm,pin=13,func=4" >&2
        echo "Then reboot." >&2
        exit 1
    fi

    PWM_PATH="$PWM_CHIP/pwm${PWM_CHANNEL}"
}

pwm_init() {
    detect_pwm

    # Export PWM channel if not already exported
    if [ ! -d "$PWM_PATH" ]; then
        echo "$PWM_CHANNEL" > "$PWM_CHIP/export" 2>/dev/null || true
        # Wait for sysfs node to appear
        local retries=10
        while [ ! -d "$PWM_PATH" ] && [ $retries -gt 0 ]; do
            sleep 0.1
            retries=$((retries - 1))
        done
    fi

    if [ ! -d "$PWM_PATH" ]; then
        echo "Error: Failed to export PWM channel at $PWM_PATH" >&2
        exit 1
    fi

    # Wait until udev rule applies writable permissions to PWM sysfs files.
    # This avoids first-run failures right after export.
    local writable_retries=40
    while [ $writable_retries -gt 0 ]; do
        if [ -w "$PWM_PATH/duty_cycle" ] \
            && [ -w "$PWM_PATH/period" ] \
            && [ -w "$PWM_PATH/enable" ]; then
            break
        fi
        sleep 0.05
        writable_retries=$((writable_retries - 1))
    done

    if [ ! -w "$PWM_PATH/duty_cycle" ] \
        || [ ! -w "$PWM_PATH/period" ] \
        || [ ! -w "$PWM_PATH/enable" ]; then
        echo "Error: PWM sysfs files are not writable: $PWM_PATH" >&2
        ls -l "$PWM_PATH" >&2 || true
        exit 1
    fi

    # Initialize: set a default period, duty=0, then enable
    echo 0 > "$PWM_PATH/duty_cycle"
    echo 250000 > "$PWM_PATH/period"    # 4kHz default
    echo 1 > "$PWM_PATH/enable"
}

cleanup() {
    if [ -n "$PWM_PATH" ] && [ -d "$PWM_PATH" ]; then
        echo 0 > "$PWM_PATH/duty_cycle" 2>/dev/null || true
        echo 0 > "$PWM_PATH/enable" 2>/dev/null || true
    fi
}
trap cleanup EXIT

# ============================================================
# Tone control
# ============================================================

tone_on() {
    local freq=$1
    local period_ns=$((1000000000 / freq))
    local duty_ns=$((period_ns / 2))
    # Set duty to 0 first to safely change period (duty must be <= period)
    echo 0 > "$PWM_PATH/duty_cycle"
    echo "$period_ns" > "$PWM_PATH/period"
    echo "$duty_ns" > "$PWM_PATH/duty_cycle"
}

tone_off() {
    echo 0 > "$PWM_PATH/duty_cycle"
}

# ============================================================
# Frequency shifting for PKLCS1212E4001-R1 (resonance: 4kHz)
# ============================================================

freq() {
    local original=$1
    if $SHIFTED; then
        # Shift toward 4kHz resonance
        # SGX-CA600 range (1900-2600): multiply by 2
        # Other: keep as-is
        if [ "$original" -le 3000 ]; then
            echo $((original * 2))
        else
            echo "$original"
        fi
    else
        echo "$original"
    fi
}

# ============================================================
# Sound definitions - SGX-CA600 (Pioneer)
# ============================================================
# Based on FFT analysis of recorded WAV files.
# Characteristic frequencies: ~1930Hz / ~2180Hz / ~2520Hz

sgx_ca600_poweron() {
    # Ascending scale: Low -> Mid -> High
    tone_on "$(freq 1928)"; sleep 0.0384; tone_off; sleep 0.0264
    tone_on "$(freq 2184)"; sleep 0.0464; tone_off; sleep 0.0272
    tone_on "$(freq 2524)"; sleep 0.0432; tone_off
}

sgx_ca600_poweroff() {
    # Descending scale: High -> Mid -> Low
    tone_on "$(freq 2518)"; sleep 0.0400; tone_off; sleep 0.0280
    tone_on "$(freq 2184)"; sleep 0.0472; tone_off; sleep 0.0256
    tone_on "$(freq 1932)"; sleep 0.0400; tone_off
}

sgx_ca600_start() {
    # Two beeps at same pitch
    tone_on "$(freq 2516)"; sleep 0.091; tone_off; sleep 0.098
    tone_on "$(freq 2516)"; sleep 0.092; tone_off
}

sgx_ca600_stop() {
    # Short + long at same pitch
    tone_on "$(freq 1927)"; sleep 0.093; tone_off; sleep 0.091
    tone_on "$(freq 1928)"; sleep 0.318; tone_off
}

sgx_ca600_lap() {
    # Low short + high long
    tone_on "$(freq 1929)"; sleep 0.091; tone_off; sleep 0.095
    tone_on "$(freq 2521)"; sleep 0.315; tone_off
}

sgx_ca600_cancel() {
    # Two short beeps
    tone_on "$(freq 1932)"; sleep 0.054; tone_off; sleep 0.032
    tone_on "$(freq 1927)"; sleep 0.059; tone_off
}

sgx_ca600_save() {
    # 4-tone confirmation
    tone_on "$(freq 1930)"; sleep 0.056; tone_off; sleep 0.025
    tone_on "$(freq 2520)"; sleep 0.070; tone_off; sleep 0.020
    tone_on "$(freq 2189)"; sleep 0.074; tone_off; sleep 0.016
    tone_on "$(freq 2522)"; sleep 0.059; tone_off
}

# ============================================================
# Utility sounds (optimized for 4kHz resonance)
# ============================================================

beep_single() {
    tone_on 4000; sleep 0.100; tone_off
}

beep_double() {
    tone_on 4000; sleep 0.080; tone_off; sleep 0.060
    tone_on 4000; sleep 0.080; tone_off
}

beep_triple() {
    tone_on 4000; sleep 0.060; tone_off; sleep 0.040
    tone_on 4000; sleep 0.060; tone_off; sleep 0.040
    tone_on 4000; sleep 0.060; tone_off
}

alert_sound() {
    # Urgent repeated alert
    local i
    for i in 1 2 3; do
        tone_on 4000; sleep 0.150; tone_off; sleep 0.100
    done
    sleep 0.200
    for i in 1 2 3; do
        tone_on 4000; sleep 0.150; tone_off; sleep 0.100
    done
}

navi_turn() {
    # Navigation turn notification: ascending double beep
    tone_on 3500; sleep 0.080; tone_off; sleep 0.050
    tone_on 4500; sleep 0.120; tone_off
}

# ============================================================
# Main
# ============================================================

play_sound() {
    case "$1" in
        sgx-ca600-poweron)   sgx_ca600_poweron ;;
        sgx-ca600-poweroff)  sgx_ca600_poweroff ;;
        sgx-ca600-start)     sgx_ca600_start ;;
        sgx-ca600-stop)      sgx_ca600_stop ;;
        sgx-ca600-lap)       sgx_ca600_lap ;;
        sgx-ca600-cancel)    sgx_ca600_cancel ;;
        sgx-ca600-save)      sgx_ca600_save ;;
        beep)            beep_single ;;
        beep-double)     beep_double ;;
        beep-triple)     beep_triple ;;
        alert)           alert_sound ;;
        navi-turn)       navi_turn ;;
        *)
            echo "Unknown sound: $1" >&2
            echo "Use --list to see available sounds." >&2
            return 1
            ;;
    esac
}

main() {
    local sound=""
    local do_test=false
    local do_list=false

    # Parse arguments
    while [ $# -gt 0 ]; do
        case "$1" in
            --shifted)
                SHIFTED=true
                shift
                ;;
            --list)
                do_list=true
                shift
                ;;
            --test)
                do_test=true
                shift
                ;;
            --help|-h)
                usage
                exit 0
                ;;
            -*)
                echo "Unknown option: $1" >&2
                usage >&2
                exit 1
                ;;
            *)
                sound="$1"
                shift
                ;;
        esac
    done

    if $do_list; then
        list_sounds
        exit 0
    fi

    # Initialize PWM via sysfs
    pwm_init

    if $do_test; then
        echo "Testing all sounds via sysfs PWM ($PWM_PATH)..."
        if $SHIFTED; then
            echo "(Frequencies shifted toward 4kHz resonance)"
        fi
        for s in $(list_sounds); do
            echo "  $s"
            play_sound "$s"
            sleep 1
        done
        echo "Done."
        exit 0
    fi

    if [ -z "$sound" ]; then
        usage >&2
        exit 1
    fi

    play_sound "$sound"
}

main "$@"
