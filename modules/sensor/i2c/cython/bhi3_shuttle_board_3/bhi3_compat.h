/**
 * @file bhi3_compat.h
 * @brief Compatibility header that maps BHI360 SDK symbols to BHI385 SDK when
 *        USE_BHI385 is defined.  With USE_BHI385 undefined the original BHI360
 *        headers are included as-is, so existing BHI360 code is unaffected.
 *
 * Usage:
 *   Build with -DUSE_BHI385 to target BHI385.
 *   Build without the macro (default) to target BHI360.
 */

#ifndef __BHI3_COMPAT_H__
#define __BHI3_COMPAT_H__

#ifdef USE_BHI385

/* ------------------------------------------------------------------ */
/* BHI385 SDK headers                                                  */
/* ------------------------------------------------------------------ */
#include "bhi385.h"
#include "bhi385_defs.h"
#include "bhi385_parse.h"
#include "bhi385_event_data.h"
#include "bhi385_virtual_sensor_conf_param.h"
#include "bhi385_virtual_sensor_info_param.h"
#include "bhi385_bsx_algo_param.h"
#include "bhi385_activity_param.h"
#include "bhi385_multi_tap_param.h"
#include "bhi385_phy_sensor_ctrl_param.h"
#include "bhi385_system_param.h"
/* BHI385-only: klio (no BHI360 equivalent) */
#include "bhi385_klio_param.h"

/* ------------------------------------------------------------------ */
/* Type aliases                                                        */
/* ------------------------------------------------------------------ */
#define bhi360_dev                               bhi385_dev
#define bhi360_intf                              bhi385_intf
#define bhi360_fifo_parse_data_info              bhi385_fifo_parse_data_info
#define bhi360_fifo_parse_callback_t             bhi385_fifo_parse_callback_t
#define bhi360_virtual_sensor_conf_param_conf    bhi385_virtual_sensor_conf_param_conf
#define bhi360_event_data_xyz                    bhi385_event_data_xyz
#define bhi360_event_data_orientation            bhi385_event_data_orientation
#define bhi360_bsx_algo_param_state_exg          bhi385_bsx_algo_param_state_exg
#define bhi360_float                             bhi385_float

/* ------------------------------------------------------------------ */
/* Core API functions                                                  */
/* ------------------------------------------------------------------ */
#define bhi360_init                              bhi385_init
#define bhi360_soft_reset                        bhi385_soft_reset
#define bhi360_get_chip_id                       bhi385_get_chip_id
#define bhi360_get_boot_status                   bhi385_get_boot_status
#define bhi360_get_kernel_version                bhi385_get_kernel_version
#define bhi360_get_error_value                   bhi385_get_error_value
#define bhi360_set_host_intf_ctrl                bhi385_set_host_intf_ctrl
#define bhi360_set_host_interrupt_ctrl           bhi385_set_host_interrupt_ctrl
#define bhi360_get_host_interrupt_ctrl           bhi385_get_host_interrupt_ctrl
#define bhi360_register_fifo_parse_callback      bhi385_register_fifo_parse_callback
#define bhi360_deregister_fifo_parse_callback    bhi385_deregister_fifo_parse_callback
#define bhi360_get_and_process_fifo              bhi385_get_and_process_fifo
#define bhi360_update_virtual_sensor_list        bhi385_update_virtual_sensor_list
#define bhi360_virtual_sensor_conf_param_set_cfg bhi385_virtual_sensor_conf_param_set_cfg
#define bhi360_virtual_sensor_conf_param_get_cfg bhi385_virtual_sensor_conf_param_get_cfg
#define bhi360_set_virt_sensor_range             bhi385_set_virt_sensor_range
#define bhi360_upload_firmware_to_ram            bhi385_upload_firmware_to_ram
#define bhi360_upload_firmware_to_ram_partly     bhi385_upload_firmware_to_ram_partly
#define bhi360_boot_from_ram                     bhi385_boot_from_ram
#define bhi360_get_regs                          bhi385_get_regs
#define bhi360_set_regs                          bhi385_set_regs
#define bhi360_get_parameter                     bhi385_get_parameter
#define bhi360_set_parameter                     bhi385_set_parameter
#define bhi360_flush_fifo                        bhi385_flush_fifo

/* Firmware blob symbol exposed by Bosch firmware header */
#define bhi360_firmware_image                    bhi385_firmware_image

/* BSX calibration */
#define bhi360_bsx_algo_param_get_bsx_states     bhi385_bsx_algo_param_get_bsx_states
#define bhi360_bsx_algo_param_set_bsx_states     bhi385_bsx_algo_param_set_bsx_states

/* Event data parsers */
#define bhi360_event_data_parse_xyz              bhi385_event_data_parse_xyz
#define bhi360_event_data_parse_orientation      bhi385_event_data_parse_orientation

/* I2C / SPI / delay callbacks (user-defined in common.c) */
#define bhi360_i2c_read                          bhi385_i2c_read
#define bhi360_i2c_write                         bhi385_i2c_write
#define bhi360_spi_read                          bhi385_spi_read
#define bhi360_spi_write                         bhi385_spi_write
#define bhi360_delay_us                          bhi385_delay_us

/* ------------------------------------------------------------------ */
/* Interface / config constants                                        */
/* ------------------------------------------------------------------ */
#define BHI360_I2C_INTERFACE                     BHI385_I2C_INTERFACE
#define BHI360_SPI_INTERFACE                     BHI385_SPI_INTERFACE
#define BHI360_INTF_RET_SUCCESS                  BHI385_INTF_RET_SUCCESS

/* Return codes */
#define BHI360_OK                                BHI385_OK
#define BHI360_E_NULL_PTR                        BHI385_E_NULL_PTR
#define BHI360_E_INVALID_PARAM                   BHI385_E_INVALID_PARAM
#define BHI360_E_IO                              BHI385_E_IO
#define BHI360_E_MAGIC                           BHI385_E_MAGIC
#define BHI360_E_TIMEOUT                         BHI385_E_TIMEOUT
#define BHI360_E_BUFFER                          BHI385_E_BUFFER
#define BHI360_E_INVALID_FIFO_TYPE               BHI385_E_INVALID_FIFO_TYPE
#define BHI360_E_INVALID_EVENT_SIZE              BHI385_E_INVALID_EVENT_SIZE
#define BHI360_E_PARAM_NOT_SET                   BHI385_E_PARAM_NOT_SET

/* Boot status */
#define BHI360_BST_HOST_INTERFACE_READY          BHI385_BST_HOST_INTERFACE_READY
#define BHI360_BST_HOST_FW_VERIFY_DONE           BHI385_BST_HOST_FW_VERIFY_DONE
#define BHI360_BST_HOST_FW_IDLE                  BHI385_BST_HOST_FW_IDLE

/* Interrupt control */
#define BHI360_ICTL_DISABLE_STATUS_FIFO          BHI385_ICTL_DISABLE_STATUS_FIFO
#define BHI360_ICTL_DISABLE_DEBUG                BHI385_ICTL_DISABLE_DEBUG
#define BHI360_ICTL_DISABLE_FAULT                BHI385_ICTL_DISABLE_FAULT
#define BHI360_ICTL_DISABLE_FIFO_W               BHI385_ICTL_DISABLE_FIFO_W
#define BHI360_ICTL_DISABLE_FIFO_NW              BHI385_ICTL_DISABLE_FIFO_NW
#define BHI360_ICTL_ACTIVE_LOW                   BHI385_ICTL_ACTIVE_LOW
#define BHI360_ICTL_EDGE                         BHI385_ICTL_EDGE
#define BHI360_ICTL_OPEN_DRAIN                   BHI385_ICTL_OPEN_DRAIN

/* Host interface control */
#define BHI360_HIF_CTRL_ASYNC_STATUS_CHANNEL     BHI385_HIF_CTRL_ASYNC_STATUS_CHANNEL

/* Chip identification */
#define BHI360_CHIP_ID                           BHI385_CHIP_ID

/* Sensor dynamic ranges */
#define BHI360_ACCEL_16G                         BHI385_ACCEL_16G
#define BHI360_ACCEL_8G                          BHI385_ACCEL_8G
#define BHI360_GYRO_2000DPS                      BHI385_GYRO_2000DPS

/* ------------------------------------------------------------------ */
/* Meta / system event IDs                                             */
/* ------------------------------------------------------------------ */
#define BHI360_SYS_ID_META_EVENT                 BHI385_SYS_ID_META_EVENT
#define BHI360_SYS_ID_META_EVENT_WU              BHI385_SYS_ID_META_EVENT_WU

#define BHI360_META_EVENT_FLUSH_COMPLETE         BHI385_META_EVENT_FLUSH_COMPLETE
#define BHI360_META_EVENT_SAMPLE_RATE_CHANGED    BHI385_META_EVENT_SAMPLE_RATE_CHANGED
#define BHI360_META_EVENT_POWER_MODE_CHANGED     BHI385_META_EVENT_POWER_MODE_CHANGED
#define BHI360_META_EVENT_SENSOR_ERROR           BHI385_META_EVENT_SENSOR_ERROR
#define BHI360_META_EVENT_FIFO_OVERFLOW          BHI385_META_EVENT_FIFO_OVERFLOW
#define BHI360_META_EVENT_DYNAMIC_RANGE_CHANGED  BHI385_META_EVENT_DYNAMIC_RANGE_CHANGED
#define BHI360_META_EVENT_FIFO_WATERMARK         BHI385_META_EVENT_FIFO_WATERMARK
#define BHI360_META_EVENT_INITIALIZED            BHI385_META_EVENT_INITIALIZED
#define BHI360_META_EVENT_SENSOR_STATUS          BHI385_META_EVENT_SENSOR_STATUS
#define BHI360_META_EVENT_RESET                  BHI385_META_EVENT_RESET

/* ------------------------------------------------------------------ */
/* Physical sensor IDs                                                 */
/* ------------------------------------------------------------------ */
#define BHI360_PHYS_SENSOR_ID_ACCELEROMETER      BHI385_PHYS_SENSOR_ID_ACCELEROMETER
#define BHI360_PHYS_SENSOR_ID_GYROSCOPE          BHI385_PHYS_SENSOR_ID_GYROSCOPE
#define BHI360_PHYS_SENSOR_ID_MAGNETOMETER       BHI385_PHYS_SENSOR_ID_MAGNETOMETER
#define BHI360_PHYS_SENSOR_ID_TEMPERATURE        BHI385_PHYS_SENSOR_ID_TEMPERATURE
#define BHI360_PHYS_SENSOR_ID_PRESSURE           BHI385_PHYS_SENSOR_ID_PRESSURE
#define BHI360_PHYS_SENSOR_ID_HUMIDITY           BHI385_PHYS_SENSOR_ID_HUMIDITY
#define BHI360_PHYS_SENSOR_ID_ANY_MOTION         BHI385_PHYS_SENSOR_ID_ANY_MOTION
#define BHI360_PHYS_SENSOR_ID_PHYS_ANY_MOTION    BHI385_PHYS_SENSOR_ID_PHYS_ANY_MOTION
#define BHI360_PHYS_SENSOR_ID_PHYS_NO_MOTION     BHI385_PHYS_SENSOR_ID_PHYS_NO_MOTION
#define BHI360_PHYS_SENSOR_ID_PHYS_SIGN_MOTION   BHI385_PHYS_SENSOR_ID_PHYS_SIGN_MOTION
#define BHI360_PHYS_SENSOR_ID_PHYS_STEP_COUNTER  BHI385_PHYS_SENSOR_ID_PHYS_STEP_COUNTER
#define BHI360_PHYS_SENSOR_ID_PHYS_STEP_DETECTOR BHI385_PHYS_SENSOR_ID_PHYS_STEP_DETECTOR
#define BHI360_PHYS_SENSOR_ID_LIGHT              BHI385_PHYS_SENSOR_ID_LIGHT
#define BHI360_PHYS_SENSOR_ID_PROXIMITY          BHI385_PHYS_SENSOR_ID_PROXIMITY
#define BHI360_PHYS_SENSOR_ID_GAS_RESISTOR       BHI385_PHYS_SENSOR_ID_GAS_RESISTOR
#define BHI360_PHYS_SENSOR_ID_TEMP_GYRO          BHI385_PHYS_SENSOR_ID_TEMP_GYRO
#define BHI360_PHYS_SENSOR_ID_POSITION           BHI385_PHYS_SENSOR_ID_POSITION
#define BHI360_PHYS_SENSOR_ID_GPS                BHI385_PHYS_SENSOR_ID_GPS
#define BHI360_PHYS_SENSOR_ID_ACT_REC            BHI385_PHYS_SENSOR_ID_ACT_REC
#define BHI360_PHYS_SENSOR_ID_EX_CAMERA_INPUT    BHI385_PHYS_SENSOR_ID_EX_CAMERA_INPUT
#define BHI360_PHYS_SENSOR_ID_NOT_SUPPORTED      BHI385_PHYS_SENSOR_ID_NOT_SUPPORTED
#define BHI360_PHYS_SENSOR_ID_WRIST_GESTURE_DETECT BHI385_PHYS_SENSOR_ID_WRIST_GESTURE_DETECT
#define BHI360_PHYS_SENSOR_ID_WRIST_WEAR_WAKEUP  BHI385_PHYS_SENSOR_ID_WRIST_WEAR_WAKEUP

/* ------------------------------------------------------------------ */
/* Virtual sensor IDs                                                  */
/* ------------------------------------------------------------------ */
#define BHI360_SENSOR_ID_ACC_PASS                BHI385_SENSOR_ID_ACC_PASS
#define BHI360_SENSOR_ID_ACC_RAW                 BHI385_SENSOR_ID_ACC_RAW
#define BHI360_SENSOR_ID_ACC                     BHI385_SENSOR_ID_ACC
#define BHI360_SENSOR_ID_ACC_BIAS                BHI385_SENSOR_ID_ACC_BIAS
#define BHI360_SENSOR_ID_ACC_WU                  BHI385_SENSOR_ID_ACC_WU
#define BHI360_SENSOR_ID_ACC_RAW_WU              BHI385_SENSOR_ID_ACC_RAW_WU
#define BHI360_SENSOR_ID_ACC_BIAS_WU             BHI385_SENSOR_ID_ACC_BIAS_WU
#define BHI360_SENSOR_ID_GYRO_PASS               BHI385_SENSOR_ID_GYRO_PASS
#define BHI360_SENSOR_ID_GYRO_RAW                BHI385_SENSOR_ID_GYRO_RAW
#define BHI360_SENSOR_ID_GYRO                    BHI385_SENSOR_ID_GYRO
#define BHI360_SENSOR_ID_GYRO_BIAS               BHI385_SENSOR_ID_GYRO_BIAS
#define BHI360_SENSOR_ID_GYRO_WU                 BHI385_SENSOR_ID_GYRO_WU
#define BHI360_SENSOR_ID_GYRO_RAW_WU             BHI385_SENSOR_ID_GYRO_RAW_WU
#define BHI360_SENSOR_ID_GYRO_BIAS_WU            BHI385_SENSOR_ID_GYRO_BIAS_WU
#define BHI360_SENSOR_ID_MAG_PASS                BHI385_SENSOR_ID_MAG_PASS
#define BHI360_SENSOR_ID_MAG_RAW                 BHI385_SENSOR_ID_MAG_RAW
#define BHI360_SENSOR_ID_MAG                     BHI385_SENSOR_ID_MAG
#define BHI360_SENSOR_ID_MAG_BIAS                BHI385_SENSOR_ID_MAG_BIAS
#define BHI360_SENSOR_ID_MAG_WU                  BHI385_SENSOR_ID_MAG_WU
#define BHI360_SENSOR_ID_MAG_RAW_WU              BHI385_SENSOR_ID_MAG_RAW_WU
#define BHI360_SENSOR_ID_MAG_BIAS_WU             BHI385_SENSOR_ID_MAG_BIAS_WU
#define BHI360_SENSOR_ID_GRA                     BHI385_SENSOR_ID_GRA
#define BHI360_SENSOR_ID_GRA_WU                  BHI385_SENSOR_ID_GRA_WU
#define BHI360_SENSOR_ID_LACC                    BHI385_SENSOR_ID_LACC
#define BHI360_SENSOR_ID_LACC_WU                 BHI385_SENSOR_ID_LACC_WU
#define BHI360_SENSOR_ID_RV                      BHI385_SENSOR_ID_RV
#define BHI360_SENSOR_ID_RV_WU                   BHI385_SENSOR_ID_RV_WU
#define BHI360_SENSOR_ID_GAMERV                  BHI385_SENSOR_ID_GAMERV
#define BHI360_SENSOR_ID_GAMERV_WU               BHI385_SENSOR_ID_GAMERV_WU
#define BHI360_SENSOR_ID_GEORV                   BHI385_SENSOR_ID_GEORV
#define BHI360_SENSOR_ID_GEORV_WU                BHI385_SENSOR_ID_GEORV_WU
#define BHI360_SENSOR_ID_ORI                     BHI385_SENSOR_ID_ORI
#define BHI360_SENSOR_ID_ORI_WU                  BHI385_SENSOR_ID_ORI_WU
#define BHI360_SENSOR_ID_TILT_DETECTOR           BHI385_SENSOR_ID_TILT_DETECTOR
#define BHI360_SENSOR_ID_STD                     BHI385_SENSOR_ID_STD
#define BHI360_SENSOR_ID_STC                     BHI385_SENSOR_ID_STC
#define BHI360_SENSOR_ID_SIG                     BHI385_SENSOR_ID_SIG
#define BHI360_SENSOR_ID_WAKE_GESTURE            BHI385_SENSOR_ID_WAKE_GESTURE
#define BHI360_SENSOR_ID_GLANCE_GESTURE          BHI385_SENSOR_ID_GLANCE_GESTURE
#define BHI360_SENSOR_ID_PICKUP_GESTURE          BHI385_SENSOR_ID_PICKUP_GESTURE
#define BHI360_SENSOR_ID_AR                      BHI385_SENSOR_ID_AR
#define BHI360_SENSOR_ID_PROX                    BHI385_SENSOR_ID_PROX
#define BHI360_SENSOR_ID_PROX_WU                 BHI385_SENSOR_ID_PROX_WU
#define BHI360_SENSOR_ID_LIGHT                   BHI385_SENSOR_ID_LIGHT
#define BHI360_SENSOR_ID_LIGHT_WU                BHI385_SENSOR_ID_LIGHT_WU
#define BHI360_SENSOR_ID_TEMP                    BHI385_SENSOR_ID_TEMP
#define BHI360_SENSOR_ID_BARO                    BHI385_SENSOR_ID_BARO
#define BHI360_SENSOR_ID_HUM                     BHI385_SENSOR_ID_HUM
#define BHI360_SENSOR_ID_GAS                     BHI385_SENSOR_ID_GAS
#define BHI360_SENSOR_ID_TEMP_WU                 BHI385_SENSOR_ID_TEMP_WU
#define BHI360_SENSOR_ID_BARO_WU                 BHI385_SENSOR_ID_BARO_WU
#define BHI360_SENSOR_ID_HUM_WU                  BHI385_SENSOR_ID_HUM_WU
#define BHI360_SENSOR_ID_GAS_WU                  BHI385_SENSOR_ID_GAS_WU
#define BHI360_SENSOR_ID_STC_LP                  BHI385_SENSOR_ID_STC_LP
#define BHI360_SENSOR_ID_STD_LP                  BHI385_SENSOR_ID_STD_LP
#define BHI360_SENSOR_ID_SIG_LP_WU               BHI385_SENSOR_ID_SIG_LP_WU
#define BHI360_SENSOR_ID_STC_LP_WU               BHI385_SENSOR_ID_STC_LP_WU
#define BHI360_SENSOR_ID_STD_LP_WU               BHI385_SENSOR_ID_STD_LP_WU
#define BHI360_SENSOR_ID_ANY_MOTION_LP_WU        BHI385_SENSOR_ID_ANY_MOTION_LP_WU
#define BHI360_SENSOR_ID_WRIST_TILT_GESTURE      BHI385_SENSOR_ID_WRIST_TILT_GESTURE
#define BHI360_SENSOR_ID_DEVICE_ORI              BHI385_SENSOR_ID_DEVICE_ORI
#define BHI360_SENSOR_ID_DEVICE_ORI_WU           BHI385_SENSOR_ID_DEVICE_ORI_WU
#define BHI360_SENSOR_ID_STATIONARY_DET          BHI385_SENSOR_ID_STATIONARY_DET
#define BHI360_SENSOR_ID_MOTION_DET              BHI385_SENSOR_ID_MOTION_DET
#define BHI360_SENSOR_ID_MULTI_TAP               BHI385_SENSOR_ID_MULTI_TAP
#define BHI360_SENSOR_ID_AR_WEAR_WU              BHI385_SENSOR_ID_AR_WEAR_WU
#define BHI360_SENSOR_ID_NO_MOTION_LP_WU         BHI385_SENSOR_ID_NO_MOTION_LP_WU
#define BHI360_SENSOR_ID_WRIST_GEST_DETECT_LP_WU BHI385_SENSOR_ID_WRIST_GEST_DETECT_LP_WU
#define BHI360_SENSOR_ID_WRIST_WEAR_LP_WU        BHI385_SENSOR_ID_WRIST_WEAR_LP_WU
#define BHI360_SENSOR_ID_STC_WU                  BHI385_SENSOR_ID_STC_WU
#define BHI360_SENSOR_ID_STD_WU                  BHI385_SENSOR_ID_STD_WU
#define BHI360_SENSOR_ID_SI_ACCEL                BHI385_SENSOR_ID_SI_ACCEL
#define BHI360_SENSOR_ID_SI_GYROS               BHI385_SENSOR_ID_SI_GYROS
#define BHI360_SENSOR_ID_HEAD_ORI_MIS_ALG        BHI385_SENSOR_ID_HEAD_ORI_MIS_ALG
#define BHI360_SENSOR_ID_IMU_HEAD_ORI_Q          BHI385_SENSOR_ID_IMU_HEAD_ORI_Q
#define BHI360_SENSOR_ID_NDOF_HEAD_ORI_Q         BHI385_SENSOR_ID_NDOF_HEAD_ORI_Q
#define BHI360_SENSOR_ID_IMU_HEAD_ORI_E          BHI385_SENSOR_ID_IMU_HEAD_ORI_E
#define BHI360_SENSOR_ID_NDOF_HEAD_ORI_E         BHI385_SENSOR_ID_NDOF_HEAD_ORI_E
#define BHI360_SENSOR_ID_AIR_QUALITY             BHI385_SENSOR_ID_AIR_QUALITY
#define BHI360_SENSOR_ID_EXCAMERA                BHI385_SENSOR_ID_EXCAMERA
#define BHI360_SENSOR_ID_GPS                     BHI385_SENSOR_ID_GPS
#define BHI360_SENSOR_ID_CUSTOM_START            BHI385_SENSOR_ID_CUSTOM_START
#define BHI360_SENSOR_ID_CUSTOM_END              BHI385_SENSOR_ID_CUSTOM_END
#define BHI360_SENSOR_BMP_TEMPERATURE            BHI385_SENSOR_BMP_TEMPERATURE
#define BHI360_SENSOR_BMP_TEMPERATURE_WU         BHI385_SENSOR_BMP_TEMPERATURE_WU
#define BHI360_SENSOR_ID_PRESSURE                BHI385_SENSOR_ID_PRESSURE
#define BHI360_SENSOR_ID_PRESSURE_WU             BHI385_SENSOR_ID_PRESSURE_WU

/* BHI385-specific API errors */
#define BHI360_E_INSUFFICIENT_MAX_SIMUL_SENSORS  BHI385_E_INSUFFICIENT_MAX_SIMUL_SENSORS
#define BHI360_E_INVALID_DATA                    BHI385_E_INVALID_DATA

/* ------------------------------------------------------------------ */
/* Inline parse helpers: present in BHI360 SDK but absent in BHI385.  */
/* Conversion factors verified against bhi360_parse.c source.         */
/* ------------------------------------------------------------------ */
#include <stdint.h>

/* 1 LSB = 1/128 Pa  (same wire format as BHI360) */
static inline void bhi360_parse_pressure(const uint8_t *data, float *out)
{
    *out = (float)BHI385_LE2U24(data) / 128.0f;
}

/* 1 LSB = 1/100 °C */
static inline void bhi360_parse_temperature_celsius(const uint8_t *data, float *out)
{
    *out = (float)BHI385_LE2S16(data) / 100.0f;
}

/* 1 LSB = 1 % */
static inline void bhi360_parse_humidity(const uint8_t *data, float *out)
{
    *out = (float)data[0];
}

#else /* BHI360 (default) -- include original SDK headers unchanged */

#include "bhi360.h"
#include "bhi360_defs.h"
#include "bhi360_parse.h"
#include "bhi360_event_data.h"
#include "bhi360_virtual_sensor_conf_param.h"
#include "bhi360_virtual_sensor_info_param.h"
#include "bhi360_bsx_algo_param.h"
#include "bhi360_activity_param.h"
#include "bhi360_bsec_param.h"
#include "bhi360_head_orientation_param.h"
#include "bhi360_multi_tap_param.h"
#include "bhi360_phy_sensor_ctrl_param.h"
#include "bhi360_system_param.h"

#endif /* USE_BHI385 */
#endif /* __BHI3_COMPAT_H__ */
