# cython: language_level=3

#cimport cython

from libc.stdint cimport int8_t


cdef extern from "bhi3_s.h":
  cdef struct bhi3_s_data:
    float acc_x
    float acc_y
    float acc_z
    float heading
    float pitch
    float roll
    float temperature
    float pressure
    float humidity
  int bhi3_s_init()
  void bhi3_s_read_data(bhi3_s_data *data)
  bint bhi3_s_ready()
  int8_t bhi3_s_last_error()
  void bhi3_s_close()


cdef class BHI3_S:
  cdef public bhi3_s_data datas
  cdef public bint status

  def __cinit__(self, int bus):
    self.status = rslt_to_bool(bhi3_s_init())
    self.reset_value()
  
  def __dealloc__(self):
    bhi3_s_close()

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
  def heading(self):
    self.read_data()
    return int(self.datas.heading)
  
  @property
  def pitch(self):
    self.read_data()
    return int(self.datas.pitch)
  
  @property
  def roll(self):
    self.read_data()
    return int(self.datas.roll)

  @property
  def temperature(self):
    self.read_data()
    return int(self.datas.temperature)
  
  @property
  def pressure(self):
    self.read_data()
    return self.datas.pressure

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


cpdef bint rslt_to_bool(int rslt):
  return rslt == 0
