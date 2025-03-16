#include "i2c_bmp5.h"


#ifdef USE_BMP5
static struct bmp5_dev dev;
static struct bmp5_osr_odr_press_config osr_odr_press_cfg = { 0 };
static struct bmp5_iir_config set_iir_cfg;
static struct bmp5_sensor_data sensor_data = { 0 };
static int fd;

void i2c_bmp5_read_data(float* value) {
    int8_t rslt;

    rslt = bmp5_get_sensor_data(&sensor_data, &osr_odr_press_cfg, &dev);
    if (rslt == BMP5_OK) {
        value[0] = sensor_data.pressure/100;
        value[1] = sensor_data.temperature;
    }
};

int8_t i2c_bmp5_init() {
    int8_t rslt;

    fd = i2c_open(I2C_DEVICE, BMP5_I2C_ADDR);

    dev.intf_ptr = &fd;
    dev.read = i2c_read;
    dev.write = i2c_write;
    dev.delay_us = delay_us;
    dev.intf = BMP5_I2C_INTF;

    //rslt = bmp5_soft_reset(&dev);
    //printf("bmp5_soft_reset [%d]\n", rslt);

    rslt = bmp5_init(&dev);
    if (rslt != BMP5_OK) {
        printf("bmp5 initialization failed\n");
        i2c_close(fd);
        return rslt;
    }

    rslt = bmp5_set_power_mode(BMP5_POWERMODE_STANDBY, &dev);
    //printf("bmp5_set_power_mode [%d]\n", rslt);

    rslt = bmp5_get_osr_odr_press_config(&osr_odr_press_cfg, &dev);
    //printf("bmp5_set_performance [%d]\n", rslt);

    osr_odr_press_cfg.odr = BMP5_ODR_50_HZ;
    osr_odr_press_cfg.press_en = BMP5_ENABLE;
    osr_odr_press_cfg.osr_t = BMP5_OVERSAMPLING_64X;
    osr_odr_press_cfg.osr_p = BMP5_OVERSAMPLING_4X;

    rslt = bmp5_set_osr_odr_press_config(&osr_odr_press_cfg, &dev);
    //printf("bmp5_set_osr_odr_press_config [%d]\n", rslt);

    set_iir_cfg.set_iir_t = BMP5_IIR_FILTER_COEFF_1;
    set_iir_cfg.set_iir_p = BMP5_IIR_FILTER_COEFF_1;
    set_iir_cfg.shdw_set_iir_t = BMP5_ENABLE;
    set_iir_cfg.shdw_set_iir_p = BMP5_ENABLE;

    rslt = bmp5_set_iir_config(&set_iir_cfg, &dev);
    //printf("bmp5_set_iir_config [%d]\n", rslt);

    rslt = bmp5_set_power_mode(BMP5_POWERMODE_NORMAL, &dev);
    //printf("bmp5_set_power_mode [%d]\n", rslt);

    return rslt;
};

void i2c_bmp5_close() {
    i2c_close(fd);
};

#ifndef NOUSE_MAIN
int main() {
    float value[2];
    int8_t rslt;
    rslt = i2c_bmp5_init();
    if (rslt != BMP5_OK) {
        return rslt;
    }
    
    while(1) {
        i2c_bmp5_read_data(&value[0]);
        printf("%.3f, %.3f\n", value[0], value[1]);
        sleep(1);
    }

    i2c_bmp5_close();
    return 0;
};
#endif

#else

#ifndef NOUSE_MAIN
int main() {};
#endif

#endif

