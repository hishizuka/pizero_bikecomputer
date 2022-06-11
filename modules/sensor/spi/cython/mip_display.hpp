#include <unistd.h>
#include <cstring>
#include <iostream>
#include <chrono>

#include <queue>
#include <vector>
#include <thread>
#include <mutex>
#include <condition_variable>

#include <pigpiod_if2.h>

//#GPIO.BCM
#define GPIO_DISP 27 //13 in GPIO.BOARD
#define GPIO_SCS 22 //15 in GPIO.BOARD
#define GPIO_VCOMSEL 17 //11 in GPIO.BOARD
#define GPIO_BACKLIGHT 18 //12 in GPIO.BOARD with hardware PWM in pigpio
#define GPIO_BACKLIGHT_FREQ 64


class MipDisplay {

  private:
    int pigpio;
    int spi;

    int WIDTH;
    int HEIGHT;

    char UPDATE_MODE = 0x80;
    int BPP = 3;
    int BUF_WIDTH;
    char* buf_image;
    char* pre_buf_image;
    char buf_clear[2] = {0x20,0x00};
    char buf_no_update[2] = {0x00,0x00};
    float inversion_interval = 0.25;
    char buf_inversion[2] = {0b00010100,0x00};
    
    const char thresholds[2] = {216, 128};
    const char add_bit[8] = {0b10000000, 0b01000000, 0b00100000, 0b00010000, 0b00001000, 0b00000100, 0b00000010, 0b00000001};

    int diff_count = 0;
    int refresh_count = 1200;
    int MAX_HEIGHT_PER_ONCE = 270;

    std::queue<std::vector<char> > queue_;
    std::mutex mutex_;
    std::condition_variable cv_;
    std::vector<std::thread> threads_;
    bool status_quit;

    void clear_buf();

    void clear();
    void no_update();

    void draw_worker();
    void draw(std::vector<char>& buf_queue);
    bool get_status_quit();

  public:
    MipDisplay(int spi_clock);
    ~MipDisplay();

    void update(unsigned char* image);
    void set_screen_size(int w, int h);
    void set_refresh_count(int r);
    void set_brightness(int brightness);
    void inversion(float sec);
    void quit();

};
