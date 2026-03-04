import time

# Prefer a prebuilt extension if present, otherwise build in-place.
try:
    from bhi3_s_helper import BHI3_S
except Exception:
    import pyximport
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
