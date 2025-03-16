#ifndef __I2C_BMM350
#define __I2C_BMM350

#ifdef __cplusplus
extern "C" {
#endif

#include <stdio.h>
#include <stdint.h>

#ifdef USE_BMM350

#include "i2c_common.h"

#include "bmm350.h"

#define I2C_DEVICE "/dev/i2c-1"
#define I2C_BUS 1
#define BMM350_I2C_ADDR 0x14

int8_t i2c_bmm350_init();
void i2c_bmm350_read_mag(float* mag);
void i2c_bmm350_close();

#else

int8_t i2c_bmm350_init() {
    //printf("no sensor bmm350\n");
    return -1;
}
void i2c_bmm350_read_mag(float* mag) {};
void i2c_bmm350_close() {};

#endif

#ifdef __cplusplus
}
#endif

#endif
