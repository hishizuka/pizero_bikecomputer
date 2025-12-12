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
        print(f"heading={bhi3_s.heading}, pitch={bhi3_s.pitch}, roll={bhi3_s.roll}, pressure={bhi3_s.pressure}, temperature={bhi3_s.temperature}, humidity={bhi3_s.humidity}")
        print(f"acc={bhi3_s.acc}")
        print()
        time.sleep(1)
    except KeyboardInterrupt:
        print()
        break
