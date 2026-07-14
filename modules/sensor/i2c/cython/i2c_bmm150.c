#include "i2c_bmm150.h"


#ifdef USE_BMM150
static struct bmm150_dev dev;
static struct bmm150_settings settings;
static struct bmm150_mag_data mag_data = { 0 };
static int fd = -1;

void i2c_bmm150_read_mag(float* mag) {
    int8_t rslt;

    rslt = bmm150_read_mag_data(&mag_data, &dev);
    if (rslt == BMM150_OK) {
        mag[0] = mag_data.x;
        mag[1] = mag_data.y;
        mag[2] = mag_data.z;
    }
};

static int8_t i2c_bmm150_init_at(uint8_t addr) {
    int8_t rslt;

    fd = i2c_open(I2C_DEVICE, addr);
    if (fd < 0) {
        return -1;
    }

    dev.intf_ptr = &fd;
    dev.read = i2c_read;
    dev.write = i2c_write;
    dev.delay_us = delay_us;
    dev.intf = BMM150_I2C_INTF;

    rslt = bmm150_init(&dev);
    if (rslt != BMM150_OK) {
        i2c_bmm150_close();
        return rslt;
    }

    settings.pwr_mode = BMM150_POWERMODE_NORMAL;
    rslt = bmm150_set_op_mode(&settings, &dev);
    //printf("bmm150_set_op_mode [%d]\n", rslt);
    if (rslt != BMM150_OK) {
        i2c_bmm150_close();
        return rslt;
    }

    settings.preset_mode = BMM150_PRESETMODE_LOWPOWER;
    rslt = bmm150_set_presetmode(&settings, &dev);
    //printf("bmm150_set_performance [%d]\n", rslt);
    if (rslt != BMM150_OK) {
        i2c_bmm150_close();
        return rslt;
    }

    if (rslt == BMM150_OK) {
        float warmup_mag[3];

        dev.delay_us(100000, dev.intf_ptr);
        i2c_bmm150_read_mag(&warmup_mag[0]);
    }

    return rslt;
};

int8_t i2c_bmm150_init() {
    int8_t rslt;
    uint8_t addrs[] = {
        BMM150_I2C_ADDR_PRIMARY,
        BMM150_I2C_ADDR_SECONDARY_1,
        BMM150_I2C_ADDR_SECONDARY_2,
        BMM150_I2C_ADDR_SECONDARY_3,
    };
    size_t i;

    for (i = 0; i < sizeof(addrs) / sizeof(addrs[0]); i++) {
        rslt = i2c_bmm150_init_at(addrs[i]);
        if (rslt == BMM150_OK) {
            return rslt;
        }
    }

    printf("BMM150 initialization failed [%d]\n", rslt);
    return rslt;
};

void i2c_bmm150_close() {
    if (fd >= 0) {
        i2c_close(fd);
        fd = -1;
    }
};

#ifndef NOUSE_MAIN
int main() {
    float mag[3];
    int8_t rslt;
    rslt = i2c_bmm150_init();
    if (rslt != BMM150_OK) {
        return rslt;
    }
    
    while(1) {
        i2c_bmm150_read_mag(&mag[0]);
        printf("%.3f, %.3f, %.3f\n", mag[0], mag[1], mag[2]);
        sleep(1);
    }

    i2c_bmm150_close();
    return 0;
};
#endif

#else

#ifndef NOUSE_MAIN
int main() {};
#endif

#endif
