import time
import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
MODULE_NAME = "bhi3_s_helper"
TARGET_MARKER = BASE_DIR / "__pycache__" / f"{MODULE_NAME}.target"


def prepare_bhi3_target():
    target = os.environ.get("BHI3_TARGET", "").strip().lower()
    try:
        import smbus2
        bus = smbus2.SMBus(1)
        try:
            chip_id = bus.read_byte_data(0x28, 0x2B)
            target = {0x7A: "bhi360", 0x7C: "bhi385"}.get(chip_id, target)
        finally:
            bus.close()
    except Exception:
        pass

    if target in ("360", "385"):
        target = f"bhi{target}"
    if target not in ("bhi360", "bhi385"):
        return

    os.environ["BHI3_TARGET"] = target
    try:
        previous_target = TARGET_MARKER.read_text().strip()
    except OSError:
        previous_target = ""

    if previous_target != target:
        remove_helper_extensions()
    TARGET_MARKER.parent.mkdir(exist_ok=True)
    TARGET_MARKER.write_text(f"{target}\n")


def remove_helper_extensions():
    for path in BASE_DIR.glob(f"{MODULE_NAME}*.so"):
        path.unlink(missing_ok=True)


# Prefer a prebuilt extension if present, otherwise build in-place.
prepare_bhi3_target()
try:
    from bhi3_s_helper import BHI3_S
except ImportError:
    import pyximport

    remove_helper_extensions()
    pyximport.install(inplace=True, language_level=3)
    from bhi3_s_helper import BHI3_S

bhi3_s = BHI3_S(1)

print(f"{bhi3_s.status=}")


def format_vec3(vec):
    return f"[{vec[0]:.3f}, {vec[1]:.3f}, {vec[2]:.3f}]"


while True:
    try:
        heading_deg = f"{bhi3_s.heading:.0f}°"
        pitch_deg = f"{bhi3_s.pitch:.0f}°"
        roll_deg = f"{bhi3_s.roll:.0f}°"
        acc_str = format_vec3(bhi3_s.acc)
        gyro_str = format_vec3(bhi3_s.gyro)
        print(
            f"heading={heading_deg}, pitch={pitch_deg}, roll={roll_deg}, "
            f"acc_rms_norm={bhi3_s.acc_rms_norm:.3f}, pressure={bhi3_s.pressure:.3f}, "
            f"temperature={bhi3_s.temperature}, humidity={bhi3_s.humidity}"
        )
        print(f"moving={bhi3_s.moving}, acc={acc_str}, gyro={gyro_str}")
        print()
        time.sleep(1)
    except KeyboardInterrupt:
        print()
        break
