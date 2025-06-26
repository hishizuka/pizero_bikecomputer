#ifndef __I2C_BMP5
#define __I2C_BMP5

#ifdef __cplusplus
extern "C" {
#endif

#include <stdio.h>
#include <stdint.h>

#ifdef USE_BMP5

#include "common.h"

#include "bmp5.h"

#define I2C_DEVICE "/dev/i2c-1"
#define I2C_BUS 1
#define BMP5_I2C_ADDR 0x47

int8_t i2c_bmp5_init();
void i2c_bmp5_read_data(float* value);
void i2c_bmp5_close();

#else
int8_t i2c_bmp5_init() {
    //printf("no sensor bmp5\n");
    return -1;
}
void i2c_bmp5_read_data(float* value) {};
void i2c_bmp5_close() {};

#endif

#ifdef __cplusplus
}
#endif

#endif
