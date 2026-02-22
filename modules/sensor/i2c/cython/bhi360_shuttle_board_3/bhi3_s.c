#include "bhi3_s.h"

#ifdef USE_BHI3_S

//#include "bhi360/Bosch_Shuttle3_BHI360_BMM350C_BME688_IAQ.fw.h"
#include "bhi360/Bosch_Shuttle3_BHI360_BMM350C_BMP580_BME688.fw.h"

#include <errno.h>
#include <math.h>
#include <pthread.h>
#include <strings.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#define WORK_BUFFER_SIZE 2048
#define SCALING_FACTOR_INVALID_LIMIT -1.0f
#define INTERRUPT_WAIT_TIMEOUT_MS 100U
#define BHI360_META_EVENT_INTERNAL_STATUS 20U
#define BHI3_SENSOR_PRIMARY_RATE_HZ 50.0f
#define BHI3_SENSOR_FALLBACK_RATE_HZ 50.0f
#define BHI3_WINDOW_NS UINT64_C(1000000000)
#define PRESSURE_EMA_ALPHA_50HZ 0.02f /* tau=0.88s at 50Hz */
#define HEADING_EMA_ALPHA_50HZ 0.0487705755f /* tau=0.4s at 50Hz */
#define TILT_EMA_ALPHA_50HZ 0.0487705755f /* tau=0.4s at 50Hz */
#define BHI3_RAW_PATH_MAX 512
#define NS_PER_SEC UINT64_C(1000000000)
#define DEG_TO_RAD 0.01745329251994329577f
#define RAD_TO_DEG 57.2957795130823208768f
/* Motion detection tuned for BHI 25-50Hz stream */
#define BHI3_MOTION_LACC_ON_G 0.080f
#define BHI3_MOTION_LACC_OFF_G 0.045f
#define BHI3_MOTION_GYRO_ON_RAD_S 0.400f
#define BHI3_MOTION_GYRO_OFF_RAD_S 0.200f
#define BHI3_MOTION_ON_COUNT 2U
#define BHI3_MOTION_OFF_COUNT 6U
#define BHI3_MOTION_SMOOTH_WINDOW_SAMPLES 50U

static void parse_euler_data(const struct bhi360_fifo_parse_data_info *callback_info, void *callback_ref);
static void parse_acc_data(const struct bhi360_fifo_parse_data_info *callback_info, void *callback_ref);
static void parse_gravity_data(const struct bhi360_fifo_parse_data_info *callback_info, void *callback_ref);
static void parse_linear_acc_data(const struct bhi360_fifo_parse_data_info *callback_info, void *callback_ref);
static void parse_gyro_data(const struct bhi360_fifo_parse_data_info *callback_info, void *callback_ref);
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
static float wrap_deg_360(float angle_deg);
static float wrap_deg_180(float angle_deg);
static void heading_filter_reset(void);
static float heading_filter_update(float raw_heading_deg);
static void tilt_filter_reset(void);
static float tilt_filter_update(float raw_angle_deg,
                                bool *initialized,
                                float *ema_sin,
                                float *ema_cos,
                                float *last_angle_deg);
static void motion_detector_reset(void);
static void motion_detector_update(void);
static uint64_t bhi3_s_time_ns(clockid_t clock_id);
static uint64_t bhi3_s_sensor_timestamp(const struct bhi360_fifo_parse_data_info *callback_info);
static uint64_t bhi3_s_sample_time_ns(const struct bhi360_fifo_parse_data_info *callback_info);
static int8_t bhi3_s_raw_log_open(const char *requested_path);
static void bhi3_s_raw_log_write_row(void);
static void bhi3_s_raw_log_close(void);
static int8_t bhi3_s_set_sensor_rate_with_fallback(uint8_t sensor_id,
                                                   struct bhi360_virtual_sensor_conf_param_conf *sensor_conf);

typedef struct bhi3_s_acc_window_state
{
    bool initialized;
    uint64_t window_start_ns;
    float sum_x;
    float sum_y;
    float sum_z;
    float sum_norm_sq;
    uint32_t count;
} bhi3_s_acc_window_state;

typedef struct bhi3_s_gyro_window_state
{
    bool initialized;
    uint64_t window_start_ns;
    uint64_t prev_sample_ns;
    float integral_x;
    float integral_y;
    float integral_z;
} bhi3_s_gyro_window_state;

enum bhi360_intf intf;
static struct bhi360_dev bhy;
static uint8_t work_buffer[WORK_BUFFER_SIZE];
static struct bhi3_s_data bhi3_s_datas;
static float last_heading = 0.0f;
static bool heading_ema_initialized = false;
static float heading_ema_sin = 0.0f;
static float heading_ema_cos = 0.0f;
static float last_pitch = 0.0f;
static bool pitch_ema_initialized = false;
static float pitch_ema_sin = 0.0f;
static float pitch_ema_cos = 0.0f;
static float last_roll = 0.0f;
static bool roll_ema_initialized = false;
static float roll_ema_sin = 0.0f;
static float roll_ema_cos = 0.0f;
static bool pressure_ema_initialized = false;
static float pressure_ema_hpa = 0.0f;
static bhi3_s_acc_window_state acc_window = { 0 };
static bhi3_s_gyro_window_state gyro_window = { 0 };
static uint8_t orientation_accuracy_state = 0U;
static uint8_t acc_accuracy_state = 0U;
static uint8_t gravity_accuracy_state = 0U;
static uint8_t linear_acc_accuracy_state = 0U;
static uint8_t gyro_accuracy_state = 0U;
static uint64_t ts_ori_sensor_ns = 0U;
static uint64_t ts_lacc_sensor_ns = 0U;
static uint64_t ts_gra_sensor_ns = 0U;
static uint64_t ts_gyro_sensor_ns = 0U;
static uint64_t ts_baro_sensor_ns = 0U;
static bool motion_state_moving = false;
static uint8_t motion_on_streak = 0U;
static uint8_t motion_off_streak = 0U;
static uint8_t motion_smooth_window[BHI3_MOTION_SMOOTH_WINDOW_SAMPLES] = { 0 };
static uint32_t motion_smooth_index = 0U;
static uint32_t motion_smooth_count = 0U;
static uint32_t motion_smooth_sum = 0U;

typedef struct bhi3_s_raw_log_context
{
    bool enabled;
    FILE *fp;
    uint64_t seq;
    uint64_t last_flush_mono_ns;
    char path[BHI3_RAW_PATH_MAX];
} bhi3_s_raw_log_context;

static bhi3_s_raw_log_context raw_log_ctx = {
    .enabled = false,
    .fp = NULL,
    .seq = 0U,
    .last_flush_mono_ns = 0U,
};
static pthread_mutex_t raw_log_lock = PTHREAD_MUTEX_INITIALIZER;

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

int8_t bhi3_s_raw_log_start(const char *path)
{
    return bhi3_s_raw_log_open(path);
}

void bhi3_s_raw_log_stop(void)
{
    bhi3_s_raw_log_close();
}

int8_t bhi3_s_raw_log_start_and_stop(const char *path)
{
    if (bhi3_s_raw_log_is_enabled())
    {
        bhi3_s_raw_log_stop();
        return BHI360_OK;
    }

    return bhi3_s_raw_log_start(path);
}

bool bhi3_s_raw_log_is_enabled(void)
{
    bool enabled;

    pthread_mutex_lock(&raw_log_lock);
    enabled = raw_log_ctx.enabled && (raw_log_ctx.fp != NULL);
    pthread_mutex_unlock(&raw_log_lock);

    return enabled;
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
    bhi3_s_raw_log_close();

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

    bhi3_s_raw_log_close();
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
    struct bhi360_virtual_sensor_conf_param_conf sensor_conf_eular = { 0 };
    struct bhi360_virtual_sensor_conf_param_conf sensor_conf_acc = { 0 };
    struct bhi360_virtual_sensor_conf_param_conf sensor_conf_gyro = { 0 };
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

    rslt = bhi360_register_fifo_parse_callback(BHI360_SYS_ID_META_EVENT, parse_meta_event, NULL, &bhy);
    if (rslt != BHI360_OK)
    {
        bhi3_s_report_api_error(rslt, &bhy);
        close_interfaces(intf);
        return rslt;
    }

    rslt = bhi360_register_fifo_parse_callback(BHI360_SYS_ID_META_EVENT_WU, parse_meta_event, NULL, &bhy);
    if (rslt != BHI360_OK)
    {
        bhi3_s_report_api_error(rslt, &bhy);
        close_interfaces(intf);
        return rslt;
    }

    rslt = bhi360_register_fifo_parse_callback(BHI360_SENSOR_ID_ORI, parse_euler_data, NULL, &bhy);
    if (rslt != BHI360_OK)
    {
        bhi3_s_report_api_error(rslt, &bhy);
        close_interfaces(intf);
        return rslt;
    }

    rslt = bhi360_register_fifo_parse_callback(BHI360_SENSOR_ID_ACC, parse_acc_data, NULL, &bhy);
    if (rslt != BHI360_OK)
    {
        bhi3_s_report_api_error(rslt, &bhy);
        close_interfaces(intf);
        return rslt;
    }

    rslt = bhi360_register_fifo_parse_callback(BHI360_SENSOR_ID_GRA, parse_gravity_data, NULL, &bhy);
    if (rslt != BHI360_OK)
    {
        bhi3_s_report_api_error(rslt, &bhy);
        close_interfaces(intf);
        return rslt;
    }

    rslt = bhi360_register_fifo_parse_callback(BHI360_SENSOR_ID_LACC, parse_linear_acc_data, NULL, &bhy);
    if (rslt != BHI360_OK)
    {
        bhi3_s_report_api_error(rslt, &bhy);
        close_interfaces(intf);
        return rslt;
    }

    rslt = bhi360_register_fifo_parse_callback(BHI360_SENSOR_ID_GYRO, parse_gyro_data, NULL, &bhy);
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

    rslt = bhi3_s_set_sensor_rate_with_fallback(BHI360_SENSOR_ID_ORI, &sensor_conf_eular);
    if (rslt != BHI360_OK)
    {
        close_interfaces(intf);
        return rslt;
    }

    rslt = bhi3_s_set_sensor_rate_with_fallback(BHI360_SENSOR_ID_ACC, &sensor_conf_acc);
    if (rslt != BHI360_OK)
    {
        close_interfaces(intf);
        return rslt;
    }
    rslt = bhi360_set_virt_sensor_range(BHI360_SENSOR_ID_ACC, BHI360_ACCEL_16G, &bhy);
    if (rslt != BHI360_OK)
    {
        bhi3_s_report_api_error(rslt, &bhy);
        close_interfaces(intf);
        return rslt;
    }

    rslt = bhi3_s_set_sensor_rate_with_fallback(BHI360_SENSOR_ID_GRA, &sensor_conf_gravity);
    if (rslt != BHI360_OK)
    {
        close_interfaces(intf);
        return rslt;
    }

    rslt = bhi3_s_set_sensor_rate_with_fallback(BHI360_SENSOR_ID_LACC, &sensor_conf_linear_acc);
    if (rslt != BHI360_OK)
    {
        close_interfaces(intf);
        return rslt;
    }

    rslt = bhi3_s_set_sensor_rate_with_fallback(BHI360_SENSOR_ID_GYRO, &sensor_conf_gyro);
    if (rslt != BHI360_OK)
    {
        close_interfaces(intf);
        return rslt;
    }
    rslt = bhi360_set_virt_sensor_range(BHI360_SENSOR_ID_GYRO, BHI360_GYRO_2000DPS, &bhy);
    if (rslt != BHI360_OK)
    {
        bhi3_s_report_api_error(rslt, &bhy);
        close_interfaces(intf);
        return rslt;
    }

    rslt = bhi3_s_set_sensor_rate_with_fallback(BHI360_SENSOR_ID_BARO, &sensor_conf_pressure);
    if (rslt != BHI360_OK)
    {
        close_interfaces(intf);
        return rslt;
    }

    sensor_conf_temperature.sample_rate = 1.0f;
    sensor_conf_temperature.latency = 0;
    rslt = bhi360_virtual_sensor_conf_param_set_cfg(BHI360_SENSOR_ID_TEMP, &sensor_conf_temperature, &bhy);
    if (rslt != BHI360_OK)
    {
        bhi3_s_report_api_error(rslt, &bhy);
        close_interfaces(intf);
        return rslt;
    }
    bhi3_s_report_api_error(rslt, &bhy);
    printf("Enable %s at %.2fHz.\r\n", get_sensor_name(BHI360_SENSOR_ID_TEMP), sensor_conf_temperature.sample_rate);

    sensor_conf_humidity.sample_rate = 1.0f;
    sensor_conf_humidity.latency = 0;
    rslt = bhi360_virtual_sensor_conf_param_set_cfg(BHI360_SENSOR_ID_HUM, &sensor_conf_humidity, &bhy);
    if (rslt != BHI360_OK)
    {
        bhi3_s_report_api_error(rslt, &bhy);
        close_interfaces(intf);
        return rslt;
    }
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

static float wrap_deg_360(float angle_deg)
{
    float wrapped = fmodf(angle_deg, 360.0f);

    if (wrapped < 0.0f)
    {
        wrapped += 360.0f;
    }

    return wrapped;
}

static float wrap_deg_180(float angle_deg)
{
    float wrapped = fmodf(angle_deg + 180.0f, 360.0f);

    if (wrapped < 0.0f)
    {
        wrapped += 360.0f;
    }

    return wrapped - 180.0f;
}

static void heading_filter_reset(void)
{
    heading_ema_initialized = false;
    heading_ema_sin = 0.0f;
    heading_ema_cos = 0.0f;
    last_heading = 0.0f;
}

static float heading_filter_update(float raw_heading_deg)
{
    float normalized = wrap_deg_360(raw_heading_deg);
    float raw_rad = normalized * DEG_TO_RAD;
    float sample_sin = sinf(raw_rad);
    float sample_cos = cosf(raw_rad);

    if (!heading_ema_initialized)
    {
        heading_ema_sin = sample_sin;
        heading_ema_cos = sample_cos;
        heading_ema_initialized = true;
    }
    else
    {
        heading_ema_sin += HEADING_EMA_ALPHA_50HZ * (sample_sin - heading_ema_sin);
        heading_ema_cos += HEADING_EMA_ALPHA_50HZ * (sample_cos - heading_ema_cos);
    }

    if ((fabsf(heading_ema_sin) < 1e-6f) && (fabsf(heading_ema_cos) < 1e-6f))
    {
        return last_heading;
    }

    last_heading = wrap_deg_360(atan2f(heading_ema_sin, heading_ema_cos) * RAD_TO_DEG);
    return last_heading;
}

static void tilt_filter_reset(void)
{
    pitch_ema_initialized = false;
    pitch_ema_sin = 0.0f;
    pitch_ema_cos = 0.0f;
    last_pitch = 0.0f;

    roll_ema_initialized = false;
    roll_ema_sin = 0.0f;
    roll_ema_cos = 0.0f;
    last_roll = 0.0f;
}

static float tilt_filter_update(float raw_angle_deg,
                                bool *initialized,
                                float *ema_sin,
                                float *ema_cos,
                                float *last_angle_deg)
{
    float normalized = wrap_deg_180(raw_angle_deg);
    float raw_rad = normalized * DEG_TO_RAD;
    float sample_sin = sinf(raw_rad);
    float sample_cos = cosf(raw_rad);

    if (!(*initialized))
    {
        *ema_sin = sample_sin;
        *ema_cos = sample_cos;
        *initialized = true;
    }
    else
    {
        *ema_sin += TILT_EMA_ALPHA_50HZ * (sample_sin - *ema_sin);
        *ema_cos += TILT_EMA_ALPHA_50HZ * (sample_cos - *ema_cos);
    }

    if ((fabsf(*ema_sin) < 1e-6f) && (fabsf(*ema_cos) < 1e-6f))
    {
        return *last_angle_deg;
    }

    *last_angle_deg = wrap_deg_180(atan2f(*ema_sin, *ema_cos) * RAD_TO_DEG);
    return *last_angle_deg;
}

static void motion_detector_reset(void)
{
    motion_state_moving = false;
    motion_on_streak = 0U;
    motion_off_streak = 0U;
    memset(motion_smooth_window, 0, sizeof(motion_smooth_window));
    motion_smooth_index = 0U;
    motion_smooth_count = 0U;
    motion_smooth_sum = 0U;
    bhi3_s_datas.moving = 0U;
}

static void motion_detector_update(void)
{
    float linear_acc_norm;
    float gyro_norm;
    bool detect_on;
    bool detect_off;
    uint8_t motion_sample;

    linear_acc_norm = sqrtf(
        (bhi3_s_datas.linear_acc_x * bhi3_s_datas.linear_acc_x) +
        (bhi3_s_datas.linear_acc_y * bhi3_s_datas.linear_acc_y) +
        (bhi3_s_datas.linear_acc_z * bhi3_s_datas.linear_acc_z));
    gyro_norm = sqrtf(
        (bhi3_s_datas.gyro_x_raw * bhi3_s_datas.gyro_x_raw) +
        (bhi3_s_datas.gyro_y_raw * bhi3_s_datas.gyro_y_raw) +
        (bhi3_s_datas.gyro_z_raw * bhi3_s_datas.gyro_z_raw));

    detect_on = (linear_acc_norm >= BHI3_MOTION_LACC_ON_G) ||
                (gyro_norm >= BHI3_MOTION_GYRO_ON_RAD_S);
    detect_off = (linear_acc_norm <= BHI3_MOTION_LACC_OFF_G) &&
                 (gyro_norm <= BHI3_MOTION_GYRO_OFF_RAD_S);

    if (motion_state_moving)
    {
        motion_on_streak = 0U;
        if (detect_off)
        {
            if (motion_off_streak < BHI3_MOTION_OFF_COUNT)
            {
                motion_off_streak++;
            }
            if (motion_off_streak >= BHI3_MOTION_OFF_COUNT)
            {
                motion_state_moving = false;
            }
        }
        else
        {
            motion_off_streak = 0U;
        }
    }
    else
    {
        motion_off_streak = 0U;
        if (detect_on)
        {
            if (motion_on_streak < BHI3_MOTION_ON_COUNT)
            {
                motion_on_streak++;
            }
            if (motion_on_streak >= BHI3_MOTION_ON_COUNT)
            {
                motion_state_moving = true;
            }
        }
        else
        {
            motion_on_streak = 0U;
        }
    }

    motion_sample = motion_state_moving ? 1U : 0U;
    if (motion_smooth_count < BHI3_MOTION_SMOOTH_WINDOW_SAMPLES)
    {
        motion_smooth_window[motion_smooth_index] = motion_sample;
        motion_smooth_sum += motion_sample;
        motion_smooth_count++;
    }
    else
    {
        motion_smooth_sum -= motion_smooth_window[motion_smooth_index];
        motion_smooth_window[motion_smooth_index] = motion_sample;
        motion_smooth_sum += motion_sample;
    }

    motion_smooth_index = (motion_smooth_index + 1U) % BHI3_MOTION_SMOOTH_WINDOW_SAMPLES;
    bhi3_s_datas.moving = ((motion_smooth_sum * 2U) >= motion_smooth_count) ? 1U : 0U;
}

static uint64_t bhi3_s_time_ns(clockid_t clock_id)
{
    struct timespec ts;

    if (clock_gettime(clock_id, &ts) != 0)
    {
        return 0U;
    }

    return ((uint64_t)ts.tv_sec * NS_PER_SEC) + (uint64_t)ts.tv_nsec;
}

static uint64_t bhi3_s_sensor_timestamp(const struct bhi360_fifo_parse_data_info *callback_info)
{
    if ((callback_info == NULL) || (callback_info->time_stamp == NULL))
    {
        return 0U;
    }

    return (*callback_info->time_stamp) * UINT64_C(15625);
}

static uint64_t bhi3_s_sample_time_ns(const struct bhi360_fifo_parse_data_info *callback_info)
{
    uint64_t ts_ns = bhi3_s_sensor_timestamp(callback_info);

    if (ts_ns != 0U)
    {
        return ts_ns;
    }

    return bhi3_s_time_ns(CLOCK_MONOTONIC);
}


static int8_t bhi3_s_raw_log_open(const char *requested_path)
{
    int path_len;
    int written;
    int err_no;
    time_t now_sec;
    struct tm now_tm;
    int8_t rslt = BHI360_OK;

    pthread_mutex_lock(&raw_log_lock);

    if (raw_log_ctx.fp != NULL)
    {
        fflush(raw_log_ctx.fp);
        fclose(raw_log_ctx.fp);
    }

    raw_log_ctx.fp = NULL;
    raw_log_ctx.enabled = true;
    raw_log_ctx.seq = 0U;
    raw_log_ctx.last_flush_mono_ns = 0U;
    raw_log_ctx.path[0] = '\0';

    if ((requested_path != NULL) && (requested_path[0] != '\0'))
    {
        written = snprintf(raw_log_ctx.path, sizeof(raw_log_ctx.path), "%s", requested_path);
        if ((written <= 0) || ((size_t)written >= sizeof(raw_log_ctx.path)))
        {
            fprintf(stderr,
                    "[BHI3] Invalid raw log path length: %d (max %zu)\n",
                    written,
                    sizeof(raw_log_ctx.path) - 1U);
            rslt = BHI360_E_NULL_PTR;
            goto raw_log_open_exit;
        }
    }
    else
    {
        if ((mkdir("log", 0755) != 0) && (errno != EEXIST))
        {
            err_no = errno;
            fprintf(stderr,
                    "[BHI3] Failed to create log directory 'log' (errno=%d: %s)\n",
                    err_no,
                    strerror(err_no));
        }
        if ((mkdir("log/bhi3", 0755) != 0) && (errno != EEXIST))
        {
            err_no = errno;
            fprintf(stderr,
                    "[BHI3] Failed to create log directory 'log/bhi3' (errno=%d: %s)\n",
                    err_no,
                    strerror(err_no));
        }

        now_sec = (time_t)(bhi3_s_time_ns(CLOCK_REALTIME) / NS_PER_SEC);
        if ((now_sec == (time_t)0) || (localtime_r(&now_sec, &now_tm) == NULL))
        {
            written = snprintf(raw_log_ctx.path, sizeof(raw_log_ctx.path), "log/bhi3/bhi3_raw_%ld.csv", (long)time(NULL));
        }
        else
        {
            written = snprintf(raw_log_ctx.path,
                               sizeof(raw_log_ctx.path),
                               "log/bhi3/bhi3_raw_%04d-%02d-%02d_%02d-%02d-%02d.csv",
                               now_tm.tm_year + 1900,
                               now_tm.tm_mon + 1,
                               now_tm.tm_mday,
                               now_tm.tm_hour,
                               now_tm.tm_min,
                               now_tm.tm_sec);
        }

        if ((written <= 0) || ((size_t)written >= sizeof(raw_log_ctx.path)))
        {
            fprintf(stderr, "[BHI3] Failed to generate default raw log path.\n");
            rslt = BHI360_E_NULL_PTR;
            goto raw_log_open_exit;
        }
    }

    raw_log_ctx.fp = fopen(raw_log_ctx.path, "w");
    if (raw_log_ctx.fp == NULL)
    {
        err_no = errno;
        fprintf(stderr,
                "[BHI3] Cannot open raw log '%s' (errno=%d: %s)\n",
                raw_log_ctx.path,
                err_no,
                strerror(err_no));
        rslt = BHI360_E_IO;
        goto raw_log_open_exit;
    }

    setvbuf(raw_log_ctx.fp, NULL, _IOLBF, 0);

    path_len = fprintf(raw_log_ctx.fp,
                       "seq,host_unix_ns,host_mono_ns,baro_sensor_ts_ns,ori_sensor_ts_ns,lacc_sensor_ts_ns,"
                       "gra_sensor_ts_ns,gyro_sensor_ts_ns,heading_filtered_deg,heading_raw_deg,"
                       "pitch_filtered_deg,pitch_raw_deg,roll_filtered_deg,roll_raw_deg,orientation_accuracy,"
                       "acc_x_g,acc_y_g,acc_z_g,acc_accuracy,acc_x_raw_g,acc_y_raw_g,"
                       "acc_z_raw_g,acc_rms_norm_g,linear_acc_x_g,linear_acc_y_g,linear_acc_z_g,"
                       "linear_acc_accuracy,moving,gravity_x_g,gravity_y_g,gravity_z_g,gravity_accuracy,gyro_x_rad_s,"
                       "gyro_y_rad_s,gyro_z_rad_s,gyro_integral_x_rad,gyro_integral_y_rad,gyro_integral_z_rad,"
                       "gyro_accuracy,baro_raw_hpa\n");
    if (path_len < 0)
    {
        fprintf(stderr, "[BHI3] Failed to write raw log CSV header.\n");
        fclose(raw_log_ctx.fp);
        raw_log_ctx.fp = NULL;
        rslt = BHI360_E_IO;
        goto raw_log_open_exit;
    }

    fflush(raw_log_ctx.fp);
    raw_log_ctx.last_flush_mono_ns = bhi3_s_time_ns(CLOCK_MONOTONIC);

raw_log_open_exit:
    if (rslt != BHI360_OK)
    {
        raw_log_ctx.enabled = false;
        raw_log_ctx.seq = 0U;
        raw_log_ctx.last_flush_mono_ns = 0U;
        raw_log_ctx.path[0] = '\0';
        if (raw_log_ctx.fp != NULL)
        {
            fclose(raw_log_ctx.fp);
            raw_log_ctx.fp = NULL;
        }
    }

    pthread_mutex_unlock(&raw_log_lock);

    return rslt;
}

static void bhi3_s_raw_log_write_row(void)
{
    uint64_t host_unix_ns;
    uint64_t host_mono_ns;
    int ret;

    pthread_mutex_lock(&raw_log_lock);

    if (!raw_log_ctx.enabled || (raw_log_ctx.fp == NULL))
    {
        pthread_mutex_unlock(&raw_log_lock);
        return;
    }

    host_unix_ns = bhi3_s_time_ns(CLOCK_REALTIME);
    host_mono_ns = bhi3_s_time_ns(CLOCK_MONOTONIC);

    ret = fprintf(raw_log_ctx.fp,
                  "%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64
                  ",%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%u,%.6f,%.6f,%.6f,%u,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%u,%u,%.6f,%.6f,"
                  "%.6f,%u,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%u,%.6f\n",
                  raw_log_ctx.seq++,
                  host_unix_ns,
                  host_mono_ns,
                  ts_baro_sensor_ns,
                  ts_ori_sensor_ns,
                  ts_lacc_sensor_ns,
                  ts_gra_sensor_ns,
                  ts_gyro_sensor_ns,
                  bhi3_s_datas.heading,
                  bhi3_s_datas.heading_raw,
                  bhi3_s_datas.pitch,
                  bhi3_s_datas.pitch_raw,
                  bhi3_s_datas.roll,
                  bhi3_s_datas.roll_raw,
                  (unsigned int)bhi3_s_datas.orientation_accuracy,
                  bhi3_s_datas.acc_x,
                  bhi3_s_datas.acc_y,
                  bhi3_s_datas.acc_z,
                  (unsigned int)bhi3_s_datas.acc_accuracy,
                  bhi3_s_datas.acc_x_raw,
                  bhi3_s_datas.acc_y_raw,
                  bhi3_s_datas.acc_z_raw,
                  bhi3_s_datas.acc_rms_norm,
                  bhi3_s_datas.linear_acc_x,
                  bhi3_s_datas.linear_acc_y,
                  bhi3_s_datas.linear_acc_z,
                  (unsigned int)bhi3_s_datas.linear_acc_accuracy,
                  (unsigned int)bhi3_s_datas.moving,
                  bhi3_s_datas.gravity_x,
                  bhi3_s_datas.gravity_y,
                  bhi3_s_datas.gravity_z,
                  (unsigned int)bhi3_s_datas.gravity_accuracy,
                  bhi3_s_datas.gyro_x_raw,
                  bhi3_s_datas.gyro_y_raw,
                  bhi3_s_datas.gyro_z_raw,
                  bhi3_s_datas.gyro_x,
                  bhi3_s_datas.gyro_y,
                  bhi3_s_datas.gyro_z,
                  (unsigned int)bhi3_s_datas.gyro_accuracy,
                  bhi3_s_datas.pressure_raw);
    if (ret < 0)
    {
        fprintf(stderr, "[BHI3] Failed to write raw log row. Disabling raw log.\n");
        if (raw_log_ctx.fp != NULL)
        {
            fflush(raw_log_ctx.fp);
            fclose(raw_log_ctx.fp);
            raw_log_ctx.fp = NULL;
        }
        raw_log_ctx.enabled = false;
        raw_log_ctx.seq = 0U;
        raw_log_ctx.last_flush_mono_ns = 0U;
        raw_log_ctx.path[0] = '\0';
        pthread_mutex_unlock(&raw_log_lock);
        return;
    }

    if ((raw_log_ctx.last_flush_mono_ns == 0U) || ((host_mono_ns - raw_log_ctx.last_flush_mono_ns) >= NS_PER_SEC))
    {
        fflush(raw_log_ctx.fp);
        raw_log_ctx.last_flush_mono_ns = host_mono_ns;
    }

    pthread_mutex_unlock(&raw_log_lock);
}

static void bhi3_s_raw_log_close(void)
{
    pthread_mutex_lock(&raw_log_lock);

    if (raw_log_ctx.fp != NULL)
    {
        fflush(raw_log_ctx.fp);
        fclose(raw_log_ctx.fp);
        raw_log_ctx.fp = NULL;
    }

    raw_log_ctx.enabled = false;
    raw_log_ctx.seq = 0U;
    raw_log_ctx.last_flush_mono_ns = 0U;
    raw_log_ctx.path[0] = '\0';

    pthread_mutex_unlock(&raw_log_lock);
}

static int8_t bhi3_s_set_sensor_rate_with_fallback(uint8_t sensor_id,
                                                   struct bhi360_virtual_sensor_conf_param_conf *sensor_conf)
{
    int8_t rslt;

    if (sensor_conf == NULL)
    {
        return BHI360_E_NULL_PTR;
    }

    sensor_conf->latency = 0;
    sensor_conf->sample_rate = BHI3_SENSOR_PRIMARY_RATE_HZ;
    rslt = bhi360_virtual_sensor_conf_param_set_cfg(sensor_id, sensor_conf, &bhy);
    if (rslt == BHI360_OK)
    {
        printf("Enable %s at %.2fHz.\r\n", get_sensor_name(sensor_id), sensor_conf->sample_rate);
        return rslt;
    }

    bhi3_s_report_api_error(rslt, &bhy);
    fprintf(stderr,
            "[BHI3] Failed to set %s at %.2fHz. Retrying %.2fHz.\n",
            get_sensor_name(sensor_id),
            (double)BHI3_SENSOR_PRIMARY_RATE_HZ,
            (double)BHI3_SENSOR_FALLBACK_RATE_HZ);

    sensor_conf->sample_rate = BHI3_SENSOR_FALLBACK_RATE_HZ;
    rslt = bhi360_virtual_sensor_conf_param_set_cfg(sensor_id, sensor_conf, &bhy);
    if (rslt == BHI360_OK)
    {
        printf("Enable %s at %.2fHz (fallback).\r\n", get_sensor_name(sensor_id), sensor_conf->sample_rate);
    }
    else
    {
        bhi3_s_report_api_error(rslt, &bhy);
    }

    return rslt;
}

static void bhi3_s_reset_local_data(void)
{
    bhi3_s_raw_log_close();

    orientation_accuracy_state = 0U;
    acc_accuracy_state = 0U;
    gravity_accuracy_state = 0U;
    linear_acc_accuracy_state = 0U;
    gyro_accuracy_state = 0U;

    ts_ori_sensor_ns = 0U;
    ts_lacc_sensor_ns = 0U;
    ts_gra_sensor_ns = 0U;
    ts_gyro_sensor_ns = 0U;
    ts_baro_sensor_ns = 0U;

    memset(&bhi3_s_datas, 0, sizeof(bhi3_s_datas));
    pressure_ema_initialized = false;
    pressure_ema_hpa = 0.0f;
    memset(&acc_window, 0, sizeof(acc_window));
    memset(&gyro_window, 0, sizeof(gyro_window));
    heading_filter_reset();
    tilt_filter_reset();
    motion_detector_reset();
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
    float raw_heading;
    float raw_pitch;
    float raw_roll;

    if (!callback_info || (callback_info->data_size != 7U))
    {
        return;
    }

    bhi360_event_data_parse_orientation(callback_info->data_ptr, &data);
    raw_heading = wrap_deg_360(data.heading * 360.0f / 32768.0f);
    raw_pitch = wrap_deg_180(data.pitch * 360.0f / 32768.0f);
    raw_roll = wrap_deg_180(data.roll * 360.0f / 32768.0f);
    bhi3_s_datas.heading_raw = raw_heading;
    bhi3_s_datas.heading = heading_filter_update(raw_heading);
    bhi3_s_datas.pitch_raw = raw_pitch;
    bhi3_s_datas.roll_raw = raw_roll;
    bhi3_s_datas.pitch = tilt_filter_update(raw_pitch,
                                            &pitch_ema_initialized,
                                            &pitch_ema_sin,
                                            &pitch_ema_cos,
                                            &last_pitch);
    bhi3_s_datas.roll = tilt_filter_update(raw_roll,
                                           &roll_ema_initialized,
                                           &roll_ema_sin,
                                           &roll_ema_cos,
                                           &last_roll);
    bhi3_s_datas.orientation_accuracy = orientation_accuracy_state;
    ts_ori_sensor_ns = bhi3_s_sensor_timestamp(callback_info);
}

static void parse_acc_data(const struct bhi360_fifo_parse_data_info *callback_info, void *callback_ref)
{
    (void)callback_ref;
    struct bhi360_event_data_xyz data;
    float scaling_factor = SCALING_FACTOR_INVALID_LIMIT;
    float raw_x;
    float raw_y;
    float raw_z;
    float mean_count;
    uint64_t sample_ts_ns;

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
    raw_x = data.x * scaling_factor;
    raw_y = data.y * scaling_factor;
    raw_z = data.z * scaling_factor;
    sample_ts_ns = bhi3_s_sample_time_ns(callback_info);

    bhi3_s_datas.acc_x_raw = raw_x;
    bhi3_s_datas.acc_y_raw = raw_y;
    bhi3_s_datas.acc_z_raw = raw_z;

    if (!acc_window.initialized)
    {
        acc_window.initialized = true;
        acc_window.window_start_ns = sample_ts_ns;
    }
    else if ((sample_ts_ns > acc_window.window_start_ns) &&
             ((sample_ts_ns - acc_window.window_start_ns) >= BHI3_WINDOW_NS))
    {
        acc_window.window_start_ns = sample_ts_ns;
        acc_window.sum_x = 0.0f;
        acc_window.sum_y = 0.0f;
        acc_window.sum_z = 0.0f;
        acc_window.sum_norm_sq = 0.0f;
        acc_window.count = 0U;
    }

    acc_window.sum_x += raw_x;
    acc_window.sum_y += raw_y;
    acc_window.sum_z += raw_z;
    acc_window.sum_norm_sq += (raw_x * raw_x) + (raw_y * raw_y) + (raw_z * raw_z);
    acc_window.count += 1U;

    mean_count = (float)acc_window.count;
    bhi3_s_datas.acc_x = acc_window.sum_x / mean_count;
    bhi3_s_datas.acc_y = acc_window.sum_y / mean_count;
    bhi3_s_datas.acc_z = acc_window.sum_z / mean_count;
    bhi3_s_datas.acc_rms_norm = sqrtf(acc_window.sum_norm_sq / mean_count);
    bhi3_s_datas.acc_accuracy = acc_accuracy_state;
}

static void parse_gravity_data(const struct bhi360_fifo_parse_data_info *callback_info, void *callback_ref)
{
    (void)callback_ref;
    struct bhi360_event_data_xyz data;
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
    bhi3_s_datas.gravity_accuracy = gravity_accuracy_state;
    ts_gra_sensor_ns = bhi3_s_sensor_timestamp(callback_info);
}

static void parse_linear_acc_data(const struct bhi360_fifo_parse_data_info *callback_info, void *callback_ref)
{
    (void)callback_ref;
    struct bhi360_event_data_xyz data;
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
    bhi3_s_datas.linear_acc_accuracy = linear_acc_accuracy_state;
    motion_detector_update();
    ts_lacc_sensor_ns = bhi3_s_sensor_timestamp(callback_info);
}

static void parse_gyro_data(const struct bhi360_fifo_parse_data_info *callback_info, void *callback_ref)
{
    (void)callback_ref;
    struct bhi360_event_data_xyz data;
    float scaling_factor = SCALING_FACTOR_INVALID_LIMIT;
    float raw_x;
    float raw_y;
    float raw_z;
    uint64_t sample_ts_ns;
    float dt_sec;
    bool reset_window = false;

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
    scaling_factor = get_sensor_dynamic_range_scaling(callback_info->sensor_id, (float)BHI360_GYRO_2000DPS);
    raw_x = data.x * scaling_factor * DEG_TO_RAD;
    raw_y = data.y * scaling_factor * DEG_TO_RAD;
    raw_z = data.z * scaling_factor * DEG_TO_RAD;
    sample_ts_ns = bhi3_s_sample_time_ns(callback_info);

    bhi3_s_datas.gyro_x_raw = raw_x;
    bhi3_s_datas.gyro_y_raw = raw_y;
    bhi3_s_datas.gyro_z_raw = raw_z;

    if (!gyro_window.initialized)
    {
        gyro_window.initialized = true;
        gyro_window.window_start_ns = sample_ts_ns;
        gyro_window.prev_sample_ns = sample_ts_ns;
        gyro_window.integral_x = 0.0f;
        gyro_window.integral_y = 0.0f;
        gyro_window.integral_z = 0.0f;
    }
    else
    {
        if (sample_ts_ns > gyro_window.prev_sample_ns)
        {
            dt_sec = (float)(sample_ts_ns - gyro_window.prev_sample_ns) / (float)NS_PER_SEC;
            if ((dt_sec >= 0.0f) && (dt_sec <= 0.5f))
            {
                gyro_window.integral_x += raw_x * dt_sec;
                gyro_window.integral_y += raw_y * dt_sec;
                gyro_window.integral_z += raw_z * dt_sec;
            }
        }
        gyro_window.prev_sample_ns = sample_ts_ns;

        reset_window = (sample_ts_ns > gyro_window.window_start_ns) &&
                       ((sample_ts_ns - gyro_window.window_start_ns) >= BHI3_WINDOW_NS);
    }

    bhi3_s_datas.gyro_x = gyro_window.integral_x;
    bhi3_s_datas.gyro_y = gyro_window.integral_y;
    bhi3_s_datas.gyro_z = gyro_window.integral_z;
    bhi3_s_datas.gyro_accuracy = gyro_accuracy_state;
    motion_detector_update();
    ts_gyro_sensor_ns = bhi3_s_sensor_timestamp(callback_info);

    if (reset_window)
    {
        gyro_window.window_start_ns = sample_ts_ns;
        gyro_window.integral_x = 0.0f;
        gyro_window.integral_y = 0.0f;
        gyro_window.integral_z = 0.0f;
    }
}

static void parse_pressure(const struct bhi360_fifo_parse_data_info *callback_info, void *callback_ref)
{
    (void)callback_ref;
    bhi360_float pressure;
    float pressure_hpa;

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
    pressure_hpa = pressure / 100.0f;
    bhi3_s_datas.pressure_raw = pressure_hpa;

    if (!pressure_ema_initialized)
    {
        pressure_ema_hpa = pressure_hpa;
        pressure_ema_initialized = true;
    }
    else
    {
        pressure_ema_hpa += PRESSURE_EMA_ALPHA_50HZ * (pressure_hpa - pressure_ema_hpa);
    }

    bhi3_s_datas.pressure = pressure_ema_hpa;
    ts_baro_sensor_ns = bhi3_s_sensor_timestamp(callback_info);
    bhi3_s_raw_log_write_row();
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
    (void)callback_ref;
    uint8_t meta_event_type;
    uint8_t byte1;
    uint8_t byte2;
    const char *event_text;

    if ((callback_info == NULL) || (callback_info->data_ptr == NULL) || (callback_info->data_size < 3U))
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
            switch (byte1)
            {
                case BHI360_SENSOR_ID_ORI:
                case BHI360_SENSOR_ID_ORI_WU:
                    orientation_accuracy_state = byte2;
                    bhi3_s_datas.orientation_accuracy = orientation_accuracy_state;
                    break;
                case BHI360_SENSOR_ID_ACC:
                case BHI360_SENSOR_ID_ACC_WU:
                case BHI360_SENSOR_ID_ACC_RAW:
                case BHI360_SENSOR_ID_ACC_RAW_WU:
                    acc_accuracy_state = byte2;
                    bhi3_s_datas.acc_accuracy = acc_accuracy_state;
                    break;
                case BHI360_SENSOR_ID_GRA:
                case BHI360_SENSOR_ID_GRA_WU:
                    gravity_accuracy_state = byte2;
                    bhi3_s_datas.gravity_accuracy = gravity_accuracy_state;
                    break;
                case BHI360_SENSOR_ID_LACC:
                case BHI360_SENSOR_ID_LACC_WU:
                    linear_acc_accuracy_state = byte2;
                    bhi3_s_datas.linear_acc_accuracy = linear_acc_accuracy_state;
                    break;
                case BHI360_SENSOR_ID_GYRO:
                case BHI360_SENSOR_ID_GYRO_WU:
                case BHI360_SENSOR_ID_GYRO_RAW:
                case BHI360_SENSOR_ID_GYRO_RAW_WU:
                    gyro_accuracy_state = byte2;
                    bhi3_s_datas.gyro_accuracy = gyro_accuracy_state;
                    break;
                default:
                    break;
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
