#include "bhi3_s.h"

#ifdef USE_BHI3_S

//#include "bhi360/Bosch_Shuttle3_BHI360_BMM350C_BME688_IAQ.fw.h"
#include "bhi360/Bosch_Shuttle3_BHI360_BMM350C_BMP580_BME688.fw.h"

#include <pthread.h>
#include <string.h>
#include <unistd.h>

#define WORK_BUFFER_SIZE 2048
#define SCALING_FACTOR_INVALID_LIMIT -1.0f
#define INTERRUPT_WAIT_TIMEOUT_MS 100U
#define BHI360_META_EVENT_INTERNAL_STATUS 20U

static void parse_euler_data(const struct bhi360_fifo_parse_data_info *callback_info, void *callback_ref);
static void parse_acc_data(const struct bhi360_fifo_parse_data_info *callback_info, void *callback_ref);
static void parse_gravity_data(const struct bhi360_fifo_parse_data_info *callback_info, void *callback_ref);
static void parse_linear_acc_data(const struct bhi360_fifo_parse_data_info *callback_info, void *callback_ref);
static void parse_temperature(const struct bhi360_fifo_parse_data_info *callback_info, void *callback_ref);
static void parse_pressure(const struct bhi360_fifo_parse_data_info *callback_info, void *callback_ref);
static void parse_humidity(const struct bhi360_fifo_parse_data_info *callback_info, void *callback_ref);
static void parse_meta_event(const struct bhi360_fifo_parse_data_info *callback_info, void *callback_ref);

static int8_t upload_firmware(uint8_t boot_stat, struct bhi360_dev *dev);
static int8_t bhi3_s_device_bootstrap(void);
static void bhi3_s_report_api_error(int8_t rslt, struct bhi360_dev *dev);
static void bhi3_s_log_interrupt_ctrl(uint8_t hintr_ctrl);
static void bhi3_s_mark_error(int8_t rslt);
static bool bhi3_s_should_continue(void);
static void bhi3_s_reset_local_data(void);
static void bhi3_s_publish_latest_data(void);
static void *bhi3_s_worker(void *arg);

enum bhi360_intf intf;
static struct bhi360_dev bhy;
static uint8_t work_buffer[WORK_BUFFER_SIZE];
static struct bhi3_s_data bhi3_s_datas;

typedef struct bhi3_s_context
{
    pthread_t thread;
    pthread_mutex_t lock;
    bool lock_initialized;
    bool running;
    bool thread_started;
    bool ready;
    bool data_valid;
    int8_t last_error;
    struct bhi3_s_data latest_data;
} bhi3_s_context;

static bhi3_s_context ctx = {
    .lock_initialized = false,
    .running = false,
    .thread_started = false,
    .ready = false,
    .data_valid = false,
    .last_error = BHI360_OK,
};

int8_t bhi3_s_init(void)
{
    int rc;

    if (!ctx.lock_initialized)
    {
        rc = pthread_mutex_init(&ctx.lock, NULL);
        if (rc != 0)
        {
            fprintf(stderr, "[BHI3] Failed to init mutex (%d)\n", rc);
            return -1;
        }
        ctx.lock_initialized = true;
    }

    pthread_mutex_lock(&ctx.lock);
    if (ctx.thread_started)
    {
        pthread_mutex_unlock(&ctx.lock);
        return 0;
    }

    ctx.running = true;
    ctx.thread_started = true;
    ctx.ready = false;
    ctx.data_valid = false;
    ctx.last_error = BHI360_OK;
    memset(&ctx.latest_data, 0, sizeof(ctx.latest_data));
    bhi3_s_reset_local_data();
    pthread_mutex_unlock(&ctx.lock);

    rc = pthread_create(&ctx.thread, NULL, bhi3_s_worker, NULL);
    if (rc != 0)
    {
        fprintf(stderr, "[BHI3] Failed to start worker thread (%d)\n", rc);
        pthread_mutex_lock(&ctx.lock);
        ctx.thread_started = false;
        ctx.running = false;
        ctx.last_error = -1;
        pthread_mutex_unlock(&ctx.lock);
        return -1;
    }

    return 0;
}

void bhi3_s_read_data(bhi3_s_data *data)
{
    if (!data || !ctx.lock_initialized)
    {
        return;
    }

    pthread_mutex_lock(&ctx.lock);
    *data = ctx.latest_data;
    pthread_mutex_unlock(&ctx.lock);
}

bool bhi3_s_ready(void)
{
    bool ready = false;

    if (!ctx.lock_initialized)
    {
        return false;
    }

    pthread_mutex_lock(&ctx.lock);
    ready = ctx.ready && ctx.data_valid && (ctx.last_error == BHI360_OK);
    pthread_mutex_unlock(&ctx.lock);

    return ready;
}

int8_t bhi3_s_last_error(void)
{
    int8_t err = -1;

    if (!ctx.lock_initialized)
    {
        return err;
    }

    pthread_mutex_lock(&ctx.lock);
    err = ctx.last_error;
    pthread_mutex_unlock(&ctx.lock);

    return err;
}

void bhi3_s_close(void)
{
    if (!ctx.lock_initialized)
    {
        return;
    }

    pthread_mutex_lock(&ctx.lock);
    if (!ctx.thread_started)
    {
        pthread_mutex_unlock(&ctx.lock);
        return;
    }

    ctx.running = false;
    pthread_mutex_unlock(&ctx.lock);

    pthread_join(ctx.thread, NULL);

    pthread_mutex_lock(&ctx.lock);
    ctx.thread_started = false;
    ctx.ready = false;
    ctx.data_valid = false;
    pthread_mutex_unlock(&ctx.lock);
}

static void *bhi3_s_worker(void *arg)
{
    (void)arg;
    int8_t rslt;

    rslt = bhi3_s_device_bootstrap();
    if (rslt != BHI360_OK)
    {
        bhi3_s_mark_error(rslt);
        return NULL;
    }

    pthread_mutex_lock(&ctx.lock);
    ctx.ready = true;
    pthread_mutex_unlock(&ctx.lock);

    while (bhi3_s_should_continue())
    {
        if (!bhi3_wait_for_interrupt(INTERRUPT_WAIT_TIMEOUT_MS))
        {
            continue;
        }

        do
        {
            rslt = bhi360_get_and_process_fifo(work_buffer, WORK_BUFFER_SIZE, &bhy);
            if (rslt != BHI360_OK)
            {
                bhi3_s_report_api_error(rslt, &bhy);
                bhi3_s_mark_error(rslt);
                break;
            }
        }
        while (bhi3_s_should_continue() && get_interrupt_status());

        if (rslt != BHI360_OK)
        {
            break;
        }

        bhi3_s_publish_latest_data();
    }

    close_interfaces(intf);

    pthread_mutex_lock(&ctx.lock);
    ctx.ready = false;
    pthread_mutex_unlock(&ctx.lock);

    return NULL;
}

static int8_t bhi3_s_device_bootstrap(void)
{
    uint8_t chip_id = 0;
    uint16_t version = 0;
    int8_t rslt;
    uint8_t hintr_ctrl;
    uint8_t hif_ctrl;
    uint8_t boot_status;
    uint8_t accuracy = 0;
    struct bhi360_virtual_sensor_conf_param_conf sensor_conf_eular = { 0 };
    struct bhi360_virtual_sensor_conf_param_conf sensor_conf_acc = { 0 };
    struct bhi360_virtual_sensor_conf_param_conf sensor_conf_gravity = { 0 };
    struct bhi360_virtual_sensor_conf_param_conf sensor_conf_linear_acc = { 0 };
    struct bhi360_virtual_sensor_conf_param_conf sensor_conf_temperature = { 0 };
    struct bhi360_virtual_sensor_conf_param_conf sensor_conf_pressure = { 0 };
    struct bhi360_virtual_sensor_conf_param_conf sensor_conf_humidity = { 0 };

#ifdef BHI3_USE_I2C
    intf = BHI360_I2C_INTERFACE;
#else
    intf = BHI360_SPI_INTERFACE;
#endif

    setup_interfaces(true, intf);

#ifdef BHI3_USE_I2C
    rslt = bhi360_init(BHI360_I2C_INTERFACE, bhi360_i2c_read, bhi360_i2c_write, bhi360_delay_us, BHI360_RD_WR_LEN, NULL, &bhy);
#else
    rslt = bhi360_init(BHI360_SPI_INTERFACE, bhi360_spi_read, bhi360_spi_write, bhi360_delay_us, BHI360_RD_WR_LEN, NULL, &bhy);
#endif
    if (rslt != BHI360_OK)
    {
        bhi3_s_report_api_error(rslt, &bhy);
        close_interfaces(intf);
        return rslt;
    }

    rslt = bhi360_soft_reset(&bhy);
    if (rslt != BHI360_OK)
    {
        bhi3_s_report_api_error(rslt, &bhy);
        close_interfaces(intf);
        return rslt;
    }

    rslt = bhi360_get_chip_id(&chip_id, &bhy);
    if (rslt != BHI360_OK)
    {
        bhi3_s_report_api_error(rslt, &bhy);
        close_interfaces(intf);
        return rslt;
    }

    if (chip_id == BHI360_CHIP_ID)
    {
        printf("Chip ID read 0x%X\r\n", chip_id);
    }
    else
    {
        printf("Device not found. Chip ID read 0x%X\r\n", chip_id);
        close_interfaces(intf);
        return BHI360_E_IO;
    }

    hif_ctrl = BHI360_HIF_CTRL_ASYNC_STATUS_CHANNEL;
    rslt = bhi360_set_host_intf_ctrl(hif_ctrl, &bhy);
    if (rslt != BHI360_OK)
    {
        bhi3_s_report_api_error(rslt, &bhy);
        close_interfaces(intf);
        return rslt;
    }

    hintr_ctrl = BHI360_ICTL_DISABLE_STATUS_FIFO | BHI360_ICTL_DISABLE_DEBUG;
    rslt = bhi360_set_host_interrupt_ctrl(hintr_ctrl, &bhy);
    if (rslt != BHI360_OK)
    {
        bhi3_s_report_api_error(rslt, &bhy);
        close_interfaces(intf);
        return rslt;
    }

    rslt = bhi360_get_host_interrupt_ctrl(&hintr_ctrl, &bhy);
    if (rslt != BHI360_OK)
    {
        bhi3_s_report_api_error(rslt, &bhy);
        close_interfaces(intf);
        return rslt;
    }

    bhi3_s_log_interrupt_ctrl(hintr_ctrl);

    hif_ctrl = 0;
    rslt = bhi360_set_host_intf_ctrl(hif_ctrl, &bhy);
    if (rslt != BHI360_OK)
    {
        bhi3_s_report_api_error(rslt, &bhy);
        close_interfaces(intf);
        return rslt;
    }

    rslt = bhi360_get_boot_status(&boot_status, &bhy);
    if (rslt != BHI360_OK)
    {
        bhi3_s_report_api_error(rslt, &bhy);
        close_interfaces(intf);
        return rslt;
    }

    if (!(boot_status & BHI360_BST_HOST_INTERFACE_READY))
    {
        printf("Host interface not ready. Exiting\r\n");
        close_interfaces(intf);
        return BHI360_E_TIMEOUT;
    }

    rslt = upload_firmware(boot_status, &bhy);
    if (rslt != BHI360_OK)
    {
        close_interfaces(intf);
        return rslt;
    }

    rslt = bhi360_get_kernel_version(&version, &bhy);
    if (rslt == BHI360_OK && version != 0)
    {
        printf("Boot successful. Kernel version %u.\r\n", version);
    }
    else
    {
        bhi3_s_report_api_error(rslt, &bhy);
    }

    rslt = bhi360_register_fifo_parse_callback(BHI360_SYS_ID_META_EVENT, parse_meta_event, (void*)&accuracy, &bhy);
    if (rslt != BHI360_OK)
    {
        bhi3_s_report_api_error(rslt, &bhy);
        close_interfaces(intf);
        return rslt;
    }

    rslt = bhi360_register_fifo_parse_callback(BHI360_SYS_ID_META_EVENT_WU, parse_meta_event, (void*)&accuracy, &bhy);
    if (rslt != BHI360_OK)
    {
        bhi3_s_report_api_error(rslt, &bhy);
        close_interfaces(intf);
        return rslt;
    }

    rslt = bhi360_register_fifo_parse_callback(BHI360_SENSOR_ID_ORI, parse_euler_data, (void*)&accuracy, &bhy);
    if (rslt != BHI360_OK)
    {
        bhi3_s_report_api_error(rslt, &bhy);
        close_interfaces(intf);
        return rslt;
    }

    rslt = bhi360_register_fifo_parse_callback(BHI360_SENSOR_ID_ACC, parse_acc_data, (void*)&accuracy, &bhy);
    if (rslt != BHI360_OK)
    {
        bhi3_s_report_api_error(rslt, &bhy);
        close_interfaces(intf);
        return rslt;
    }

    rslt = bhi360_register_fifo_parse_callback(BHI360_SENSOR_ID_GRA, parse_gravity_data, (void*)&accuracy, &bhy);
    if (rslt != BHI360_OK)
    {
        bhi3_s_report_api_error(rslt, &bhy);
        close_interfaces(intf);
        return rslt;
    }

    rslt = bhi360_register_fifo_parse_callback(BHI360_SENSOR_ID_LACC, parse_linear_acc_data, (void*)&accuracy, &bhy);
    if (rslt != BHI360_OK)
    {
        bhi3_s_report_api_error(rslt, &bhy);
        close_interfaces(intf);
        return rslt;
    }

    rslt = bhi360_register_fifo_parse_callback(BHI360_SENSOR_ID_BARO, parse_pressure, NULL, &bhy);
    if (rslt != BHI360_OK)
    {
        bhi3_s_report_api_error(rslt, &bhy);
        close_interfaces(intf);
        return rslt;
    }

    rslt = bhi360_register_fifo_parse_callback(BHI360_SENSOR_ID_TEMP, parse_temperature, NULL, &bhy);
    if (rslt != BHI360_OK)
    {
        bhi3_s_report_api_error(rslt, &bhy);
        close_interfaces(intf);
        return rslt;
    }

    rslt = bhi360_register_fifo_parse_callback(BHI360_SENSOR_ID_HUM, parse_humidity, NULL, &bhy);
    if (rslt != BHI360_OK)
    {
        bhi3_s_report_api_error(rslt, &bhy);
        close_interfaces(intf);
        return rslt;
    }

    rslt = bhi360_get_and_process_fifo(work_buffer, WORK_BUFFER_SIZE, &bhy);
    if (rslt != BHI360_OK)
    {
        bhi3_s_report_api_error(rslt, &bhy);
        close_interfaces(intf);
        return rslt;
    }

    rslt = bhi360_update_virtual_sensor_list(&bhy);
    if (rslt != BHI360_OK)
    {
        bhi3_s_report_api_error(rslt, &bhy);
        close_interfaces(intf);
        return rslt;
    }

    sensor_conf_eular.sample_rate = 10.0f;
    sensor_conf_eular.latency = 0;
    rslt = bhi360_virtual_sensor_conf_param_set_cfg(BHI360_SENSOR_ID_ORI, &sensor_conf_eular, &bhy);
    bhi3_s_report_api_error(rslt, &bhy);
    printf("Enable %s at %.2fHz.\r\n", get_sensor_name(BHI360_SENSOR_ID_ORI), sensor_conf_eular.sample_rate);

    sensor_conf_acc.sample_rate = 10.0f;
    sensor_conf_acc.latency = 0;
    rslt = bhi360_virtual_sensor_conf_param_set_cfg(BHI360_SENSOR_ID_ACC, &sensor_conf_acc, &bhy);
    if (rslt == BHI360_OK)
    {
        rslt = bhi360_set_virt_sensor_range(BHI360_SENSOR_ID_ACC, BHI360_ACCEL_16G, &bhy);
    }
    bhi3_s_report_api_error(rslt, &bhy);
    printf("Enable %s at %.2fHz.\r\n", get_sensor_name(BHI360_SENSOR_ID_ACC), sensor_conf_acc.sample_rate);

    sensor_conf_gravity.sample_rate = 10.0f;
    sensor_conf_gravity.latency = 0;
    rslt = bhi360_virtual_sensor_conf_param_set_cfg(BHI360_SENSOR_ID_GRA, &sensor_conf_gravity, &bhy);
    bhi3_s_report_api_error(rslt, &bhy);
    printf("Enable %s at %.2fHz.\r\n", get_sensor_name(BHI360_SENSOR_ID_GRA), sensor_conf_gravity.sample_rate);

    sensor_conf_linear_acc.sample_rate = 10.0f;
    sensor_conf_linear_acc.latency = 0;
    rslt = bhi360_virtual_sensor_conf_param_set_cfg(BHI360_SENSOR_ID_LACC, &sensor_conf_linear_acc, &bhy);
    bhi3_s_report_api_error(rslt, &bhy);
    printf("Enable %s at %.2fHz.\r\n", get_sensor_name(BHI360_SENSOR_ID_LACC), sensor_conf_linear_acc.sample_rate);

    sensor_conf_pressure.sample_rate = 1.0f;
    sensor_conf_pressure.latency = 0;
    rslt = bhi360_virtual_sensor_conf_param_set_cfg(BHI360_SENSOR_ID_BARO, &sensor_conf_pressure, &bhy);
    bhi3_s_report_api_error(rslt, &bhy);
    printf("Enable %s at %.2fHz.\r\n", get_sensor_name(BHI360_SENSOR_ID_BARO), sensor_conf_pressure.sample_rate);

    sensor_conf_temperature.sample_rate = 1.0f;
    sensor_conf_temperature.latency = 0;
    rslt = bhi360_virtual_sensor_conf_param_set_cfg(BHI360_SENSOR_ID_TEMP, &sensor_conf_temperature, &bhy);
    bhi3_s_report_api_error(rslt, &bhy);
    printf("Enable %s at %.2fHz.\r\n", get_sensor_name(BHI360_SENSOR_ID_TEMP), sensor_conf_temperature.sample_rate);

    sensor_conf_humidity.sample_rate = 1.0f;
    sensor_conf_humidity.latency = 0;
    rslt = bhi360_virtual_sensor_conf_param_set_cfg(BHI360_SENSOR_ID_HUM, &sensor_conf_humidity, &bhy);
    bhi3_s_report_api_error(rslt, &bhy);
    printf("Enable %s at %.2fHz.\r\n", get_sensor_name(BHI360_SENSOR_ID_HUM), sensor_conf_humidity.sample_rate);

    return rslt;
}

static void bhi3_s_publish_latest_data(void)
{
    pthread_mutex_lock(&ctx.lock);
    ctx.latest_data = bhi3_s_datas;
    ctx.data_valid = true;
    ctx.last_error = BHI360_OK;
    pthread_mutex_unlock(&ctx.lock);
}

static void bhi3_s_report_api_error(int8_t rslt, struct bhi360_dev *dev)
{
    if (rslt != BHI360_OK)
    {
        printf("%s\r\n", get_api_error(rslt));
        if ((rslt == BHI360_E_IO) && (dev != NULL))
        {
            printf("%s\r\n", get_intf_error(dev->hif.intf_rslt));
            dev->hif.intf_rslt = BHI360_INTF_RET_SUCCESS;
        }
    }
}

static void bhi3_s_log_interrupt_ctrl(uint8_t hintr_ctrl)
{
    printf("Host interrupt control\r\n");
    printf("    Wake up FIFO %s.\r\n", (hintr_ctrl & BHI360_ICTL_DISABLE_FIFO_W) ? "disabled" : "enabled");
    printf("    Non wake up FIFO %s.\r\n", (hintr_ctrl & BHI360_ICTL_DISABLE_FIFO_NW) ? "disabled" : "enabled");
    printf("    Status FIFO %s.\r\n", (hintr_ctrl & BHI360_ICTL_DISABLE_STATUS_FIFO) ? "disabled" : "enabled");
    printf("    Debugging %s.\r\n", (hintr_ctrl & BHI360_ICTL_DISABLE_DEBUG) ? "disabled" : "enabled");
    printf("    Fault %s.\r\n", (hintr_ctrl & BHI360_ICTL_DISABLE_FAULT) ? "disabled" : "enabled");
    printf("    Interrupt is %s.\r\n", (hintr_ctrl & BHI360_ICTL_ACTIVE_LOW) ? "active low" : "active high");
    printf("    Interrupt is %s triggered.\r\n", (hintr_ctrl & BHI360_ICTL_EDGE) ? "pulse" : "level");
    printf("    Interrupt pin drive is %s.\r\n", (hintr_ctrl & BHI360_ICTL_OPEN_DRAIN) ? "open drain" : "push-pull");
}

static void bhi3_s_mark_error(int8_t rslt)
{
    pthread_mutex_lock(&ctx.lock);
    ctx.last_error = rslt;
    ctx.running = false;
    pthread_mutex_unlock(&ctx.lock);
}

static bool bhi3_s_should_continue(void)
{
    bool running;

    pthread_mutex_lock(&ctx.lock);
    running = ctx.running;
    pthread_mutex_unlock(&ctx.lock);

    return running;
}

static void bhi3_s_reset_local_data(void)
{
    memset(&bhi3_s_datas, 0, sizeof(bhi3_s_datas));
}

static int8_t upload_firmware(uint8_t boot_stat, struct bhi360_dev *dev)
{
    uint8_t sensor_error = 0;
    int8_t temp_rslt;
    int8_t rslt = BHI360_OK;

    printf("Loading firmware into RAM.\r\n");
    rslt = bhi360_upload_firmware_to_ram(bhi360_firmware_image, sizeof(bhi360_firmware_image), dev);
    bhi3_s_report_api_error(rslt, dev);

    temp_rslt = bhi360_get_error_value(&sensor_error, dev);
    if (sensor_error != 0)
    {
        printf("%s\r\n", get_sensor_error_text(sensor_error));
    }
    bhi3_s_report_api_error(temp_rslt, dev);

    if (rslt != BHI360_OK)
    {
        return rslt;
    }

    printf("Booting from RAM.\r\n");
    rslt = bhi360_boot_from_ram(dev);
    bhi3_s_report_api_error(rslt, dev);

    temp_rslt = bhi360_get_error_value(&sensor_error, dev);
    if (sensor_error != 0)
    {
        printf("%s\r\n", get_sensor_error_text(sensor_error));
    }
    bhi3_s_report_api_error(temp_rslt, dev);

    if (rslt != BHI360_OK)
    {
        return rslt;
    }

    (void)boot_stat;
    return BHI360_OK;
}

static void parse_euler_data(const struct bhi360_fifo_parse_data_info *callback_info, void *callback_ref)
{
    (void)callback_ref;
    struct bhi360_event_data_orientation data;
    uint8_t *accuracy = (uint8_t *)callback_ref;

    if (!callback_info || (callback_info->data_size != 7U))
    {
        return;
    }

    bhi360_event_data_parse_orientation(callback_info->data_ptr, &data);
    bhi3_s_datas.heading = data.heading * 360.0f / 32768.0f;
    bhi3_s_datas.pitch = data.pitch * 360.0f / 32768.0f;
    bhi3_s_datas.roll = data.roll * 360.0f / 32768.0f;

    if (accuracy != NULL)
    {
        bhi3_s_datas.orientation_accuracy = *accuracy;
    }
}

static void parse_acc_data(const struct bhi360_fifo_parse_data_info *callback_info, void *callback_ref)
{
    struct bhi360_event_data_xyz data;
    uint8_t *accuracy = (uint8_t *)callback_ref;
    float scaling_factor = SCALING_FACTOR_INVALID_LIMIT;

    if (!callback_info)
    {
        printf("Null reference\r\n");
        return;
    }
    if (callback_info->data_size != 7U)
    {
        return;
    }

    bhi360_event_data_parse_xyz(callback_info->data_ptr, &data);
    scaling_factor = get_sensor_dynamic_range_scaling(callback_info->sensor_id, (float)BHI360_ACCEL_16G);
    bhi3_s_datas.acc_x = data.x * scaling_factor;
    bhi3_s_datas.acc_y = data.y * scaling_factor;
    bhi3_s_datas.acc_z = data.z * scaling_factor;

    if (accuracy != NULL)
    {
        bhi3_s_datas.acc_accuracy = *accuracy;
    }
}

static void parse_gravity_data(const struct bhi360_fifo_parse_data_info *callback_info, void *callback_ref)
{
    struct bhi360_event_data_xyz data;
    uint8_t *accuracy = (uint8_t *)callback_ref;
    float scaling_factor = SCALING_FACTOR_INVALID_LIMIT;

    if (!callback_info)
    {
        printf("Null reference\r\n");
        return;
    }
    if (callback_info->data_size != 7U)
    {
        return;
    }

    bhi360_event_data_parse_xyz(callback_info->data_ptr, &data);
    scaling_factor = (float)BHI360_ACCEL_8G / 32768.0f;
    bhi3_s_datas.gravity_x = data.x * scaling_factor;
    bhi3_s_datas.gravity_y = data.y * scaling_factor;
    bhi3_s_datas.gravity_z = data.z * scaling_factor;

    if (accuracy != NULL)
    {
        bhi3_s_datas.gravity_accuracy = *accuracy;
    }
}

static void parse_linear_acc_data(const struct bhi360_fifo_parse_data_info *callback_info, void *callback_ref)
{
    struct bhi360_event_data_xyz data;
    uint8_t *accuracy = (uint8_t *)callback_ref;
    float scaling_factor = SCALING_FACTOR_INVALID_LIMIT;

    if (!callback_info)
    {
        printf("Null reference\r\n");
        return;
    }
    if (callback_info->data_size != 7U)
    {
        return;
    }

    bhi360_event_data_parse_xyz(callback_info->data_ptr, &data);
    scaling_factor = (float)BHI360_ACCEL_8G / 32768.0f;
    bhi3_s_datas.linear_acc_x = data.x * scaling_factor;
    bhi3_s_datas.linear_acc_y = data.y * scaling_factor;
    bhi3_s_datas.linear_acc_z = data.z * scaling_factor;

    if (accuracy != NULL)
    {
        bhi3_s_datas.linear_acc_accuracy = *accuracy;
    }
}

static void parse_pressure(const struct bhi360_fifo_parse_data_info *callback_info, void *callback_ref)
{
    (void)callback_ref;
    bhi360_float pressure;

    if (!callback_info)
    {
        printf("Null reference\r\n");
        return;
    }
    if (callback_info->data_size != 4U)
    {
        return;
    }

    bhi360_parse_pressure(callback_info->data_ptr, &pressure);
    bhi3_s_datas.pressure = pressure / 100.0f;
}

static void parse_temperature(const struct bhi360_fifo_parse_data_info *callback_info, void *callback_ref)
{
    (void)callback_ref;
    bhi360_float temperature;

    if (!callback_info)
    {
        printf("Null reference\r\n");
        return;
    }
    if (callback_info->data_size != 3U)
    {
        return;
    }

    bhi360_parse_temperature_celsius(callback_info->data_ptr, &temperature);
    bhi3_s_datas.temperature = temperature;
}

static void parse_humidity(const struct bhi360_fifo_parse_data_info *callback_info, void *callback_ref)
{
    (void)callback_ref;
    bhi360_float humidity;

    if (!callback_info)
    {
        printf("Null reference\r\n");
        return;
    }
    if (callback_info->data_size != 2U)
    {
        return;
    }

    bhi360_parse_humidity(callback_info->data_ptr, &humidity);
    bhi3_s_datas.humidity = humidity;
}

static void parse_meta_event(const struct bhi360_fifo_parse_data_info *callback_info, void *callback_ref)
{
    uint8_t meta_event_type;
    uint8_t byte1;
    uint8_t byte2;
    uint8_t *accuracy = (uint8_t *)callback_ref;
    char *event_text;

    if (!callback_info)
    {
        return;
    }

    meta_event_type = callback_info->data_ptr[0];
    byte1 = callback_info->data_ptr[1];
    byte2 = callback_info->data_ptr[2];

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
        case BHI360_META_EVENT_SENSOR_STATUS:
            printf("%s Accuracy for sensor id %u (%s) changed to %u (%s)\r\n", event_text, byte1, get_sensor_name(byte1), byte2, get_sensor_name(byte2));
            if (accuracy != NULL)
            {
                *accuracy = byte2;
            }
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
        case BHI360_META_EVENT_RESET:
            printf("%s Reset event\r\n", event_text);
            break;
        case BHI360_META_EVENT_INTERNAL_STATUS:
            /* Ignore repetitive internal status event to avoid noisy logging. */
            break;
        default:
            printf("%s Unknown meta event with id: %u\r\n", event_text, meta_event_type);
            break;
    }
}

#ifndef NOUSE_MAIN
int main(void)
{
    bhi3_s_init();
    return 0;
}
#endif

#else

#ifndef NOUSE_MAIN
int main(void)
{
    return 0;
}
#endif

#endif
