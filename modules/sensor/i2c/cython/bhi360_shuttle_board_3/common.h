/**
* Copyright (c) 2025 Bosch Sensortec GmbH. All rights reserved.
*
* BSD-3-Clause
*
* Redistribution and use in source and binary forms, with or without
* modification, are permitted provided that the following conditions are met:
*
* 1. Redistributions of source code must retain the above copyright
*    notice, this list of conditions and the following disclaimer.
*
* 2. Redistributions in binary form must reproduce the above copyright
*    notice, this list of conditions and the following disclaimer in the
*    documentation and/or other materials provided with the distribution.
*
* 3. Neither the name of the copyright holder nor the names of its
*    contributors may be used to endorse or promote products derived from
*    this software without specific prior written permission.
*
* THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
* "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
* LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
* FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
* COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
* INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
* (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
* SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
* HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT,
* STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING
* IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
* POSSIBILITY OF SUCH DAMAGE.
*
* @file    common.h
* @brief   Common header file for the BHI360 examples
*
*/

#ifndef _COMMON_H_
#define _COMMON_H_

#ifdef __cplusplus
extern "C" {
#endif

#include <stdbool.h>

#include <stdio.h>
#include <unistd.h>
#include <stdint.h>
#include <string.h>
#include <fcntl.h>
#include <sys/ioctl.h>
//#include <linux/spi/spidev.h>
#include <linux/i2c-dev.h>
#include <pigpiod_if2.h>
//#include <gpiod.h>

#include "bhy.h"
#include "bhi3_defs.h"
#include "bhy_activity_param.h"
#include "bhy_bsec_param.h"
#include "bhy_bsx_algo_param.h"
#include "bhy_head_orientation_param.h"
#include "bhy_multi_tap_param.h"
#include "bhy_phy_sensor_ctrl_param.h"
#include "bhy_system_param.h"
#include "bhy_virtual_sensor_conf_param.h"
#include "bhy_virtual_sensor_info_param.h"

#include "intf_codes.h"

#define BHY_RD_WR_LEN           256   /* MCU maximum read write length */

#define SPI_CHANNEL 1
#define SPI_DEVICE "/dev/spidev0.1"
#define I2C_DEVICE "/dev/i2c-1"
//#define I2C_BUS 1
#define BHI360_I2C_ADDR 0x28

void cb(int pi, unsigned gpio, unsigned level, uint32_t tick);
char *get_intf_error(int16_t rslt);
char *get_api_error(int8_t error_code);
char *get_sensor_error_text(uint8_t sensor_error);
char *get_sensor_name(uint8_t sensor_id);
char *get_physical_sensor_name(uint8_t sensor_id);
uint8_t get_physical_sensor_id(uint8_t virt_sensor_id);
float get_sensor_dynamic_range_scaling(uint8_t sensor_id, float dynamic_range);
char *get_sensor_si_unit(uint8_t sensor_id);
char *get_sensor_parse_format(uint8_t sensor_id);
char *get_sensor_axis_names(uint8_t sensor_id);

void setup_interfaces(bool reset_power, enum bhy_intf intf);
void close_interfaces(enum bhy_intf intf);
int8_t bhy_spi_read(uint8_t reg_addr, uint8_t *reg_data, uint32_t length, void *intf_ptr);
int8_t bhy_spi_write(uint8_t reg_addr, const uint8_t *reg_data, uint32_t length, void *intf_ptr);
int8_t bhy_i2c_read(uint8_t reg_addr, uint8_t *reg_data, uint32_t length, void *intf_ptr);
int8_t bhy_i2c_write(uint8_t reg_addr, const uint8_t *reg_data, uint32_t length, void *intf_ptr);
void bhy_delay_us(uint32_t us, void *private_data);
bool get_interrupt_status(void);

#ifdef __cplusplus
}
#endif

#endif /* _COMMON_H_ */
