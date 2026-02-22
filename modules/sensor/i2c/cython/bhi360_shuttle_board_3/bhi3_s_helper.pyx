# cython: language_level=3

#cimport cython

from libc.stdint cimport int8_t


cdef extern from "bhi3_s.h":
  cdef struct bhi3_s_data:
    float acc_x_raw
    float acc_y_raw
    float acc_z_raw
    unsigned char acc_accuracy
    float acc_x
    float acc_y
    float acc_z
    float acc_rms_norm
    float gravity_x
    float gravity_y
    float gravity_z
    unsigned char gravity_accuracy
    float linear_acc_x
    float linear_acc_y
    float linear_acc_z
    unsigned char linear_acc_accuracy
    unsigned char moving
    float gyro_x_raw
    float gyro_y_raw
    float gyro_z_raw
    unsigned char gyro_accuracy
    float gyro_x
    float gyro_y
    float gyro_z
    float heading_raw
    float pitch_raw
    float roll_raw
    unsigned char orientation_accuracy
    float heading
    float pitch
    float roll
    float pressure_raw
    float pressure
    float temperature
    float humidity
  int bhi3_s_init()
  void bhi3_s_read_data(bhi3_s_data *data)
  bint bhi3_s_ready()
  int8_t bhi3_s_last_error()
  void bhi3_s_close()
  int8_t bhi3_s_raw_log_start(const char *path)
  void bhi3_s_raw_log_stop()
  int8_t bhi3_s_raw_log_start_and_stop(const char *path)
  bint bhi3_s_raw_log_is_enabled()


cdef class BHI3_S:
  cdef public bhi3_s_data datas
  cdef public bint status

  def __cinit__(self, int bus):
    self.status = rslt_to_bool(bhi3_s_init())
    self.reset_value()
  
  def __dealloc__(self):
    self.close()

  cdef reset_value(self):
    pass

  cpdef bint read_data(self):
    if self.status:
      bhi3_s_read_data(&self.datas)
      return bhi3_s_ready()
    return 0

  @property
  def acc(self):
    self.read_data()
    return [self.datas.acc_x, self.datas.acc_y, self.datas.acc_z]

  @property
  def acc_rms_norm(self):
    self.read_data()
    return self.datas.acc_rms_norm

  @property
  def gyro(self):
    self.read_data()
    return [self.datas.gyro_x, self.datas.gyro_y, self.datas.gyro_z]

  @property
  def moving(self):
    self.read_data()
    return int(self.datas.moving)

  @property
  def heading(self):
    self.read_data()
    return int(self.datas.heading)

  @property
  def pitch(self):
    self.read_data()
    return self.datas.pitch

  @property
  def roll(self):
    self.read_data()
    return self.datas.roll

  @property
  def pressure(self):
    self.read_data()
    return self.datas.pressure

  @property
  def temperature(self):
    self.read_data()
    return int(self.datas.temperature)

  @property
  def humidity(self):
    self.read_data()
    return int(self.datas.humidity)

  @property
  def ready(self):
    return bhi3_s_ready()

  @property
  def last_error(self):
    return bhi3_s_last_error()

  @property
  def raw_log_enabled(self):
    return bhi3_s_raw_log_is_enabled()

  cpdef bint start_and_stop(self, path=None):
    cdef bytes encoded_path
    cdef const char *c_path = NULL

    if not self.status:
      return 0

    if path is not None:
      encoded_path = str(path).encode("utf-8")
      c_path = encoded_path

    return rslt_to_bool(bhi3_s_raw_log_start_and_stop(c_path))

  cpdef close(self):
    """Stop worker thread and mark instance inactive."""
    if self.status:
      bhi3_s_close()
      self.status = 0


cpdef bint rslt_to_bool(int rslt):
  return rslt == 0
