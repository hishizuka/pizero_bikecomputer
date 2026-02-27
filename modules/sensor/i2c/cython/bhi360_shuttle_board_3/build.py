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

while True:
    try:
        heading_deg = f"{bhi3_s.heading:.0f}°"
        pitch_deg = f"{bhi3_s.pitch:.0f}°"
        roll_deg = f"{bhi3_s.roll:.0f}°"
        print(f"heading={heading_deg}, pitch={pitch_deg}, roll={roll_deg}, acc_rms_norm={bhi3_s.acc_rms_norm}, pressure={bhi3_s.pressure}, temperature={bhi3_s.temperature}, humidity={bhi3_s.humidity}")
        print(f"moving={bhi3_s.moving}, acc={bhi3_s.acc}")
        print()
        time.sleep(1)
    except KeyboardInterrupt:
        print()
        break
