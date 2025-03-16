#include "i2c_bmi270.h"


#ifdef USE_BMI270
static struct bmi2_dev dev;
static struct bmi2_sens_config config[2];
static uint8_t sensor_list[2] = { BMI2_ACCEL, BMI2_GYRO };
static struct bmi2_sens_data sensor_data = { { 0 } };
static int fd;
static float lsb_to_mps_factor = 0.0f;
static float lsb_to_dps_factor = 0.0f;
static float lsb_to_rps_factor = 0.0f;

#define ACCEL          UINT8_C(0x00)
#define GYRO           UINT8_C(0x01)

void i2c_bmi270_read_data(float* acc, float* gyro) {
    int8_t rslt;

    rslt = bmi2_get_sensor_data(&sensor_data, &dev);
    if (rslt == BMI2_OK) {
        acc[0] = lsb_to_mps_factor * sensor_data.acc.x;
        acc[1] = lsb_to_mps_factor * sensor_data.acc.y;
        acc[2] = lsb_to_mps_factor * sensor_data.acc.z;
        // Gyro data in degree per second
        //gyro[0] = lsb_to_dps_factor * sensor_data.gyr.x;
        //gyro[1] = lsb_to_dps_factor * sensor_data.gyr.y;
        //gyro[2] = lsb_to_dps_factor * sensor_data.gyr.z;
        // Gyro data in radian per second
        gyro[0] = lsb_to_rps_factor * sensor_data.gyr.x;
        gyro[1] = lsb_to_rps_factor * sensor_data.gyr.y;
        gyro[2] = lsb_to_rps_factor * sensor_data.gyr.z;
    }
};

int8_t i2c_bmi270_init() {
    int8_t rslt;

    fd = i2c_open(I2C_DEVICE, BMI270_I2C_ADDR);

    dev.intf_ptr = &fd;
    dev.intf = BMI2_I2C_INTF;
    dev.read = i2c_read;
    dev.write = i2c_write;
    dev.delay_us = delay_us;

    rslt = bmi270_init(&dev);
    if (rslt != BMI2_OK) {
        printf("BMI270 initialization failed\n");
        i2c_close(fd);
        return rslt;
    }

    config[ACCEL].type = BMI2_ACCEL;
    config[GYRO].type = BMI2_GYRO;

    rslt = bmi2_get_sensor_config(config, 2, &dev);
    //printf("bmi2_get_sensor_config [%d]\n", rslt);

    config[ACCEL].cfg.acc.odr = BMI2_ACC_ODR_200HZ;
    config[ACCEL].cfg.acc.range = BMI2_ACC_RANGE_2G;
    config[ACCEL].cfg.acc.bwp = BMI2_ACC_NORMAL_AVG4;
    config[ACCEL].cfg.acc.filter_perf = BMI2_PERF_OPT_MODE;

    config[GYRO].cfg.gyr.odr = BMI2_GYR_ODR_200HZ;
    config[GYRO].cfg.gyr.range = BMI2_GYR_RANGE_2000;
    config[GYRO].cfg.gyr.bwp = BMI2_GYR_NORMAL_MODE;
    config[GYRO].cfg.gyr.noise_perf = BMI2_POWER_OPT_MODE;
    config[GYRO].cfg.gyr.filter_perf = BMI2_PERF_OPT_MODE;

    lsb_to_mps_factor = (float)(2 << config[ACCEL].cfg.acc.range) / ((float)((pow((double)2.0f, (double)dev.resolution) / 2.0f)));
    // degree per second
    lsb_to_dps_factor = (float)(125.0f * (1 << (BMI2_GYR_RANGE_125 - config[GYRO].cfg.gyr.range))) / ((float)((pow((double)2.0f, (double)dev.resolution) / 2.0f)));
    // radian per second
    lsb_to_rps_factor = lsb_to_dps_factor * (M_PI / 180.0f);

    rslt = bmi2_set_sensor_config(config, 2, &dev);
    //printf("bmi2_set_sensor_config [%d]\n", rslt);

    rslt = bmi2_sensor_enable(sensor_list, 2, &dev);
    //printf("bmi2_sensor_enable [%d]\n", rslt);

    return rslt;
};

void i2c_bmi270_close() {
    i2c_close(fd);
};

#ifndef NOUSE_MAIN
int main() {
    float acc[3];
    float gyro[3];
    int8_t rslt;
    rslt = i2c_bmi270_init();
    if (rslt != BMI2_OK) {
        return rslt;
    }
    
    while(1) {
        i2c_bmi270_read_data(&acc[0], &gyro[0]);
        printf("%.3f, %.3f, %.3f / %.3f, %.3f, %.3f\n", acc[0], acc[1], acc[2], gyro[0], gyro[1], gyro[2]);
        sleep(1);
    }

    i2c_bmi270_close();
    return 0;
};
#endif

#else

#ifndef NOUSE_MAIN
int main() {};
#endif

#endif

