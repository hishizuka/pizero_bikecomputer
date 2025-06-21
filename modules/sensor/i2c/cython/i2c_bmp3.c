#include "i2c_bmp3.h"

#ifdef USE_BMP3
static struct bmp3_dev dev;
static struct bmp3_settings settings = { 0 };
static struct bmp3_data data = { 0 };
static int fd;

void i2c_bmp3_read_data(float* value) {
    int8_t rslt;

    rslt = bmp3_get_sensor_data(BMP3_PRESS_TEMP, &data, &dev);
    if (rslt == BMP3_OK) {
        value[0] = data.pressure/100;
        value[1] = data.temperature;
    }
};

int8_t i2c_bmp3_init() {
    int8_t rslt;
    uint16_t settings_sel;

    fd = i2c_open(I2C_DEVICE, BMP3_I2C_ADDR);

    dev.read = i2c_read;
    dev.write = i2c_write;
    dev.intf = BMP3_I2C_INTF;
    dev.intf_ptr = &fd;
    dev.delay_us = delay_us;

    rslt = bmp3_init(&dev);
    if (rslt != BMP3_OK) {
        printf("bmp3 initialization failed\n");
        i2c_close(fd);
        return rslt;
    }

    settings.press_en = BMP3_ENABLE;
    settings.temp_en = BMP3_ENABLE;
    settings.odr_filter.press_os = BMP3_OVERSAMPLING_2X;
    settings.odr_filter.temp_os = BMP3_OVERSAMPLING_2X;
    settings.odr_filter.odr = BMP3_ODR_100_HZ;
    settings_sel = BMP3_SEL_PRESS_EN | BMP3_SEL_TEMP_EN | BMP3_SEL_PRESS_OS | BMP3_SEL_TEMP_OS | BMP3_SEL_ODR;

    rslt = bmp3_set_sensor_settings(settings_sel, &settings, &dev);
    printf("bmp3_set_sensor_settings [%d]\n", rslt);
    
    settings.op_mode = BMP3_MODE_NORMAL;
    rslt = bmp3_set_op_mode(&settings, &dev);
    printf("bmp3_set_op_mode [%d]\n", rslt);

    return rslt;
};

void i2c_bmp3_close() {
    i2c_close(fd);
};

#ifndef NOUSE_MAIN
int main() {
    float value[2];
    int8_t rslt;
    rslt = i2c_bmp3_init();
    if (rslt != BMP3_OK) {
        return rslt;
    }
    
    while(1) {
        i2c_bmp3_read_data(&value[0]);
        printf("%.3f, %.3f\n", value[0], value[1]);
        sleep(1);
    }

    i2c_bmp3_close();
    return 0;
};
#endif

#else

#ifndef NOUSE_MAIN
int main() {};
#endif

#endif

