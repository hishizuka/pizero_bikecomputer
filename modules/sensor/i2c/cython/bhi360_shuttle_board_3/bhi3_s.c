#include "bhi3_s.h"

#ifdef USE_BHI3_S

//#include "bhi360/Bosch_Shuttle3_BHI360_BMM350C_BME688_IAQ.fw.h"
#include "bhi360/Bosch_Shuttle3_BHI360_BMM350C_BMP580_BME688.fw.h"

#define WORK_BUFFER_SIZE  2048
#define SCALING_FACTOR_INVALID_LIMIT  -1.0f

static void parse_euler_data(const struct bhi360_fifo_parse_data_info *callback_info, void *callback_ref);
static void parse_acc_data(const struct bhi360_fifo_parse_data_info *callback_info, void *callback_ref);
static void parse_gravity_data(const struct bhi360_fifo_parse_data_info *callback_info, void *callback_ref);
static void parse_linear_acc_data(const struct bhi360_fifo_parse_data_info *callback_info, void *callback_ref);
static void parse_temperature(const struct bhi360_fifo_parse_data_info *callback_info, void *callback_ref);
static void parse_pressure(const struct bhi360_fifo_parse_data_info *callback_info, void *callback_ref);
static void parse_humidity(const struct bhi360_fifo_parse_data_info *callback_info, void *callback_ref);

static void parse_meta_event(const struct bhi360_fifo_parse_data_info *callback_info, void *callback_ref);
static void print_api_error(int8_t rslt, struct bhi360_dev *dev);
static void upload_firmware(uint8_t boot_stat, struct bhi360_dev *dev);

enum bhi360_intf intf;
struct bhi360_dev bhy;
uint8_t work_buffer[WORK_BUFFER_SIZE];
struct bhi3_s_data bhi3_s_datas;


int8_t bhi3_s_init(void)
{
    uint8_t chip_id = 0;
    uint16_t version = 0;
    int8_t rslt;
    uint8_t hintr_ctrl, hif_ctrl, boot_status;
    uint8_t accuracy; /* Accuracy is reported as a meta event. It is being printed alongside the data */
    struct bhi360_virtual_sensor_conf_param_conf sensor_conf_eular = { 0 };
    struct bhi360_virtual_sensor_conf_param_conf sensor_conf_acc = { 0 };
    struct bhi360_virtual_sensor_conf_param_conf sensor_conf_gravity = { 0 };
    struct bhi360_virtual_sensor_conf_param_conf sensor_conf_linear_acc = { 0 };
    struct bhi360_virtual_sensor_conf_param_conf sensor_conf_temperature = { 0 };
    struct bhi360_virtual_sensor_conf_param_conf sensor_conf_pressure = { 0 };
    struct bhi360_virtual_sensor_conf_param_conf sensor_conf_humidity = { 0 };


#ifdef BHI360_USE_I2C
    intf = BHI360_I2C_INTERFACE;
#else
    intf = BHI360_SPI_INTERFACE;
#endif

    setup_interfaces(true, intf); /* Perform a power on reset */

#ifdef BHI360_USE_I2C
    rslt = bhi360_init(BHI360_I2C_INTERFACE, bhi360_i2c_read, bhi360_i2c_write, bhi360_delay_us, BHI360_RD_WR_LEN, NULL, &bhy);
#else
    rslt = bhi360_init(BHI360_SPI_INTERFACE, bhi360_spi_read, bhi360_spi_write, bhi360_delay_us, BHI360_RD_WR_LEN, NULL, &bhy);
#endif
    print_api_error(rslt, &bhy);

    rslt = bhi360_soft_reset(&bhy);
    print_api_error(rslt, &bhy);

    rslt = bhi360_get_chip_id(&chip_id, &bhy);
    print_api_error(rslt, &bhy);

    /* Check for a valid Chip ID */
    if (chip_id == BHI360_CHIP_ID)
    {
        printf("Chip ID read 0x%X\r\n", chip_id);
    }
    else
    {
        printf("Device not found. Chip ID read 0x%X\r\n", chip_id);
    }

    /* Configure the host interface */
    hif_ctrl = BHI360_HIF_CTRL_ASYNC_STATUS_CHANNEL;
    rslt = bhi360_set_host_intf_ctrl(hif_ctrl, &bhy);
    print_api_error(rslt, &bhy);

    /* Check the interrupt pin and FIFO configurations. Disable status and debug */
    hintr_ctrl = BHI360_ICTL_DISABLE_STATUS_FIFO | BHI360_ICTL_DISABLE_DEBUG;

    rslt = bhi360_set_host_interrupt_ctrl(hintr_ctrl, &bhy);
    print_api_error(rslt, &bhy);
    rslt = bhi360_get_host_interrupt_ctrl(&hintr_ctrl, &bhy);
    print_api_error(rslt, &bhy);

    printf("Host interrupt control\r\n");
    printf("    Wake up FIFO %s.\r\n", (hintr_ctrl & BHI360_ICTL_DISABLE_FIFO_W) ? "disabled" : "enabled");
    printf("    Non wake up FIFO %s.\r\n", (hintr_ctrl & BHI360_ICTL_DISABLE_FIFO_NW) ? "disabled" : "enabled");
    printf("    Status FIFO %s.\r\n", (hintr_ctrl & BHI360_ICTL_DISABLE_STATUS_FIFO) ? "disabled" : "enabled");
    printf("    Debugging %s.\r\n", (hintr_ctrl & BHI360_ICTL_DISABLE_DEBUG) ? "disabled" : "enabled");
    printf("    Fault %s.\r\n", (hintr_ctrl & BHI360_ICTL_DISABLE_FAULT) ? "disabled" : "enabled");
    printf("    Interrupt is %s.\r\n", (hintr_ctrl & BHI360_ICTL_ACTIVE_LOW) ? "active low" : "active high");
    printf("    Interrupt is %s triggered.\r\n", (hintr_ctrl & BHI360_ICTL_EDGE) ? "pulse" : "level");
    printf("    Interrupt pin drive is %s.\r\n", (hintr_ctrl & BHI360_ICTL_OPEN_DRAIN) ? "open drain" : "push-pull");

    /* Configure the host interface */
    hif_ctrl = 0;
    rslt = bhi360_set_host_intf_ctrl(hif_ctrl, &bhy);
    print_api_error(rslt, &bhy);

    /* Check if the sensor is ready to load firmware */
    rslt = bhi360_get_boot_status(&boot_status, &bhy);
    print_api_error(rslt, &bhy);

    if (boot_status & BHI360_BST_HOST_INTERFACE_READY)
    {
        upload_firmware(boot_status, &bhy);

        rslt = bhi360_get_kernel_version(&version, &bhy);
        print_api_error(rslt, &bhy);
        if ((rslt == BHI360_OK) && (version != 0))
        {
            printf("Boot successful. Kernel version %u.\r\n", version);
        }

        rslt = bhi360_register_fifo_parse_callback(BHI360_SYS_ID_META_EVENT, parse_meta_event, (void*)&accuracy, &bhy);
        print_api_error(rslt, &bhy);
        rslt = bhi360_register_fifo_parse_callback(BHI360_SYS_ID_META_EVENT_WU, parse_meta_event, (void*)&accuracy, &bhy);
        print_api_error(rslt, &bhy);
        rslt = bhi360_register_fifo_parse_callback(BHI360_SENSOR_ID_ORI, parse_euler_data, (void*)&accuracy, &bhy);
        print_api_error(rslt, &bhy);
        rslt = bhi360_register_fifo_parse_callback(BHI360_SENSOR_ID_ACC, parse_acc_data, (void*)&accuracy, &bhy);
        print_api_error(rslt, &bhy);
        rslt = bhi360_register_fifo_parse_callback(BHI360_SENSOR_ID_GRA, parse_gravity_data, (void*)&accuracy, &bhy);
        print_api_error(rslt, &bhy);
        rslt = bhi360_register_fifo_parse_callback(BHI360_SENSOR_ID_LACC, parse_linear_acc_data, (void*)&accuracy, &bhy);
        print_api_error(rslt, &bhy);
        rslt = bhi360_register_fifo_parse_callback(BHI360_SENSOR_ID_BARO, parse_pressure, NULL, &bhy);
        print_api_error(rslt, &bhy);
        rslt = bhi360_register_fifo_parse_callback(BHI360_SENSOR_ID_TEMP, parse_temperature, NULL, &bhy);
        print_api_error(rslt, &bhy);
        rslt = bhi360_register_fifo_parse_callback(BHI360_SENSOR_ID_HUM, parse_humidity, NULL, &bhy);
        print_api_error(rslt, &bhy);

        rslt = bhi360_get_and_process_fifo(work_buffer, WORK_BUFFER_SIZE, &bhy);
        print_api_error(rslt, &bhy);
    }
    else
    {
        printf("Host interface not ready. Exiting\r\n");

        close_interfaces(intf);

        return 0;
    }

    /* Update the callback table to enable parsing of sensor data */
    rslt = bhi360_update_virtual_sensor_list(&bhy);
    print_api_error(rslt, &bhy);

    sensor_conf_eular.sample_rate = 10.0f;
    sensor_conf_eular.latency = 0;
    rslt = bhi360_virtual_sensor_conf_param_set_cfg(BHI360_SENSOR_ID_ORI, &sensor_conf_eular, &bhy);
    print_api_error(rslt, &bhy);
    printf("Enable %s at %.2fHz.\r\n", get_sensor_name(BHI360_SENSOR_ID_ORI), sensor_conf_eular.sample_rate);

    sensor_conf_acc.sample_rate = 10.0f;
    sensor_conf_acc.latency = 0;
    rslt = bhi360_virtual_sensor_conf_param_set_cfg(BHI360_SENSOR_ID_ACC, &sensor_conf_acc, &bhy);
    print_api_error(rslt, &bhy);
    printf("Enable %s at %.2fHz.\r\n", get_sensor_name(BHI360_SENSOR_ID_ACC), sensor_conf_acc.sample_rate);
     rslt = bhi360_set_virt_sensor_range(BHI360_SENSOR_ID_ACC, BHI360_ACCEL_16G, &bhy);
     print_api_error(rslt, &bhy);

    sensor_conf_gravity.sample_rate = 10.0f;
    sensor_conf_gravity.latency = 0;
    rslt = bhi360_virtual_sensor_conf_param_set_cfg(BHI360_SENSOR_ID_GRA, &sensor_conf_gravity, &bhy);
    print_api_error(rslt, &bhy);
    printf("Enable %s at %.2fHz.\r\n", get_sensor_name(BHI360_SENSOR_ID_GRA), sensor_conf_gravity.sample_rate);

    sensor_conf_linear_acc.sample_rate = 10.0f;
    sensor_conf_linear_acc.latency = 0;
    rslt = bhi360_virtual_sensor_conf_param_set_cfg(BHI360_SENSOR_ID_LACC, &sensor_conf_linear_acc, &bhy);
    print_api_error(rslt, &bhy);
    printf("Enable %s at %.2fHz.\r\n", get_sensor_name(BHI360_SENSOR_ID_LACC), sensor_conf_linear_acc.sample_rate);

    sensor_conf_pressure.sample_rate = 1.0f;
    sensor_conf_pressure.latency = 0;
    rslt = bhi360_virtual_sensor_conf_param_set_cfg(BHI360_SENSOR_ID_BARO, &sensor_conf_pressure, &bhy);
    print_api_error(rslt, &bhy);
    printf("Enable %s at %.2fHz.\r\n", get_sensor_name(BHI360_SENSOR_ID_BARO), sensor_conf_pressure.sample_rate);

    sensor_conf_temperature.sample_rate = 1.0f;
    sensor_conf_temperature.latency = 0;
    rslt = bhi360_virtual_sensor_conf_param_set_cfg(BHI360_SENSOR_ID_TEMP, &sensor_conf_temperature, &bhy);
    print_api_error(rslt, &bhy);
    printf("Enable %s at %.2fHz.\r\n", get_sensor_name(BHI360_SENSOR_ID_TEMP), sensor_conf_temperature.sample_rate);

    sensor_conf_humidity.sample_rate = 1.0f;
    sensor_conf_humidity.latency = 0;
    rslt = bhi360_virtual_sensor_conf_param_set_cfg(BHI360_SENSOR_ID_HUM, &sensor_conf_humidity, &bhy);
    print_api_error(rslt, &bhy);
    printf("Enable %s at %.2fHz.\r\n", get_sensor_name(BHI360_SENSOR_ID_HUM), sensor_conf_humidity.sample_rate);

    return rslt;
}

static void parse_euler_data(const struct bhi360_fifo_parse_data_info *callback_info, void *callback_ref)
{
    (void)callback_ref;
    struct bhi360_event_data_orientation data;
    //uint32_t s, ns;
    uint8_t *accuracy = (uint8_t*)callback_ref;
    if (callback_info->data_size != 7) /* Check for a valid payload size. Includes sensor ID */
    {
        return;
    }

    bhi360_event_data_parse_orientation(callback_info->data_ptr, &data);

    //uint64_t timestamp = *callback_info->time_stamp; /* Store the last timestamp */

    //timestamp = timestamp * 15625; /* Timestamp is now in nanoseconds */
    //s = (uint32_t)(timestamp / UINT64_C(1000000000));
    //ns = (uint32_t)(timestamp - (s * UINT64_C(1000000000)));
    bhi3_s_datas.heading = data.heading * 360.0f / 32768.0f;
    bhi3_s_datas.pitch = data.pitch * 360.0f / 32768.0f;
    bhi3_s_datas.roll = data.roll * 360.0f / 32768.0f;

    if (accuracy)
    {
        bhi3_s_datas.orientation_accuracy = *accuracy;
    }
}

static void parse_acc_data(const struct bhi360_fifo_parse_data_info *callback_info, void *callback_ref) {
    struct bhi360_event_data_xyz data;
    uint8_t *accuracy = (uint8_t*)callback_ref;
    float scaling_factor = SCALING_FACTOR_INVALID_LIMIT;

    if (!callback_info)
    {
        printf("Null reference\r\n");
        return;
    }
    if (callback_info->data_size != 7) /* Check for a valid payload size. Includes sensor ID */
    {
        return;
    }

    bhi360_event_data_parse_xyz(callback_info->data_ptr, &data);
    //scaling_factor = (float)BHI360_ACCEL_8G / 32768.0f; // since the sensor data will be scaled to signed 16bits
    scaling_factor = get_sensor_dynamic_range_scaling(callback_info->sensor_id, (float)BHI360_ACCEL_16G);
    bhi3_s_datas.acc_x = data.x * scaling_factor;
    bhi3_s_datas.acc_y = data.y * scaling_factor;
    bhi3_s_datas.acc_z = data.z * scaling_factor;

    if (accuracy)
    {
        bhi3_s_datas.acc_accuracy = *accuracy;
    }
    //printf("Acceleration data: X: %.3f, Y: %.3f, Z: %.3f\r\n", bhi3_s_datas.acc_x, bhi3_s_datas.acc_y, bhi3_s_datas.acc_z);
}

static void parse_gravity_data(const struct bhi360_fifo_parse_data_info *callback_info, void *callback_ref)
{
    struct bhi360_event_data_xyz data;
    uint8_t *accuracy = (uint8_t*)callback_ref;
    float scaling_factor = SCALING_FACTOR_INVALID_LIMIT;

    if (!callback_info)
    {
        printf("Null reference\r\n");
        return;
    }
    if (callback_info->data_size != 7) /* Check for a valid payload size. Includes sensor ID */
    {
        return;
    }

    bhi360_event_data_parse_xyz(callback_info->data_ptr, &data);
    scaling_factor = (float)BHI360_ACCEL_8G / 32768.0f; // since the sensor data will be scaled to signed 16bits
    bhi3_s_datas.gravity_x = data.x * scaling_factor;
    bhi3_s_datas.gravity_y = data.y * scaling_factor;
    bhi3_s_datas.gravity_z = data.z * scaling_factor;

    if (accuracy)
    {
        bhi3_s_datas.gravity_accuracy = *accuracy;
    }
    //printf("Gravity data: X: %.3f, Y: %.3f, Z: %.3f\r\n", bhi3_s_datas.acc_x, bhi3_s_datas.acc_y, bhi3_s_datas.acc_z);
}

static void parse_linear_acc_data(const struct bhi360_fifo_parse_data_info *callback_info, void *callback_ref) {
    struct bhi360_event_data_xyz data;
    uint8_t *accuracy = (uint8_t*)callback_ref;
    float scaling_factor = SCALING_FACTOR_INVALID_LIMIT;

    if (!callback_info)
    {
        printf("Null reference\r\n");
        return;
    }
    if (callback_info->data_size != 7) /* Check for a valid payload size. Includes sensor ID */
    {
        return;
    }

    bhi360_event_data_parse_xyz(callback_info->data_ptr, &data);
    scaling_factor = (float)BHI360_ACCEL_8G / 32768.0f; // since the sensor data will be scaled to signed 16bits
    bhi3_s_datas.linear_acc_x = data.x * scaling_factor;
    bhi3_s_datas.linear_acc_y = data.y * scaling_factor;
    bhi3_s_datas.linear_acc_z = data.z * scaling_factor;

    if (accuracy)
    {
        bhi3_s_datas.linear_acc_accuracy = *accuracy;
    }
    //printf("Linear data: X: %.3f, Y: %.3f, Z: %.3f\r\n", bhi3_s_datas.acc_x, bhi3_s_datas.acc_y, bhi3_s_datas.acc_z);
}

static void parse_pressure(const struct bhi360_fifo_parse_data_info *callback_info, void *callback_ref)
{
    bhi360_float pressure;

    if (!callback_info)
    {
        printf("Null reference\r\n");
        return;
    }
    if (callback_info->data_size != 4) /* Check for a valid payload size. Includes sensor ID */
    {
        return;
    }

    bhi360_parse_pressure(callback_info->data_ptr, &pressure);
    bhi3_s_datas.pressure = pressure / 100;
}

static void parse_temperature(const struct bhi360_fifo_parse_data_info *callback_info, void *callback_ref)
{
    bhi360_float temperature;;

    if (!callback_info)
    {
        printf("Null reference\r\n");
        return;
    }
    if (callback_info->data_size != 3) /* Check for a valid payload size. Includes sensor ID */
    {
        return;
    }

    bhi360_parse_temperature_celsius(callback_info->data_ptr, &temperature);
    bhi3_s_datas.temperature = temperature;
}

static void parse_humidity(const struct bhi360_fifo_parse_data_info *callback_info, void *callback_ref)
{
    bhi360_float humidity;

    if (!callback_info)
    {
        printf("Null reference\r\n");
        return;
    }
    if (callback_info->data_size != 2) /* Check for a valid payload size. Includes sensor ID */
    {
        return;
    }

    bhi360_parse_humidity(callback_info->data_ptr, &humidity);
    bhi3_s_datas.humidity = humidity;
}

static void parse_meta_event(const struct bhi360_fifo_parse_data_info *callback_info, void *callback_ref)
{
    (void)callback_ref;
    uint8_t meta_event_type = callback_info->data_ptr[0];
    uint8_t byte1 = callback_info->data_ptr[1];
    uint8_t byte2 = callback_info->data_ptr[2];
    uint8_t *accuracy = (uint8_t*)callback_ref;
    char *event_text;

    if (callback_info->sensor_id == BHI360_SYS_ID_META_EVENT)
    {
        event_text = "[META EVENT]";
    }
    else if (callback_info->sensor_id == BHI360_SYS_ID_META_EVENT_WU)
    {
        event_text = "[META EVENT WAKE UP]";
    }
    else
    {
        return;
    }

    switch (meta_event_type)
    {
        case BHI360_META_EVENT_FLUSH_COMPLETE:
            printf("%s Flush complete for sensor id %u (%s)\r\n", event_text, byte1, get_sensor_name(byte1));
            break;
        case BHI360_META_EVENT_SAMPLE_RATE_CHANGED:
            printf("%s Sample rate changed for sensor id %u (%s)\r\n", event_text, byte1, get_sensor_name(byte1));
            break;
        case BHI360_META_EVENT_POWER_MODE_CHANGED:
            printf("%s Power mode changed for sensor id %u (%s)\r\n", event_text, byte1, get_sensor_name(byte1));
            break;
        case BHI360_META_EVENT_ALGORITHM_EVENTS:
            printf("%s Algorithm event\r\n", event_text);
            break;
        case BHI360_META_EVENT_SENSOR_STATUS:
            printf("%s Accuracy for sensor id %u (%s) changed to %u (%s)\r\n", event_text, byte1, get_sensor_name(byte1), byte2, get_sensor_name(byte2));
            if (accuracy)
            {
                *accuracy = byte2;
            }

            break;
        case BHI360_META_EVENT_BSX_DO_STEPS_MAIN:
            printf("%s BSX event (do steps main)\r\n", event_text);
            break;
        case BHI360_META_EVENT_BSX_DO_STEPS_CALIB:
            printf("%s BSX event (do steps calib)\r\n", event_text);
            break;
        case BHI360_META_EVENT_BSX_GET_OUTPUT_SIGNAL:
            printf("%s BSX event (get output signal)\r\n", event_text);
            break;
        case BHI360_META_EVENT_SENSOR_ERROR:
            printf("%s Sensor id %u (%s) reported error 0x%02X\r\n", event_text, byte1, get_sensor_name(byte1), byte2);
            break;
        case BHI360_META_EVENT_FIFO_OVERFLOW:
            printf("%s FIFO overflow\r\n", event_text);
            break;
        case BHI360_META_EVENT_DYNAMIC_RANGE_CHANGED:
            printf("%s Dynamic range changed for sensor id %u (%s)\r\n", event_text, byte1, get_sensor_name(byte1));
            break;
        case BHI360_META_EVENT_FIFO_WATERMARK:
            printf("%s FIFO watermark reached\r\n", event_text);
            break;
        case BHI360_META_EVENT_INITIALIZED:
            printf("%s Firmware initialized. Firmware version %u\r\n", event_text, ((uint16_t)byte2 << 8) | byte1);
            break;
        case BHI360_META_TRANSFER_CAUSE:
            printf("%s Transfer cause for sensor id %u (%s)\r\n", event_text, byte1, get_sensor_name(byte1));
            break;
        case BHI360_META_EVENT_SENSOR_FRAMEWORK:
            printf("%s Sensor framework event for sensor id %u (%s)\r\n", event_text, byte1, get_sensor_name(byte1));
            break;
        case BHI360_META_EVENT_RESET:
            printf("%s Reset event\r\n", event_text);
            break;
        case BHI360_META_EVENT_SPACER:
            break;
        default:
            printf("%s Unknown meta event with id: %u\r\n", event_text, meta_event_type);
            break;
    }
}

static void print_api_error(int8_t rslt, struct bhi360_dev *dev)
{
    if (rslt != BHI360_OK)
    {
        printf("%s\r\n", get_api_error(rslt));
        if ((rslt == BHI360_E_IO) && (dev != NULL))
        {
            printf("%s\r\n", get_intf_error(dev->hif.intf_rslt));
            dev->hif.intf_rslt = BHI360_INTF_RET_SUCCESS;
        }

        close_interfaces(intf);
        exit(0);
    }
}

static void upload_firmware(uint8_t boot_stat, struct bhi360_dev *dev)
{
    uint8_t sensor_error;
    int8_t temp_rslt;
    int8_t rslt = BHI360_OK;

    printf("Loading firmware into RAM.\r\n");
    rslt = bhi360_upload_firmware_to_ram(bhi360_firmware_image, sizeof(bhi360_firmware_image), dev);
    temp_rslt = bhi360_get_error_value(&sensor_error, dev);
    if (sensor_error)
    {
        printf("%s\r\n", get_sensor_error_text(sensor_error));
    }

    print_api_error(rslt, dev);
    print_api_error(temp_rslt, dev);

    printf("Booting from RAM.\r\n");
    rslt = bhi360_boot_from_ram(dev);

    temp_rslt = bhi360_get_error_value(&sensor_error, dev);
    if (sensor_error)
    {
        printf("%s\r\n", get_sensor_error_text(sensor_error));
    }

    print_api_error(rslt, dev);
    print_api_error(temp_rslt, dev);
}

void bhi3_s_read_data(bhi3_s_data *data) {
    int rslt;
    while (get_interrupt_status()) {
        //Data from the FIFO is read and the relevant callbacks if registered are called
        rslt = bhi360_get_and_process_fifo(work_buffer, WORK_BUFFER_SIZE, &bhy);
        print_api_error(rslt, &bhy);
        data->acc_x = bhi3_s_datas.acc_x;
        data->acc_y = bhi3_s_datas.acc_y;
        data->acc_z = bhi3_s_datas.acc_z;
        data->heading = bhi3_s_datas.heading;
        data->pitch = bhi3_s_datas.pitch;
        data->roll = bhi3_s_datas.roll;
        data->temperature = bhi3_s_datas.temperature;
        data->pressure = bhi3_s_datas.pressure;
        data->humidity = bhi3_s_datas.humidity;
    }
}
void bhi3_s_close() {
    close_interfaces(intf);
}

#ifndef NOUSE_MAIN
int main() {
    bhi3_s_init();
    return 0;
};
#endif

#else

#ifndef NOUSE_MAIN
int main() {
    return 0;
};
#endif

#endif
