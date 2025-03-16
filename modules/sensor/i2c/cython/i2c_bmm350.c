#include "i2c_bmm350.h"


#ifdef USE_BMM350
static struct bmm350_dev dev;
static struct bmm350_mag_temp_data mag_temp_data = { 0 };
static struct bmm350_pmu_cmd_status_0 pmu_cmd_stat_0 = { 0 };
static int fd;

void i2c_bmm350_read_mag(float* mag) {
    int8_t rslt;

    rslt = bmm350_get_compensated_mag_xyz_temp_data(&mag_temp_data, &dev);
    if (rslt == BMM350_OK) {
        mag[0] = mag_temp_data.x;
        mag[1] = mag_temp_data.y;
        mag[2] = mag_temp_data.z;
    }
};

int8_t i2c_bmm350_init() {
    int8_t rslt;
    uint8_t err_reg_data = 0;

    fd = i2c_open(I2C_DEVICE, BMM350_I2C_ADDR);

    dev.intf_ptr = &fd;
    dev.read = i2c_read;
    dev.write = i2c_write;
    dev.delay_us = delay_us;

    rslt = bmm350_init(&dev);
    if (rslt != BMM350_OK) {
        printf("BMM350 initialization failed\n");
        i2c_close(fd);
        return rslt;
    }

    rslt = bmm350_get_pmu_cmd_status_0(&pmu_cmd_stat_0, &dev);
    //printf("bmm350_get_pmu_cmd_status_0 [%d]\n", rslt);
    //printf("  Expected : 0x07 : PMU cmd busy : 0x0\n");
    //printf("  Read : 0x07 : PMU cmd busy : 0x%X\n", pmu_cmd_stat_0.pmu_cmd_busy);

    rslt = bmm350_get_regs(BMM350_REG_ERR_REG, &err_reg_data, 1, &dev);
    //printf("bmm350_get_error_reg_data [%d]\n", rslt);
    //printf("  Expected : 0x02 : Error Register : 0x0\n");
    ///printf("  Read : 0x02 : Error Register : 0x%X\n", err_reg_data);

    /* Set ODR and performance */
    rslt = bmm350_set_odr_performance(BMM350_DATA_RATE_25HZ, BMM350_AVERAGING_8, &dev);
    //printf("bmm350_set_odr_performance [%d]\n", rslt);

    /* Enable all axis */
    rslt = bmm350_enable_axes(BMM350_X_EN, BMM350_Y_EN, BMM350_Z_EN, &dev);
    //printf("bmm350_enable_axes [%d]\n", rslt);

    rslt = bmm350_set_powermode(BMM350_NORMAL_MODE, &dev);
    //printf("bmm350_set_powermode [%d]\n", rslt); 

    return rslt;
};

void i2c_bmm350_close() {
    i2c_close(fd);
};

#ifndef NOUSE_MAIN
int main() {
    float mag[3];
    int8_t rslt;
    rslt = i2c_bmm350_init();
    if (rslt != BMM350_OK) {
        return rslt;
    }
    
    while(1) {
        i2c_bmm350_read_mag(&mag[0]);
        printf("%.3f, %.3f, %.3f\n", mag[0], mag[1], mag[2]);
        sleep(1);
    }

    i2c_bmm350_close();
    return 0;
};
#endif

#else

#ifndef NOUSE_MAIN
int main() {};
#endif

#endif

