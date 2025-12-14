#include "mip_display.hpp"


MipDisplay::MipDisplay(int spi_clock) {
  try {
    init_spi(spi_clock);
    usleep(6);

    init_gpio();
    usleep(6);

    init_common();
  } catch(...) {
    close_spi();
    close_gpio();
    throw;
  }
}

MipDisplay::~MipDisplay() {
  try {
    quit();
  } catch(...) {
  }
}

int MipDisplay::detect_spi_max_buf_size() {
  const char* sysfs_path = "/sys/module/spidev/parameters/bufsiz";
  FILE* fp = fopen(sysfs_path, "r");
  if(fp == nullptr) {
    return -1;
  }
  long v = -1;
  const int n = fscanf(fp, "%ld", &v);
  fclose(fp);
  if(n != 1) {
    return -1;
  }
  if(v <= 0 || v > INT_MAX) {
    return -1;
  }
  return static_cast<int>(v);
}

void MipDisplay::init_spi(int spi_clock) {
  const char* spi_device = PIZERO_SPI_DEVICE_PATH;

  spi_fd = ::open(spi_device, O_RDWR | O_CLOEXEC);
  if(spi_fd < 0) {
    throw std::runtime_error(std::string("Failed to open SPI device: ") + spi_device + " (" + std::strerror(errno) + ")");
  }

  // Preserve non-mode flags configured by device tree, and force MODE0.
  uint8_t mode = 0;
  if(::ioctl(spi_fd, SPI_IOC_RD_MODE, &mode) < 0) {
    mode = 0;
  }
  mode = static_cast<uint8_t>((mode & ~0x3) | SPI_MODE_0);

  if(::ioctl(spi_fd, SPI_IOC_WR_MODE, &mode) < 0) {
    throw std::runtime_error(std::string("Failed to set SPI mode (") + std::strerror(errno) + ")");
  }

  uint8_t bits_per_word = 8;
  if(::ioctl(spi_fd, SPI_IOC_WR_BITS_PER_WORD, &bits_per_word) < 0) {
    throw std::runtime_error(std::string("Failed to set SPI bits-per-word (") + std::strerror(errno) + ")");
  }

  uint32_t speed_hz = static_cast<uint32_t>(spi_clock);
  if(::ioctl(spi_fd, SPI_IOC_WR_MAX_SPEED_HZ, &speed_hz) < 0) {
    throw std::runtime_error(std::string("Failed to set SPI speed (") + std::strerror(errno) + ")");
  }

  const int spidev_bufsiz = detect_spi_max_buf_size();
  if(spidev_bufsiz > 0) {
    SPI_MAX_BUF_SIZE = std::min(SPI_MAX_BUF_SIZE, spidev_bufsiz);
  }
}

void MipDisplay::close_spi() {
  if(spi_fd >= 0) {
    ::close(spi_fd);
    spi_fd = -1;
  }
}

void MipDisplay::init_gpio() {
  const char* chip_path = PIZERO_GPIOCHIP_PATH;

  gpio_chip = gpiod_chip_open(chip_path);
  if(gpio_chip == nullptr) {
    throw std::runtime_error(std::string("Failed to open GPIO chip: ") + chip_path);
  }

  gpiod_request_config* req_cfg = gpiod_request_config_new();
  gpiod_line_config* line_cfg = gpiod_line_config_new();
  gpiod_line_settings* settings = gpiod_line_settings_new();
  if(req_cfg == nullptr || line_cfg == nullptr || settings == nullptr) {
    if(settings != nullptr) { gpiod_line_settings_free(settings); }
    if(line_cfg != nullptr) { gpiod_line_config_free(line_cfg); }
    if(req_cfg != nullptr) { gpiod_request_config_free(req_cfg); }
    throw std::runtime_error("Failed to allocate libgpiod configs");
  }

  gpiod_request_config_set_consumer(req_cfg, PIZERO_GPIO_CONSUMER);
  gpiod_line_settings_set_direction(settings, GPIOD_LINE_DIRECTION_OUTPUT);
  gpiod_line_settings_set_output_value(settings, GPIOD_LINE_VALUE_INACTIVE);

  unsigned int offsets[] = {GPIO_DISP, GPIO_VCOMSEL, GPIO_BACKLIGHT};
  if(gpiod_line_config_add_line_settings(line_cfg, offsets, 3, settings) != 0) {
    gpiod_line_settings_free(settings);
    gpiod_line_config_free(line_cfg);
    gpiod_request_config_free(req_cfg);
    throw std::runtime_error("Failed to configure GPIO lines");
  }

  gpio_request = gpiod_chip_request_lines(gpio_chip, req_cfg, line_cfg);
  gpiod_line_settings_free(settings);
  gpiod_line_config_free(line_cfg);
  gpiod_request_config_free(req_cfg);

  if(gpio_request == nullptr) {
    throw std::runtime_error("Failed to request GPIO lines via libgpiod");
  }
}

void MipDisplay::close_gpio() {
  if(gpio_request != nullptr) {
    gpiod_line_request_release(gpio_request);
    gpio_request = nullptr;
  }
  if(gpio_chip != nullptr) {
    gpiod_chip_close(gpio_chip);
    gpio_chip = nullptr;
  }
}

void MipDisplay::spi_write_bytes(const char* data, std::size_t length) {
  ssize_t n = 0;
  do {
    n = ::write(spi_fd, data, length);
  } while(n < 0 && errno == EINTR);

  if(n < 0) {
    throw std::runtime_error(std::string("SPI write failed (") + std::strerror(errno) + ")");
  }
  if(static_cast<std::size_t>(n) != length) {
    throw std::runtime_error("SPI write returned a short write");
  }
}

void MipDisplay::gpio_write_value(unsigned int offset, bool value) {
  if(gpio_request == nullptr) {
    throw std::runtime_error("GPIO lines are not initialized");
  }
  const enum gpiod_line_value v = value ? GPIOD_LINE_VALUE_ACTIVE : GPIOD_LINE_VALUE_INACTIVE;
  if(gpiod_line_request_set_value(gpio_request, offset, v) != 0) {
    throw std::runtime_error("Failed to set GPIO line value");
  }
}

void MipDisplay::set_PWM_duty(int duty_percent) {
  gpio_write_value(GPIO_BACKLIGHT, duty_percent > 0);
}

void MipDisplay::close_backend() {
  close_spi();
  close_gpio();
}
