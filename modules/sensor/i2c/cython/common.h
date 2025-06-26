#ifndef __COMMON
#define __COMMON

#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <stdint.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <linux/i2c-dev.h>

#ifdef __cplusplus
extern "C" {
#endif

int8_t i2c_open(const char *device, uint8_t addr);
void i2c_close(int fd);
int8_t i2c_read(uint8_t reg_addr, uint8_t *data, uint32_t len, void *intf_ptr);
int8_t i2c_write(uint8_t reg_addr, const uint8_t *data, uint32_t len, void *intf_ptr);
void delay_us(uint32_t period, void *intf_ptr);

#ifdef __cplusplus
}
#endif

#endif