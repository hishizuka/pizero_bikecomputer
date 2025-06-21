#ifndef __I2C_BMM150
#define __I2C_BMM150

#ifdef __cplusplus
extern "C" {
#endif

#include <stdio.h>
#include <stdint.h>

#ifdef USE_BMM150

#include "common.h"

#include "bmm150.h"

#define I2C_DEVICE "/dev/i2c-1"
//#define I2C_BUS 1
#define BMM150_I2C_ADDR 0x13

int8_t i2c_bmm150_init();
void i2c_bmm150_read_mag(float* mag);
void i2c_bmm150_close();

#else
int8_t i2c_bmm150_init() {
    //printf("no sensor bmi150\n");
    return -1;
}
void i2c_bmm150_read_mag(float* mag) {};
void i2c_bmm150_close() {};

#endif

#ifdef __cplusplus
}
#endif

#endif
