import time
import struct

try:
    # run from top directory (pizero_bikecomputer)
    from . import i2c
except:
    # directly run this program
    import i2c


# for MS5637
# https://www.te.com/commerce/DocumentDelivery/DDEController?Action=showdoc&DocId=Data+Sheet%7FMS5637-02BA03%7FB4%7Fpdf%7FEnglish%7FENG_DS_MS5637-02BA03_B4.pdf%7FCAT-BLPS0037

# temperature resolution
OSRS_T = 0  # no oversampling
# OSRS_T = 1 # x2 oversampling
# OSRS_T = 2 # x4 oversampling
# OSRS_T = 3 # x8 oversampling
# OSRS_T = 4 # x16 oversampling
# OSRS_T = 5 # x32 oversampling

# pressure resolution
# OSRS_P = 0 # no oversampling
OSRS_P = 1  # x2 oversampling
# OSRS_P = 2 # x4 oversampling
# OSRS_P = 3 # x8 oversampling
# OSRS_P = 4 # x16 oversampling
# OSRS_P = 5 # x32 oversampling


class MS5637(i2c.i2c):
    # address
    SENSOR_ADDRESS = 0x76

    # for reset
    RESET_ADDRESS = 0x1E
    RESET_VALUE = 0x00  # ???

    # for reading value
    VALUE_ADDRESS = 0x00
    VALUE_BYTES = 3

    # for test
    TEST_ADDRESS = 0xA0  # PROM Address #0
    TEST_VALUE = (0xA7,)  # Factory defined value at data[0]

    elements = ("temperature", "pressure")
    temperature = None
    pressure = None

    def init_sensor(self):
        # Read calibration data from PROM
        # Pressure sensitivity
        data = self.bus.read_i2c_block_data(self.SENSOR_ADDRESS, 0xA2, 2)
        self.C1 = data[0] * 256 + data[1]
        time.sleep(0.01)

        # Pressure offset
        data = self.bus.read_i2c_block_data(self.SENSOR_ADDRESS, 0xA4, 2)
        self.C2 = data[0] * 256 + data[1]
        time.sleep(0.01)

        # Temperature coefficient of pressure sensitivity
        data = self.bus.read_i2c_block_data(self.SENSOR_ADDRESS, 0xA6, 2)
        self.C3 = data[0] * 256 + data[1]
        time.sleep(0.01)

        # Temperature coefficient of pressure offset
        data = self.bus.read_i2c_block_data(self.SENSOR_ADDRESS, 0xA8, 2)
        self.C4 = data[0] * 256 + data[1]
        time.sleep(0.01)

        # Reference temperature
        data = self.bus.read_i2c_block_data(self.SENSOR_ADDRESS, 0xAA, 2)
        self.C5 = data[0] * 256 + data[1]
        time.sleep(0.01)

        # Temperature coefficient of the temperature
        data = self.bus.read_i2c_block_data(self.SENSOR_ADDRESS, 0xAC, 2)
        self.C6 = data[0] * 256 + data[1]
        time.sleep(0.01)

    def read(self):
        # Read digital pressure and temperature data
        # get D1
        self.bus.write_byte(self.SENSOR_ADDRESS, 0x40 + 2 * OSRS_T)
        time.sleep(0.1)
        value = self.bus.read_i2c_block_data(
            self.SENSOR_ADDRESS, self.VALUE_ADDRESS, self.VALUE_BYTES
        )
        D1 = value[0] * 65536 + value[1] * 256 + value[2]
        # get D2
        self.bus.write_byte(self.SENSOR_ADDRESS, 0x50 + 2 * OSRS_P)
        time.sleep(0.1)
        value = self.bus.read_i2c_block_data(
            self.SENSOR_ADDRESS, self.VALUE_ADDRESS, self.VALUE_BYTES
        )
        D2 = value[0] * 65536 + value[1] * 256 + value[2]

        # Calculate temperature
        dT = D2 - self.C5 * 256
        TEMP = 2000 + dT * self.C6 / 8388608

        # Calculate temperature compensated pressure
        OFF = self.C2 * 131072 + (self.C4 * dT) / 64
        SENS = self.C1 * 65536 + (self.C3 * dT) / 128

        T2 = 0
        OFF2 = 0
        SENS2 = 0

        if TEMP >= 2000:
            T2 = 5 * dT * dT / 274877906944
            OFF2 = 0
            SENS2 = 0
        else:
            T2 = 3 * (dT * dT) / 8589934592
            OFF2 = 61 * ((TEMP - 2000) * (TEMP - 2000)) / 16
            SENS2 = 29 * ((TEMP - 2000) * (TEMP - 2000)) / 16
            if TEMP < -1500:
                OFF2 = OFF2 + 17 * ((TEMP + 1500) * (TEMP + 1500))
                SENS2 = SENS2 + 9 * ((TEMP + 1500) * (TEMP + 1500))

        TEMP = TEMP - T2
        OFF = OFF - OFF2
        SENS = SENS - SENS2

        pressure = ((((D1 * SENS) / 2097152) - OFF) / 32768.0) / 100.0
        temperature = TEMP / 100.0

        # Output data to screen
        self.values["pressure"] = pressure
        self.values["temperature"] = temperature
        self.pressure = self.values["pressure"]
        self.temperature = self.values["temperature"]


if __name__ == "__main__":
    s = MS5637()
    while True:
        time.sleep(1)
        s.read()
        print(s.values["temperature"], s.values["pressure"])
