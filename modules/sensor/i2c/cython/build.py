import time

import pyximport
pyximport.install(inplace=True)
from i2c_helper import BMM150_C, BMI270_C, BMM350_C, BMP5_C

bmm150 = BMM150_C(1)
bmm350 = BMM350_C(1)
bmi270 = BMI270_C(1)
bmp5   = BMP5_C(1)

print(f"{bmm150.status=}, {bmm350.status=}, {bmi270.status=}, {bmp5.status=}")

while True:
    try:
        print(f"BMM150 mag: {bmm150.magnetic}")
        print(f"BMM350 mag: {bmm350.magnetic}")
        print(f"BMI270 acc: {bmi270.acceleration}")
        print(f"BMI270 gyr: {bmi270.gyro}")
        print(f"BMP5      : {bmp5.pressure}, {bmp5.temperature}")
        print()
        time.sleep(1)
    except KeyboardInterrupt:
        print()
        break
