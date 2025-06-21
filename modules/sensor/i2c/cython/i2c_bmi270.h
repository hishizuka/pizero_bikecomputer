#ifndef __I2C_BMI270
#define __I2C_BMI270

#ifdef __cplusplus
extern "C" {
#endif

#include <stdio.h>
#include <stdint.h>

#ifdef USE_BMI270
#include <math.h>

#include "common.h"

#include "bmi270.h"

#define I2C_DEVICE "/dev/i2c-1"
//#define I2C_BUS 1
#define BMI270_I2C_ADDR 0x68

int8_t i2c_bmi270_init();
void i2c_bmi270_read_data(float* acc, float* gyro);
void i2c_bmi270_close();

#else
int8_t i2c_bmi270_init() {
    //printf("no sensor bmi270\n");
    return -1;
}
void i2c_bmi270_read_data(float* acc, float* gyro) {};
void i2c_bmi270_close() {};

#endif

#ifdef __cplusplus
}
#endif

#endif
