#ifndef __BHI3_S
#define __BHI3_S

#ifdef __cplusplus
extern "C" {
#endif

#include <stdlib.h>
#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <inttypes.h>

#ifdef USE_BHI3_S

#include "common.h"

#include "bhi360.h"
#include "bhi360_parse.h"
#include "bhi360_virtual_sensor_conf_param.h"
#include "bhi360_event_data.h"

#include "common.h"

typedef struct bhi3_s_data
{
    /* Acceleration: raw -> accuracy -> filtered -> norm */
    float acc_x_raw;
    float acc_y_raw;
    float acc_z_raw;
    uint8_t acc_accuracy;
    float acc_x;
    float acc_y;
    float acc_z;
    float acc_rms_norm;

    /* Gravity and linear acceleration */
    float gravity_x;
    float gravity_y;
    float gravity_z;
    uint8_t gravity_accuracy;
    float linear_acc_x;
    float linear_acc_y;
    float linear_acc_z;
    uint8_t linear_acc_accuracy;
    uint8_t moving;

    /* Gyro: raw -> accuracy -> filtered */
    float gyro_x_raw;
    float gyro_y_raw;
    float gyro_z_raw;
    uint8_t gyro_accuracy;
    float gyro_x;
    float gyro_y;
    float gyro_z;

    /* Orientation: raw -> accuracy -> filtered */
    float heading_raw;
    float pitch_raw;
    float roll_raw;
    uint8_t orientation_accuracy;
    float heading;
    float pitch;
    float roll;

    /* Environment */
    float pressure_raw;
    float pressure;
    float temperature;
    float humidity;
} bhi3_s_data;

int8_t bhi3_s_init();
void bhi3_s_read_data(bhi3_s_data *data);
bool bhi3_s_ready();
int8_t bhi3_s_last_error();
void bhi3_s_close();
int8_t bhi3_s_raw_log_start(const char *path);
void bhi3_s_raw_log_stop(void);
int8_t bhi3_s_raw_log_start_and_stop(const char *path);
bool bhi3_s_raw_log_is_enabled(void);

#else
int8_t bhi3_s_init() {
    //printf("no sensor bhi3_s\n");
    return -1;
}
void bhi3_s_read_data(bhi3_s_data *data) {};
bool bhi3_s_ready() { return false; }
int8_t bhi3_s_last_error() { return -1; }
void bhi3_s_close() {};
int8_t bhi3_s_raw_log_start(const char *path) { (void)path; return -1; };
void bhi3_s_raw_log_stop(void) {};
int8_t bhi3_s_raw_log_start_and_stop(const char *path) { (void)path; return -1; };
bool bhi3_s_raw_log_is_enabled(void) { return false; };

#endif

#ifdef __cplusplus
}
#endif

#endif
