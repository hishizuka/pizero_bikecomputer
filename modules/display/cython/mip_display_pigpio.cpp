#include "mip_display.hpp"


MipDisplay::MipDisplay(int spi_clock) {

  pigpio = pigpio_start(0, 0);
  spi = spi_open(pigpio, 0, spi_clock, 0b00000100);
  usleep(6);

  set_mode(pigpio, GPIO_DISP, PI_OUTPUT);
  set_mode(pigpio, GPIO_VCOMSEL, PI_OUTPUT);
  set_mode(pigpio, GPIO_BACKLIGHT, PI_OUTPUT);
  usleep(6);

  init_common();
}

MipDisplay::~MipDisplay() {
  try {
    quit();
  } catch(...) {
  }
}

void MipDisplay::spi_write_bytes(const char* data, std::size_t length) {
  // pigpio API takes a non-const buffer pointer but does not modify the contents.
  spi_write(pigpio, spi, const_cast<char*>(data), static_cast<unsigned int>(length));
}

void MipDisplay::gpio_write_value(unsigned int offset, bool value) {
  gpio_write(pigpio, offset, value ? 1 : 0);
}

void MipDisplay::set_PWM_duty(int duty_percent) {
  hardware_PWM(pigpio, GPIO_BACKLIGHT, GPIO_BACKLIGHT_FREQ, duty_percent*10000);
}

void MipDisplay::close_backend() {
  if(pigpio < 0) {
    return;
  }
  if(spi >= 0) {
    spi_close(pigpio, spi);
    spi = -1;
  }
  pigpio_stop(pigpio);
  pigpio = -1;
}
