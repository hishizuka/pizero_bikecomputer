# cython: language_level=3

# Thin Cython wrapper around the CXD5610 C helper.

from libc.math cimport isnan

# Older Cython on some systems lacks libc.time.timespec, so declare it manually.
cdef extern from "time.h":
    cdef struct timespec:
        long tv_sec
        long tv_nsec


cdef extern from "cxd5610_rpi.h":
  cdef struct cxd5610_ctx
  cdef struct cxd5610_data:
    double lat
    double lon
    double alt
    double speed
    double track
    int mode
    int status
    double pdop
    double hdop
    double vdop
    int used_sats
    int total_sats
    timespec timestamp

  int cxd5610_create(cxd5610_ctx **out_ctx)
  int cxd5610_read(cxd5610_ctx *ctx, cxd5610_data *out, int timeout_ms)
  void cxd5610_close(cxd5610_ctx *ctx)


cdef inline object _nan_to_none(double v):
  if isnan(v):
    return None
  return v


cdef inline object _ts_to_epoch(timespec ts):
  if ts.tv_sec == 0:
    return None
  return ts.tv_sec + ts.tv_nsec / 1e9


cdef class CXD5610:
  cdef cxd5610_ctx *ctx
  cdef cxd5610_data data

  def __cinit__(self):
    self.ctx = NULL
    cdef int ret = cxd5610_create(&self.ctx)
    if ret != 0:
      # ret is negative errno; convert to positive for OSError
      if ret < 0:
        ret = -ret
      raise OSError(ret, "failed to initialize CXD5610")

  def __dealloc__(self):
    if self.ctx is not NULL:
      cxd5610_close(self.ctx)
      self.ctx = NULL

  cpdef int poll(self, int timeout_ms=1000):
    if self.ctx is NULL:
      raise ValueError("CXD5610 not initialized")
    return cxd5610_read(self.ctx, &self.data, timeout_ms)

  @property
  def lat(self):
    return _nan_to_none(self.data.lat)

  @property
  def lon(self):
    return _nan_to_none(self.data.lon)

  @property
  def alt(self):
    return _nan_to_none(self.data.alt)

  @property
  def speed(self):
    return _nan_to_none(self.data.speed)

  @property
  def track(self):
    return _nan_to_none(self.data.track)

  @property
  def mode(self):
    return None if self.data.mode < 0 else self.data.mode

  @property
  def status(self):
    return None if self.data.status < 0 else self.data.status

  @property
  def pdop(self):
    return _nan_to_none(self.data.pdop)

  @property
  def hdop(self):
    return _nan_to_none(self.data.hdop)

  @property
  def vdop(self):
    return _nan_to_none(self.data.vdop)

  @property
  def used_sats(self):
    return None if self.data.used_sats < 0 else self.data.used_sats

  @property
  def total_sats(self):
    return None if self.data.total_sats < 0 else self.data.total_sats

  @property
  def timestamp(self):
    return _ts_to_epoch(self.data.timestamp)
