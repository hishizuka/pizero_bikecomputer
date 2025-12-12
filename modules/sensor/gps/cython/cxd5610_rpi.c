#define _GNU_SOURCE

#include "cxd5610_rpi.h"

/*
 * Minimal Linux userspace port of the Sony CXD5610 GNSS I2C protocol.
 *
 * This implementation is informed by and includes portions adapted from
 * the Apache NuttX RTOS (Apache License 2.0), specifically the Sony CXD56xx
 * GNSS driver/protocol handling. See NOTICE for attribution and details.
 *
 * To mirror the structure of BHI3 (bhi3_s.c), this file is organized into:
 *   1) Wire-format helpers (checksum, endian, I/O)
 *   2) Notify parsers
 *   3) Session management (init/recover)
 *   4) Worker thread (interrupt wait + receive loop)
 *   5) Public API (create/read/close)
 */

typedef struct cxd5610_ctx {
  int i2c_fd;
  struct gpiod_chip *chip;
  struct gpiod_line_request *irq_req;
  struct gpiod_edge_event_buffer *evbuf;
  uint8_t sndbuf[64];
  uint8_t rcvbuf[64];
  uint8_t notifybuf[NOTIFY_MAX_BUF];
  bool boot_seen;
  bool sleeping;
  struct cxd5610_data last;
  int err_streak;
  pthread_t thread;
  pthread_mutex_t lock;
  pthread_cond_t cond;
  bool lock_initialized;
  bool cond_initialized;
  bool running;
  bool thread_started;
  bool ready;
  bool data_valid;
  int last_opc;
  uint64_t sample_seq;
} cxd5610_ctx;

/* Forward declaration for reuse inside the worker loop */
static void handle_notify(struct cxd5610_ctx *ctx,
                          uint8_t opc,
                          const uint8_t *payload,
                          uint16_t len);

static int cond_wait_ms(pthread_cond_t *cond,
                        pthread_mutex_t *lock,
                        int timeout_ms)
{
  if (timeout_ms < 0)
    {
      pthread_cond_wait(cond, lock);
      return 0;
    }

  if (timeout_ms == 0)
    {
      return -ETIMEDOUT;
    }

  struct timespec ts;
  clock_gettime(CLOCK_REALTIME, &ts);
  ts.tv_sec += timeout_ms / 1000;
  ts.tv_nsec += (timeout_ms % 1000) * 1000000L;
  if (ts.tv_nsec >= 1000000000L)
    {
      ts.tv_sec += 1;
      ts.tv_nsec -= 1000000000L;
    }

  int wret = pthread_cond_timedwait(cond, lock, &ts);
  if (wret == 0)
    {
      return 0;
    }
  if (wret == ETIMEDOUT)
    {
      return -ETIMEDOUT;
    }
  return -wret;
}

static void cxd5610_join_and_destroy_sync(struct cxd5610_ctx *ctx)
{
  if (!ctx)
    {
      return;
    }

  if (ctx->lock_initialized)
    {
      pthread_mutex_lock(&ctx->lock);
      if (ctx->thread_started)
        {
          ctx->running = false;
          pthread_cond_broadcast(&ctx->cond);
          pthread_mutex_unlock(&ctx->lock);
          pthread_join(ctx->thread, NULL);
          pthread_mutex_lock(&ctx->lock);
          ctx->thread_started = false;
        }
      pthread_mutex_unlock(&ctx->lock);
    }

  if (ctx->cond_initialized)
    {
      pthread_cond_destroy(&ctx->cond);
      ctx->cond_initialized = false;
    }
  if (ctx->lock_initialized)
    {
      pthread_mutex_destroy(&ctx->lock);
      ctx->lock_initialized = false;
    }
}

static int cond_wait_ms(pthread_cond_t *cond,
                        pthread_mutex_t *lock,
                        int timeout_ms);
static void cxd5610_join_and_destroy_sync(struct cxd5610_ctx *ctx);
/* -------------------------------------------------------------------------- */
/* 1. Wire-format helpers                                                     */
/* -------------------------------------------------------------------------- */

/* Packed wire structures (little-endian fields) */
struct __attribute__((packed)) cmd_notify_time {
  uint8_t ver8;
  uint8_t type;
  uint8_t yearl;
  uint8_t yearu_mon;
  uint8_t day;
  uint8_t hour;
  uint8_t min;
  uint8_t sec;
  uint8_t sec100;
};

struct __attribute__((packed)) cmd_notify_pos {
  uint8_t  ver8;
  uint8_t  mode;
  int32_t  lat32;
  int32_t  lon32;
  int32_t  alt32;
  int16_t  geo16;
};

struct __attribute__((packed)) cmd_notify_vel {
  uint8_t  ver8;
  uint8_t  mode;
  uint16_t course16;
  uint16_t mag_course16;
  int16_t  vel16;
  int16_t  up_vel16;
};

struct __attribute__((packed)) cmd_notify_sat {
  uint8_t  ver8;
  uint8_t  mode;
  uint16_t numsv;
};

struct __attribute__((packed)) cmd_notify_satinfo {
  uint8_t  signal;
  uint8_t  svid;
  uint8_t  cn;
  uint8_t  elevation;
  uint16_t azimuth;
};

struct __attribute__((packed)) cmd_notify_acc {
  uint8_t  ver8;
  uint16_t h_uc16;
  uint16_t v_uc16;
  uint16_t h_speed_uc16;
  uint16_t v_speed_uc16;
  uint8_t  pdop8;
  uint8_t  hdop8;
  uint8_t  vdop8;
  uint16_t semimajor16;
  uint16_t semiminor16;
  uint8_t  orientation;
};

struct __attribute__((packed)) mt43_data {
  uint8_t svid;
  uint8_t data[32];
};

struct __attribute__((packed)) cmd_notify_dcreport {
  uint8_t ver8;
  uint8_t nr;
  struct mt43_data msg[3];
};

static volatile sig_atomic_t g_stop = 0;

static void reset_data(struct cxd5610_data *d)
{
  if (!d)
    {
      return;
    }
  d->lat = NAN;
  d->lon = NAN;
  d->alt = NAN;
  d->speed = NAN;
  d->track = NAN;
  d->mode = -1;
  d->status = -1;
  d->pdop = NAN;
  d->hdop = NAN;
  d->vdop = NAN;
  d->used_sats = -1;
  d->total_sats = -1;
  d->timestamp.tv_sec = 0;
  d->timestamp.tv_nsec = 0;
}

static void handle_sigint(int sig)
{
  (void)sig;
  g_stop = 1;
}

/* Small helpers */
static uint8_t cxd_checksum(const uint8_t *data, uint16_t len)
{
  uint8_t s = 0;
  for (uint16_t i = 0; i < len; i++)
    {
      s += data[i];
    }
  return s;
}

static uint16_t le16(const void *p)
{
  const uint8_t *b = (const uint8_t *)p;
  return (uint16_t)b[0] | ((uint16_t)b[1] << 8);
}

static int32_t le32(const void *p)
{
  const uint8_t *b = (const uint8_t *)p;
  return (int32_t)(b[0] | (b[1] << 8) | (b[2] << 16) | (b[3] << 24));
}

static int read_exact(int fd, uint8_t *buf, size_t len)
{
  size_t off = 0;
  while (off < len)
    {
      ssize_t n = read(fd, buf + off, len - off);
      if (n < 0)
        {
          if (errno == EINTR)
            {
              continue;
            }
          return -errno;
        }
      if (n == 0)
        {
          return -EIO;
        }
      off += (size_t)n;
    }
  return 0;
}

static int write_exact(int fd, const uint8_t *buf, size_t len)
{
  size_t off = 0;
  while (off < len)
    {
      ssize_t n = write(fd, buf + off, len - off);
      if (n < 0)
        {
          if (errno == EINTR)
            {
              continue;
            }
          return -errno;
        }
      off += (size_t)n;
    }
  return 0;
}

static int wait_irq(struct cxd5610_ctx *ctx, int timeout_ms)
{
  struct pollfd pfd = {
    .fd = gpiod_line_request_get_fd(ctx->irq_req),
    .events = POLLIN
  };

  int pret = poll(&pfd, 1, timeout_ms);
  if (pret == 0)
    {
      return -ETIMEDOUT;
    }
  if (pret < 0)
    {
      return -errno;
    }

  int n = gpiod_line_request_read_edge_events(ctx->irq_req, ctx->evbuf, 16);
  if (n <= 0)
    {
      return -EIO;
    }

  return 0;
}

static int read_packet(struct cxd5610_ctx *ctx,
                       uint8_t *opc_out,
                       uint8_t **payload_out,
                       uint16_t *len_out,
                       int timeout_ms,
                       bool quiet)
{
  uint8_t header[PACKET_HEADERLEN];
  int ret;

  if (timeout_ms == 0)
    {
      ret = 0; /* explicit poll mode: skip IRQ wait */
    }
  else
    {
      ret = wait_irq(ctx, timeout_ms);
      if (ret < 0)
        {
          return ret;
        }
    }
  memset(header, 0, sizeof(header));
  ret = read_exact(ctx->i2c_fd, header, sizeof(header));
  if (ret < 0)
    {
      return ret;
    }

  if (header[0] != PACKET_SYNC)
    {
      if (!quiet)
        {
          fprintf(stderr, "[ERR] sync byte mismatch: 0x%02x\n", header[0]);
        }
      /* Try to re-sync by scanning upcoming bytes for PACKET_SYNC */
      for (int i = 0; i < 64; i++)
        {
          uint8_t b;
          ret = read_exact(ctx->i2c_fd, &b, 1);
          if (ret < 0)
            {
              return ret;
            }
          if (b == PACKET_SYNC)
            {
              header[0] = b;
              ret = read_exact(ctx->i2c_fd, &header[1], PACKET_HEADERLEN - 1);
              if (ret < 0)
                {
                  return ret;
                }
              goto header_ready;
            }
        }
      return -EAGAIN; /* give caller a chance to retry without aborting */
    }

header_ready:
  uint16_t oprlen = le16(&header[1]);
  uint8_t opc = header[3];

  if (header[4] != cxd_checksum(header, 4))
    {
      if (!quiet)
        {
          fprintf(stderr, "[ERR] header checksum opc=0x%02x len=%u\n", opc, oprlen);
        }
      /* Attempt to resync once */
      for (int i = 0; i < 64; i++)
        {
          uint8_t b;
          ret = read_exact(ctx->i2c_fd, &b, 1);
          if (ret < 0)
            {
              return ret;
            }
          if (b == PACKET_SYNC)
            {
              header[0] = b;
              ret = read_exact(ctx->i2c_fd, &header[1], PACKET_HEADERLEN - 1);
              if (ret < 0)
                {
                  return ret;
                }
              oprlen = le16(&header[1]);
              opc = header[3];
              if (header[4] == cxd_checksum(header, 4))
                {
                  break;
                }
              /* checksum still bad, keep searching */
            }
        }
      /* if still bad, let caller reopen */
      if (header[4] != cxd_checksum(header, 4))
        {
          return -EAGAIN;
        }
    }

  uint8_t *buf = (opc < OPC_TIME_NOTIFY) ? ctx->rcvbuf : ctx->notifybuf;
  size_t maxlen = (opc < OPC_TIME_NOTIFY) ? sizeof(ctx->rcvbuf) : sizeof(ctx->notifybuf);

  if ((size_t)oprlen + 1 > maxlen)
    {
      fprintf(stderr, "[ERR] buffer too small opc=0x%02x len=%u\n", opc, oprlen);
      return -EOVERFLOW;
    }

  if (oprlen > 0)
    {
      ret = wait_irq(ctx, timeout_ms);
      if (ret < 0)
        {
          return ret;
        }

      int totallen = oprlen + 1; /* payload + checksum */
      int num = PACKET_NR(totallen);
      int rcvlen = (totallen > PACKET_MAXLEN) ? PACKET_MAXLEN : totallen;
      uint8_t *dst = buf;

      ret = read_exact(ctx->i2c_fd, dst, rcvlen);
      if (ret < 0)
        {
          return ret;
        }

      int remaining = totallen - rcvlen;
      dst += PACKET_MAXLEN;

      while (--num > 0)
        {
          ret = wait_irq(ctx, timeout_ms);
          if (ret < 0)
            {
              return ret;
            }

          rcvlen = (remaining > PACKET_MAXLEN) ? PACKET_MAXLEN : remaining;
          ret = read_exact(ctx->i2c_fd, dst, rcvlen);
          if (ret < 0)
            {
              return ret;
            }

          remaining -= rcvlen;
          dst += PACKET_MAXLEN;
        }

      if (buf[oprlen] != cxd_checksum(buf, oprlen))
        {
      if (!quiet)
        {
          fprintf(stderr, "[ERR] payload checksum opc=0x%02x len=%u\n", opc, oprlen);
        }
          return -EAGAIN;
        }
    }

  *opc_out = opc;
  *payload_out = (oprlen > 0) ? buf : NULL;
  *len_out = oprlen;
  return 0;
}

/* Notify parsers */
static void handle_time_notify(struct cxd5610_ctx *ctx,
                               const uint8_t *p,
                               uint16_t len)
{
  if (len < sizeof(struct cmd_notify_time))
    {
      return;
    }

  const struct cmd_notify_time *t = (const struct cmd_notify_time *)p;
  if (IS_NOTIFY_INVALID(t->ver8))
    {
      return;
    }

  int year = ((t->yearu_mon >> 4) << 8) | t->yearl;
  int month = t->yearu_mon & 0x0f;

  struct tm tmv;
  memset(&tmv, 0, sizeof(tmv));
  tmv.tm_year = year - 1900;
  tmv.tm_mon = month - 1;
  tmv.tm_mday = t->day;
  tmv.tm_hour = t->hour;
  tmv.tm_min = t->min;
  tmv.tm_sec = t->sec;

#ifdef _GNU_SOURCE
  time_t epoch = timegm(&tmv);
#else
  time_t epoch = mktime(&tmv);
#endif

  ctx->last.timestamp.tv_sec = epoch;
  ctx->last.timestamp.tv_nsec = (long)t->sec100 * 10L * 1000000L;
}

static void handle_pos_notify(struct cxd5610_ctx *ctx,
                              const uint8_t *p,
                              uint16_t len)
{
  const uint16_t MIN_POS_LEN = 14;
  if (len < MIN_POS_LEN)
    {
      return;
    }

  const struct cmd_notify_pos *pos = (const struct cmd_notify_pos *)p;
  if (IS_NOTIFY_INVALID(pos->ver8))
    {
      return;
    }

  double lat = (double)le32(&pos->lat32) / 10000000.0;
  double lon = (double)le32(&pos->lon32) / 10000000.0;
  double alt = (double)le32(&pos->alt32) / 100.0;        // [m]
  double geo = 0.0;
  if (GET_PACKET_VERSION(pos->ver8) > 0 && len >= sizeof(struct cmd_notify_pos))
    {
      geo = (double)(int16_t)le16(&pos->geo16) / 100.0;
    }
  int svtype = pos->mode >> 4;
  int fix = pos->mode & 0x0f;

  ctx->last.lat = lat;
  ctx->last.lon = lon;
  ctx->last.alt = alt;
  ctx->last.status = fix;
}

static void handle_vel_notify(struct cxd5610_ctx *ctx,
                              const uint8_t *p,
                              uint16_t len)
{
  if (len < sizeof(struct cmd_notify_vel))
    {
      return;
    }

  const struct cmd_notify_vel *vel = (const struct cmd_notify_vel *)p;
  if (IS_NOTIFY_INVALID(vel->ver8))
    {
      return;
    }

  double course = (double)le16(&vel->course16) / 10.0;           // [deg]
  double mag_course = (double)le16(&vel->mag_course16) / 10.0;   // [deg]
  double v_h = (double)(int16_t)le16(&vel->vel16) / 10.0 * 1000 / 3600;     // [km/h] -> [m/s]
  double v_up = (double)(int16_t)le16(&vel->up_vel16) / 10.0 * 1000 / 3600; // [km/h] -> [m/s]

  (void)mag_course;
  (void)v_up;
  ctx->last.speed = v_h;
  ctx->last.track = course;
}

static void handle_sat_notify(struct cxd5610_ctx *ctx,
                              const uint8_t *p,
                              uint16_t len)
{
  if (len < sizeof(struct cmd_notify_sat))
    {
      return;
    }

  const struct cmd_notify_sat *sat = (const struct cmd_notify_sat *)p;
  if (IS_NOTIFY_INVALID(sat->ver8))
    {
      return;
    }

  uint16_t numsv = le16(&sat->numsv);
  if (numsv > CXD5610_MAX_SV2_NUM)
    {
      numsv = CXD5610_MAX_SV2_NUM; /* sanity cap aligned to upstream */
    }

  const struct cmd_notify_satinfo *info =
      (const struct cmd_notify_satinfo *)(p + sizeof(struct cmd_notify_sat));

  uint16_t expect_len = sizeof(struct cmd_notify_sat) + numsv * sizeof(*info);
  if (len < expect_len)
    {
      numsv = (len - sizeof(struct cmd_notify_sat)) / sizeof(*info);
    }

  // Todo: duplicate check with same type + s->svid
  uint16_t valid_sats = 0;
  for (uint16_t i = 0; i < numsv; i++)
    {
      const struct cmd_notify_satinfo *s = &info[i];
      uint16_t type = s->signal & 0x0f;
      uint16_t az = le16(&s->azimuth);
      bool tracking = (s->signal & 0x20) != 0;
      bool positioning = (s->signal & 0x80) != 0;
      bool velocity = (s->signal & 0x40) != 0;

      if (tracking)
      {
        valid_sats++;
      }
    }
  ctx->last.used_sats = (int)valid_sats;
  ctx->last.total_sats = (int)numsv;
  ctx->last.mode = sat->mode & 0x3;
}

static void handle_acc_notify(struct cxd5610_ctx *ctx,
                              const uint8_t *p,
                              uint16_t len)
{
  if (len < sizeof(struct cmd_notify_acc))
    {
      return;
    }

  const struct cmd_notify_acc *acc = (const struct cmd_notify_acc *)p;
  if (IS_NOTIFY_INVALID(acc->ver8))
    {
      return;
    }

  float hvar = (float)le16(&acc->h_uc16);                      // [m]
  float vvar = (float)le16(&acc->v_uc16);                      // [m]
  float hvar_speed = (float)le16(&acc->h_speed_uc16) / 10.0f;  // [km/h]
  float vvar_speed = (float)le16(&acc->v_speed_uc16) / 10.0f;  // [km/h]
  float pdop = (float)acc->pdop8 / 10.0f;
  float hdop = (float)acc->hdop8 / 10.0f;
  float vdop = (float)acc->vdop8 / 10.0f;
  float semimajor = (float)le16(&acc->semimajor16);
  float semiminor = (float)le16(&acc->semiminor16);
  float orientation = (float)acc->orientation;

  (void)hvar;
  (void)vvar;
  (void)hvar_speed;
  (void)vvar_speed;
  (void)semimajor;
  (void)semiminor;
  (void)orientation;

  /* Round DOP values to 3 decimal places before crossing the C/Python boundary */
  ctx->last.pdop = roundf(pdop * 1000.0f) / 1000.0f;
  ctx->last.hdop = roundf(hdop * 1000.0f) / 1000.0f;
  ctx->last.vdop = roundf(vdop * 1000.0f) / 1000.0f;
}

static void handle_dc_notify(struct cxd5610_ctx *ctx,
                             const uint8_t *p,
                             uint16_t len)
{
  if (len < sizeof(struct cmd_notify_dcreport))
    {
      return;
    }

  const struct cmd_notify_dcreport *dc = (const struct cmd_notify_dcreport *)p;
  if (IS_NOTIFY_INVALID(dc->ver8))
    {
      return;
    }

  uint8_t count = dc->nr;
  if (count > 3)
    {
      count = 3;
    }

  (void)count;
  (void)ctx;
}

/* -------------------------------------------------------------------------- */
/* 2. Notify dispatcher                                                       */
/* -------------------------------------------------------------------------- */

static void handle_notify(struct cxd5610_ctx *ctx,
                          uint8_t opc,
                          const uint8_t *payload,
                          uint16_t len)
{
  switch (opc)
    {
      case OPC_TIME_NOTIFY:
        handle_time_notify(ctx, payload, len);
        break;
      case OPC_RECEIVER_POS_NOTIFY:
        handle_pos_notify(ctx, payload, len);
        break;
      case OPC_RECEIVER_VEL_NOTIFY:
        handle_vel_notify(ctx, payload, len);
        break;
      case OPC_SAT_INFO_NOTIFY:
        handle_sat_notify(ctx, payload, len);
        break;
      case OPC_ACCURACY_IDX_NOTIFY:
        handle_acc_notify(ctx, payload, len);
        break;
      case OPC_DISASTER_CRISIS_NOTIFY:
        handle_dc_notify(ctx, payload, len);
        break;
      default:
        (void)len;
        break;
    }
}

/* Command helpers */
static int send_command(struct cxd5610_ctx *ctx,
                        uint8_t opc,
                        const void *opr,
                        size_t oprlen,
                        int timeout_ms)
{
  if (PACKET_LEN(oprlen) > sizeof(ctx->sndbuf))
    {
      return -EINVAL;
    }

  uint8_t *pkt = ctx->sndbuf;
  size_t buflen = PACKET_HEADERLEN;

  pkt[0] = PACKET_SYNC;
  pkt[1] = (uint8_t)(oprlen & 0xff);
  pkt[2] = (uint8_t)(oprlen >> 8);
  pkt[3] = opc;
  pkt[4] = cxd_checksum(pkt, 4);

  if (opr && oprlen > 0)
    {
      memcpy(&pkt[5], opr, oprlen);
      pkt[5 + oprlen] = cxd_checksum(&pkt[5], oprlen);
      buflen += (oprlen + 1);
    }

  int ret = write_exact(ctx->i2c_fd, pkt, buflen);
  if (ret < 0)
    {
      return ret;
    }

  /* Wait for the command response, printing any async notify on the way. */
  bool first_try = true;
  while (!g_stop)
    {
      uint8_t ropc;
      uint8_t *payload;
      uint16_t rlen;

      int use_timeout = first_try ? 0 : timeout_ms;
      ret = read_packet(ctx, &ropc, &payload, &rlen, use_timeout, first_try);
      first_try = false;
      if (ret < 0)
        {
          return ret;
        }

      if (ropc < OPC_TIME_NOTIFY)
        {
          if (ropc == OPC_SYS_STATE_CHANGE_INSTRUCTION && rlen > 0)
            {
              if (payload[0] == STATE_RESET)
                {
                  ctx->boot_seen = true;
                }
              else if (payload[0] == STATE_WAKEUP)
                {
                  ctx->sleeping = false;
                }
            }

          int8_t err = (rlen > 0) ? (int8_t)payload[0] : 0;
          return err;
        }
      else
        {
          handle_notify(ctx, ropc, payload, rlen);
        }
    }

  return -EINTR;
}

/* -------------------------------------------------------------------------- */
/* 3. Session management (init/cleanup/recover)                              */
/* -------------------------------------------------------------------------- */

static int init_i2c(struct cxd5610_ctx *ctx)
{
  ctx->i2c_fd = open(CXD5610_I2C_DEV, O_RDWR);
  if (ctx->i2c_fd < 0)
    {
      return -errno;
    }

  if (ioctl(ctx->i2c_fd, I2C_SLAVE, CXD5610_I2C_ADDR) < 0)
    {
      int err = -errno;
      close(ctx->i2c_fd);
      return err;
    }

  return 0;
}

static int init_gpio(struct cxd5610_ctx *ctx)
{
  ctx->chip = gpiod_chip_open("/dev/gpiochip4");
  if (!ctx->chip)
    {
      return -errno;
    }

  struct gpiod_line_settings *settings = gpiod_line_settings_new();
  if (!settings)
    {
      return -ENOMEM;
    }
  gpiod_line_settings_set_direction(settings, GPIOD_LINE_DIRECTION_INPUT);
  gpiod_line_settings_set_edge_detection(settings, GPIOD_LINE_EDGE_RISING);

  struct gpiod_line_config *lcfg = gpiod_line_config_new();
  if (!lcfg)
    {
      gpiod_line_settings_free(settings);
      return -ENOMEM;
    }

  unsigned int offset = CXD5610_INT_GPIO;
  int ret = gpiod_line_config_add_line_settings(lcfg, &offset, 1, settings);
  gpiod_line_settings_free(settings);
  if (ret < 0)
    {
      gpiod_line_config_free(lcfg);
      return -errno;
    }

  struct gpiod_request_config *rcfg = gpiod_request_config_new();
  if (!rcfg)
    {
      gpiod_line_config_free(lcfg);
      return -ENOMEM;
    }
  gpiod_request_config_set_consumer(rcfg, "cxd5610_gnss");

  ctx->irq_req = gpiod_chip_request_lines(ctx->chip, rcfg, lcfg);
  gpiod_request_config_free(rcfg);
  gpiod_line_config_free(lcfg);

  if (!ctx->irq_req)
    {
      return -errno;
    }

  ctx->evbuf = gpiod_edge_event_buffer_new(16);
  if (!ctx->evbuf)
    {
      return -ENOMEM;
    }

  return 0;
}

static void cleanup(struct cxd5610_ctx *ctx)
{
  if (!ctx)
    {
      return;
    }
  if (ctx->evbuf)
    {
      gpiod_edge_event_buffer_free(ctx->evbuf);
    }
  if (ctx->irq_req)
    {
      gpiod_line_request_release(ctx->irq_req);
    }
  if (ctx->chip)
    {
      gpiod_chip_close(ctx->chip);
    }
  if (ctx->i2c_fd >= 0)
    {
      close(ctx->i2c_fd);
    }
}

static int reopen_i2c(struct cxd5610_ctx *ctx)
{
  if (ctx->i2c_fd >= 0)
    {
      close(ctx->i2c_fd);
    }
  ctx->i2c_fd = -1;
  return init_i2c(ctx);
}

static int configure_session(struct cxd5610_ctx *ctx)
{
  int ret;

  reset_data(&ctx->last);

  /* Stop GNSS first (no payload) */
  ret = send_command(ctx, OPC_GNSS_STOP, NULL, 0, 3000);
  if (ret == -ETIMEDOUT || ret == -EAGAIN)
    {
      ret = 0; /* quiet-start: ignore initial missing response */
    }
  if (ret < 0)
    {
      return ret;
    }

  /* Satellite system setting: enable all */
  //uint8_t sat_setting[] = {0b00110101, 0b00000011}; // for GPS+QZSS
  uint8_t sat_setting[] = {0b11110111, 0b00111111}; // for all
  ret = send_command(ctx, OPC_GNSS_SAT_SETTING, sat_setting,
                     sizeof(sat_setting), 3000);
  if (ret == -ETIMEDOUT || ret == -EAGAIN)
    {
      ret = 0;
    }
  if (ret < 0)
    {
      return ret;
    }

  /* Request binary notify set */
  uint8_t notify_list[] = {
    OPC_TIME_NOTIFY,
    OPC_RECEIVER_POS_NOTIFY,
    OPC_RECEIVER_VEL_NOTIFY,
    OPC_SAT_INFO_NOTIFY,
    OPC_ACCURACY_IDX_NOTIFY
    //OPC_DISASTER_CRISIS_NOTIFY
  };
  ret = send_command(ctx, OPC_BINARY_OUTPUT_SET, notify_list, sizeof(notify_list), 3000);
  if (ret == -ETIMEDOUT || ret == -EAGAIN)
    {
      ret = 0;
    }
  if (ret < 0)
    {
      return ret;
    }

  /* Start GNSS */
  uint8_t start_param = 3;
  ret = send_command(ctx, OPC_GNSS_START, &start_param, sizeof(start_param), 3000);
  if (ret == -ETIMEDOUT || ret == -EAGAIN)
    {
      ret = 0;
    }
  return ret;
}

static void recover_session(struct cxd5610_ctx *ctx)
{
  /* Reopen I2C and re-issue minimal init sequence */
  if (reopen_i2c(ctx) < 0)
    {
      fprintf(stderr, "[RECOVER] reopen i2c failed: %s\n", strerror(errno));
      return;
    }

  int ret;

  ret = configure_session(ctx);
  fprintf(stderr, "[RECOVER] restart result=%d\n", ret);

  if (ctx->lock_initialized)
    {
      pthread_mutex_lock(&ctx->lock);
      ctx->ready = (ret == 0);
      if (ret < 0)
        {
          ctx->data_valid = false;
        }
      pthread_mutex_unlock(&ctx->lock);
    }

  ctx->err_streak = 0;
}

/* -------------------------------------------------------------------------- */
/* 4. Worker thread                                                           */
/* -------------------------------------------------------------------------- */

static bool cxd5610_should_continue(struct cxd5610_ctx *ctx)
{
  if (!ctx)
    {
      return false;
    }
  if (ctx->lock_initialized)
    {
      return ctx->running;
    }
  return false;
}

static void *cxd5610_worker(void *arg)
{
  struct cxd5610_ctx *ctx = (struct cxd5610_ctx *)arg;
  int ret;

  ret = configure_session(ctx);

  pthread_mutex_lock(&ctx->lock);
  ctx->ready = (ret == 0);
  ctx->data_valid = false;
  ctx->last_opc = ret;
  pthread_mutex_unlock(&ctx->lock);

  if (ret < 0)
    {
      return NULL;
    }

  bool first_loop = true;

  while (cxd5610_should_continue(ctx))
    {
      uint8_t opc;
      uint8_t *payload;
      uint16_t len;

      ret = read_packet(ctx, &opc, &payload, &len, -1, first_loop);
      if (ret < 0)
        {
          if (!cxd5610_should_continue(ctx))
            {
              break;
            }

          if (ret == -EAGAIN || ret == -ETIMEDOUT)
            {
              if (first_loop)
                {
                  first_loop = false;
                  ctx->err_streak = 0;
                  continue;
                }

              fprintf(stderr, "[CXD5610] read warning (%s). Reopening I2C...\n",
                      strerror(-ret));
              if (reopen_i2c(ctx) < 0)
                {
                  fprintf(stderr, "[CXD5610] reopen failed: %s\n", strerror(errno));
                }
              if (++ctx->err_streak >= 5)
                {
                  fprintf(stderr, "[CXD5610] consecutive errors, reinitializing session...\n");
                  recover_session(ctx);
                }
              continue;
            }

          fprintf(stderr, "[CXD5610] read error: %s\n", strerror(-ret));
          if (++ctx->err_streak >= 5)
            {
              fprintf(stderr, "[CXD5610] consecutive errors, reinitializing session...\n");
              recover_session(ctx);
            }
          continue;
        }

      first_loop = false;
      ctx->err_streak = 0;

      pthread_mutex_lock(&ctx->lock);
      ctx->last_opc = (int)opc;
      if (opc < OPC_TIME_NOTIFY)
        {
          /* Command reply: keep last opcode/status for diagnostics. */
          pthread_mutex_unlock(&ctx->lock);
          continue;
        }

      handle_notify(ctx, opc, payload, len);
      ctx->data_valid = true;
      ctx->sample_seq++;
      pthread_cond_signal(&ctx->cond);
      pthread_mutex_unlock(&ctx->lock);
    }

  return NULL;
}

/* -------------------------------------------------------------------------- */
/* 5. Public API (create/read/close)                                          */
/* -------------------------------------------------------------------------- */

int cxd5610_create(struct cxd5610_ctx **out_ctx)
{
  if (!out_ctx)
    {
      return -EINVAL;
    }

  struct cxd5610_ctx *ctx = calloc(1, sizeof(struct cxd5610_ctx));
  if (!ctx)
    {
      return -ENOMEM;
    }

  ctx->i2c_fd = -1;
  reset_data(&ctx->last);
  ctx->lock_initialized = false;
  ctx->cond_initialized = false;
  ctx->running = false;
  ctx->thread_started = false;
  ctx->ready = false;
  ctx->data_valid = false;
  ctx->last_opc = -1;
  ctx->sample_seq = 0;
  ctx->err_streak = 0;

  int ret = init_i2c(ctx);
  if (ret < 0)
    {
      cxd5610_close(ctx);
      *out_ctx = NULL;
      return ret;
    }

  ret = init_gpio(ctx);
  if (ret < 0)
    {
      cxd5610_close(ctx);
      *out_ctx = NULL;
      return ret;
    }

  if (pthread_mutex_init(&ctx->lock, NULL) == 0)
    {
      ctx->lock_initialized = true;
    }
  else
    {
      cxd5610_close(ctx);
      *out_ctx = NULL;
      return -ENOMEM;
    }

  if (pthread_cond_init(&ctx->cond, NULL) == 0)
    {
      ctx->cond_initialized = true;
    }
  else
    {
      pthread_mutex_destroy(&ctx->lock);
      ctx->lock_initialized = false;
      cxd5610_close(ctx);
      *out_ctx = NULL;
      return -ENOMEM;
    }

  ctx->running = true;
  ret = pthread_create(&ctx->thread, NULL, cxd5610_worker, ctx);
  if (ret != 0)
    {
      ctx->running = false;
      cxd5610_close(ctx);
      *out_ctx = NULL;
      return -ret;
    }

  ctx->thread_started = true;
  *out_ctx = ctx;
  return 0;
}

int cxd5610_read(struct cxd5610_ctx *ctx, struct cxd5610_data *out, int timeout_ms)
{
  if (!ctx)
    {
      return -EINVAL;
    }

  if (ctx->thread_started && ctx->lock_initialized)
    {
      int ret = 0;
      pthread_mutex_lock(&ctx->lock);
      uint64_t start_seq = ctx->sample_seq;

      while (ctx->running && (!ctx->data_valid || ctx->sample_seq == start_seq))
        {
          if (timeout_ms == 0)
            {
              ret = -EAGAIN;
              break;
            }

          if (timeout_ms < 0)
            {
              pthread_cond_wait(&ctx->cond, &ctx->lock);
            }
          else
            {
              struct timespec ts;
              clock_gettime(CLOCK_REALTIME, &ts);
              ts.tv_sec += timeout_ms / 1000;
              ts.tv_nsec += (timeout_ms % 1000) * 1000000L;
              if (ts.tv_nsec >= 1000000000L)
                {
                  ts.tv_sec += 1;
                  ts.tv_nsec -= 1000000000L;
                }

              int wret = pthread_cond_timedwait(&ctx->cond, &ctx->lock, &ts);
              if (wret == ETIMEDOUT)
                {
                  ret = -ETIMEDOUT;
                  break;
                }
              else if (wret != 0)
                {
                  ret = -wret;
                  break;
                }
            }
        }

      if (ret == 0 && (!ctx->running || !ctx->data_valid))
        {
          ret = -EIO;
        }

      if (ret == 0 && out)
        {
          *out = ctx->last;
        }

      int opc = (ret == 0) ? ctx->last_opc : ret;
      pthread_mutex_unlock(&ctx->lock);
      return opc;
    }

  /* Fallback: blocking read without worker thread */
  uint8_t opc;
  uint8_t *payload;
  uint16_t len;

  int ret = read_packet(ctx, &opc, &payload, &len, timeout_ms, false);
  if (ret < 0)
    {
      return ret;
    }

  if (opc >= OPC_TIME_NOTIFY)
    {
      handle_notify(ctx, opc, payload, len);
    }

  if (out)
    {
      *out = ctx->last;
    }

  return (int)opc;
}

void cxd5610_close(struct cxd5610_ctx *ctx)
{
  if (!ctx)
    {
      return;
    }

  cxd5610_join_and_destroy_sync(ctx);

  /* Attempt to stop GNSS cleanly once worker is gone */
  if (ctx->i2c_fd >= 0)
    {
      int ret = send_command(ctx, OPC_GNSS_STOP, NULL, 0, 1000);
      if (ret < 0)
        {
          fprintf(stderr, "[CXD5610] stop during close failed: %s\n", strerror(-ret));
        }
    }

  cleanup(ctx);
  free(ctx);
}


#ifndef CXD5610_NO_MAIN
int main(void)
{
  cxd5610_ctx *ctx = NULL;
  signal(SIGINT, handle_sigint);

  int ret = cxd5610_create(&ctx);
  if (ret < 0 || !ctx)
    {
      fprintf(stderr, "[CLI ] Failed to init CXD5610: %s\\n", strerror(-ret));
      return EXIT_FAILURE;
    }

  printf("[CLI ] CXD5610 initialized. Waiting for GNSS notifications (Ctrl+C to exit)...\\n");

  while (!g_stop)
    {
      struct cxd5610_data d;
      ret = cxd5610_read(ctx, &d, 1000);
      if (ret == -ETIMEDOUT || ret == -EAGAIN)
        {
          continue;
        }
      if (ret < 0)
        {
          fprintf(stderr, "[CLI ] read error: %s\\n", strerror(-ret));
          continue;
        }

      printf("[DATA] opc=0x%02x lat=%.7f lon=%.7f alt=%.2f speed=%.2f track=%.2f fix=%d sats=%d/%d\\n",
             ret,
             d.lat, d.lon, d.alt, d.speed, d.track,
             d.mode, d.used_sats, d.total_sats);
    }

  cxd5610_close(ctx);
  return EXIT_SUCCESS;
}

#endif /* CXD5610_NO_MAIN */
