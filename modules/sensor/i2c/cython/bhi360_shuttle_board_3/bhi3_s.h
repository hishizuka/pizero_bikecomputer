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
    float heading;
    float pitch;
    float roll;
    uint8_t orientation_accuracy;
    float acc_x;
    float acc_y;
    float acc_z;
    uint8_t acc_accuracy;
    float gravity_x;
    float gravity_y;
    float gravity_z;
    uint8_t gravity_accuracy;
    float linear_acc_x;
    float linear_acc_y;
    float linear_acc_z;
    uint8_t linear_acc_accuracy;
    float temperature;
    float pressure;
    float humidity;
} bhi3_s_data;

int8_t bhi3_s_init();
void bhi3_s_read_data(bhi3_s_data *data);
void bhi3_s_close();

#else
int8_t bhi3_s_init() {
    //printf("no sensor bhi3_s\n");
    return -1;
}
void bhi3_s_read_data(bhi3_s_data *data) {};
void bhi3_s_close() {};

#endif

#ifdef __cplusplus
}
#endif

#endif
