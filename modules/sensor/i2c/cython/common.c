#include "common.h"

int8_t i2c_open(const char *device, uint8_t addr) {
    int fd = open(device, O_RDWR);
    if (fd < 0) {
        perror("Failed to open the i2c bus");
        return -1;
    }
    
    if (ioctl(fd, I2C_SLAVE, addr) < 0) {
        perror("Failed to acquire bus access and/or talk to slave");
        close(fd);
        return -1;
    }

    return fd;
}

void i2c_close(int fd) {
    close(fd);
}

int8_t i2c_read(uint8_t reg_addr, uint8_t *data, uint32_t len, void *intf_ptr) {
    int fd = *(int *)intf_ptr;
    if (write(fd, &reg_addr, 1) != 1) return -1;
    if (read(fd, data, len) != (ssize_t)len) return -1;
    return 0;
}

int8_t i2c_write(uint8_t reg_addr, const uint8_t *data, uint32_t len, void *intf_ptr) {
    int fd = *(int *)intf_ptr;
    uint8_t buffer[len + 1];
    buffer[0] = reg_addr;
    memcpy(&buffer[1], data, len);
    if (write(fd, buffer, len + 1) != (ssize_t)(len + 1)) return -1;
    return 0;
}

void delay_us(uint32_t period, void *intf_ptr) {
    (void)intf_ptr;
    usleep(period);
}
