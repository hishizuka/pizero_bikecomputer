#ifndef __MIP_DISPLAY
#define __MIP_DISPLAY

#include "mip_display_base.hpp"

#include <pigpiod_if2.h>

class MipDisplay final : public MipDisplayBase {
  private:
    int pigpio = -1;
    int spi = -1;

  protected:
    void spi_write_bytes(const char* data, std::size_t length) override;
    void gpio_write_value(unsigned int offset, bool value) override;
    void set_PWM_duty(int duty_percent) override;
    void close_backend() override;

  public:
    explicit MipDisplay(int spi_clock);
    ~MipDisplay() override;
};

#endif
