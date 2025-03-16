#include "i2c_bmm150.h"


#ifdef USE_BMM150
static struct bmm150_dev dev;
static struct bmm150_settings settings;
static struct bmm150_mag_data mag_data = { 0 };
static int fd;

void i2c_bmm150_read_mag(float* mag) {
    int8_t rslt;

    rslt = bmm150_read_mag_data(&mag_data, &dev);
    if (rslt == BMM150_OK) {
        mag[0] = mag_data.x;
        mag[1] = mag_data.y;
        mag[2] = mag_data.z;
    }
};

int8_t i2c_bmm150_init() {
    int8_t rslt;

    fd = i2c_open(I2C_DEVICE, BMM150_I2C_ADDR);

    dev.intf_ptr = &fd;
    dev.read = i2c_read;
    dev.write = i2c_write;
    dev.delay_us = delay_us;
    dev.intf = BMM150_I2C_INTF;

    rslt = bmm150_init(&dev);
    if (rslt != BMM150_OK) {
        printf("BMM150 initialization failed\n");
        i2c_close(fd);
        return rslt;
    }

    settings.pwr_mode = BMM150_POWERMODE_NORMAL;
    rslt = bmm150_set_op_mode(&settings, &dev);
    //printf("bmm150_set_op_mode [%d]\n", rslt);

    settings.preset_mode = BMM150_PRESETMODE_LOWPOWER;
    rslt = bmm150_set_presetmode(&settings, &dev);
    //printf("bmm150_set_performance [%d]\n", rslt);

    return rslt;
};

void i2c_bmm150_close() {
    i2c_close(fd);
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

