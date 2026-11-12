#ifndef __MIP_DISPLAY
#define __MIP_DISPLAY

#include <cerrno>
#include <climits>
#include <cstdio>
#include <stdexcept>
#include <string>
#include "mip_display_base.hpp"

#include <sys/ioctl.h>
#include <fcntl.h>
#include <linux/spi/spidev.h>

#include <gpiod.h>

// Device paths (compile-time overrides are supported).
#ifndef PIZERO_SPI_DEVICE_PATH
#define PIZERO_SPI_DEVICE_PATH "/dev/spidev0.0"
#endif

#ifndef PIZERO_GPIO_CONSUMER
#define PIZERO_GPIO_CONSUMER "pizero_bikecomputer"
#endif

class MipDisplay final : public MipDisplayBase {
  private:
    int spi_fd = -1;

    struct gpiod_chip* gpio_chip = nullptr;
    struct gpiod_line_request* gpio_request = nullptr;

    int detect_spi_max_buf_size();
    void init_spi(int spi_clock);
    void close_spi();

    void init_gpio(const char* gpiochip_path);
    void close_gpio();

  protected:
    void spi_write_bytes(const char* data, std::size_t length) override;
    void gpio_write_value(unsigned int offset, bool value) override;
    void close_backend() override;

  public:
    MipDisplay(int spi_clock, const char* gpiochip_path);
    ~MipDisplay() override;
};

#endif
