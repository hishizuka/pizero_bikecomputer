#ifndef PIZERO_BIKECOMPUTER_MIP_DISPLAY_BASE_HPP
#define PIZERO_BIKECOMPUTER_MIP_DISPLAY_BASE_HPP

#include <unistd.h>
#include <cstddef>
#include <cstdint>
#include <cstring>

#include <algorithm>
#include <atomic>
#include <queue>
#include <vector>
#include <thread>
#include <mutex>
#include <condition_variable>

// GPIO.BCM
#define GPIO_DISP 25  // 22pin
#define GPIO_VCOMSEL 24  // 18pin
#define GPIO_BACKLIGHT 18  // 12pin (backend may treat as on/off)
#define GPIO_BACKLIGHT_SWITCH 24  // 18pin
#define GPIO_BACKLIGHT_FREQ 64

class MipDisplayBase {
  protected:
    virtual void spi_write_bytes(const char* data, std::size_t length) = 0;
    virtual void gpio_write_value(unsigned int offset, bool value) = 0;
    virtual void set_PWM_duty(int duty_percent) = 0;
    virtual void close_backend() = 0;

    void init_common();

    int WIDTH = 0;
    int HEIGHT = 0;

    char UPDATE_MODE = 0x80;
    int BPP = 3;
    int COLORS = 8;
    int BUF_WIDTH = 0;
    int HALF_BUF_WIDTH_64COLORS = 0;

    char* buf_image = nullptr;
    char* pre_buf_image = nullptr;

    char buf_clear[2] = {0x20,0x00};
    char buf_no_update[2] = {0x00,0x00};
    char buf_inversion[2] = {0b00010100,0x00};
    float inversion_interval = 0.25f;

    // NOTE: These are compared against uint8 image data; keep them unsigned to avoid sign-extension bugs.
    const unsigned char thresholds_3bit_27colors[2] = {216, 128};
    const unsigned char thresholds_4bit_343colors[2][3] = {{96, 160, 226}, {64, 128, 192}};
    const unsigned char add_bit[8] = {0b10000000, 0b01000000, 0b00100000, 0b00010000, 0b00001000, 0b00000100, 0b00000010, 0b00000001};

    // for riemersma dithering
    int weights[16];
    int error_r[16] = {0};
    int error_g[16] = {0};
    int error_b[16] = {0};
    int error_index = 0;
    int color_4_levels[4] = {0, 85, 170, 255};
    int quantize_lut[256];
    unsigned char *img_ptr = nullptr;
    int cur_x = 0;
    int cur_y = 0;

    int SPI_MAX_BUF_SIZE = 65536;
    int SPI_MAX_ROWS = 0;

    int pre_brightness = 0;

    std::queue<std::vector<char> > queue_;
    std::mutex mutex_;
    std::mutex update_mutex_;
    std::condition_variable cv_;
    std::vector<std::thread> threads_;
    std::atomic<bool> status_quit{false};

    void clear_buf();

    void clear();
    void no_update();

    int (MipDisplayBase::*conv_color)(unsigned char* image) = nullptr;
    int conv_1bit_2colors(unsigned char* image);
    int conv_3bit_8colors(unsigned char* image);
    int conv_3bit_27colors(unsigned char* image);
    int conv_4bit_64colors(unsigned char* image);
    int conv_4bit_343colors(unsigned char* image);

    // for riemersma dithering
    void init_weights();
    int quantize_4level(int value);
    void dither_pixel_rgb(unsigned char *pixel);
    void dither_pixel_rgb_64(unsigned char *pixel);
    void move(int direction);
    void hilbert_level(int level, int direction);
    int log2int(int value);
    void riemersma_dithering(unsigned char *image);

    void set_PWM(int b);

    void draw_worker();
    void draw(std::vector<char>& buf_queue);
    bool get_status_quit();

  public:
    MipDisplayBase() = default;
    virtual ~MipDisplayBase() = default;

    void update(unsigned char* image);
    void set_screen_size(int w, int h, int c);
    void set_brightness(int brightness);
    void inversion(float sec);
    void quit();
};

#endif
