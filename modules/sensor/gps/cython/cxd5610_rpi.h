/* Public API for CXD5610 GNSS access from Cython */
#ifndef CXD5610_RPI_H
#define CXD5610_RPI_H

#include <errno.h>
#include <fcntl.h>
#include <gpiod.h>
#include <linux/i2c-dev.h>
#include <math.h>
#include <pthread.h>
#include <poll.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <time.h>
#include <unistd.h>

#define CXD5610_INT_GPIO   17  /* Interrupt GPIO pin (BCM numbering) */
#define CXD5610_I2C_DEV     "/dev/i2c-1"
#define CXD5610_I2C_ADDR    0x24

#define PACKET_SYNC         0x7f
#define PACKET_MAXLEN       512
#define PACKET_HEADERLEN    5
#define PACKET_CHECKSUMLEN  1
#define PACKET_LEN(n)       ((n) + PACKET_HEADERLEN + PACKET_CHECKSUMLEN)
#define PACKET_NR(n)        (((n) + (PACKET_MAXLEN - 1)) / PACKET_MAXLEN)

/* OPC codes */
#define OPC_SYS_STATE_CHANGE_INSTRUCTION  0x00
#define OPC_FWVER_REQ                     0x06
#define OPC_BACKUP_MANUAL                 0x10
#define OPC_PPS_OUTPUT                    0x15
#define OPC_GNSS_START                    0x30
#define OPC_GNSS_STOP                     0x31
#define OPC_GNSS_SAT_SETTING              0x32
#define OPC_BINARY_OUTPUT_SET             0x34
#define OPC_RECEIVER_POS_SET              0x35
#define OPC_UTC_TIME_SET                  0x36
#define OPC_OP_MODE_SET                   0x3d
#define OPC_OP_MODE_GET                   0x3e
#define OPC_TIME_NOTIFY                   0x80
#define OPC_RECEIVER_POS_NOTIFY           0x81
#define OPC_RECEIVER_VEL_NOTIFY           0x82
#define OPC_SAT_INFO_NOTIFY               0x83
#define OPC_ACCURACY_IDX_NOTIFY           0x89
#define OPC_DISASTER_CRISIS_NOTIFY        0x8b

/* System state payload values */
#define STATE_RESET     0x01
#define STATE_WAKEUP    0x02

/* Notify helpers */
#define IS_NOTIFY_INVALID(v)  (((v) & 0x80) == 0)
#define GET_PACKET_VERSION(v) ((v) & 0x7f)

#define NOTIFY_MAX_BUF  (PACKET_MAXLEN * 3) /* 1536 bytes as in the RTOS driver */
#define CXD5610_MAX_SV2_NUM 150 /* Align with CXD56_GNSS_MAX_SV2_NUM in NuttX */

#ifdef __cplusplus
extern "C" {
#endif

typedef struct cxd5610_ctx cxd5610_ctx;

struct cxd5610_data {
  double lat;
  double lon;
  double alt;
  double speed;
  double track;
  int mode;
  int status;
  double pdop;
  double hdop;
  double vdop;
  int used_sats;
  int total_sats;
  struct timespec timestamp;
};

int cxd5610_create(cxd5610_ctx **out_ctx);
int cxd5610_read(cxd5610_ctx *ctx, struct cxd5610_data *out, int timeout_ms);
void cxd5610_close(cxd5610_ctx *ctx);

#ifdef __cplusplus
}
#endif

#endif /* CXD5610_RPI_H */
