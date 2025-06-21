#ifndef __I2C_BMP3
#define __I2C_BMP3

#ifdef __cplusplus
extern "C" {
#endif

#include <stdio.h>
#include <stdint.h>

#ifdef USE_BMP3

#include "common.h"

#include "bmp3.h"

#define I2C_DEVICE "/dev/i2c-1"
//#define I2C_BUS 1
#define BMP3_I2C_ADDR 0x77

int8_t i2c_bmp3_init();
void i2c_bmp3_read_data(float* value);
void i2c_bmp3_close();

#else
int8_t i2c_bmp3_init() {
    //printf("no sensor bmp5\n");
    return -1;
}
void i2c_bmp3_read_data(float* value) {};
void i2c_bmp3_close() {};

#endif

#ifdef __cplusplus
}
#endif

#endif
