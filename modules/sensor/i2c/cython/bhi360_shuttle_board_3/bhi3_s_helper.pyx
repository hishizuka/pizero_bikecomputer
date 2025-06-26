# cython: language_level=3

#cimport cython


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
    
  cpdef read_data(self):
    if self.status:
      bhi3_s_read_data(&self.datas)

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
    return int(self.datas.pitch)
  
  @property
  def roll(self):
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


cpdef rslt_to_bool(int rslt):
  if rslt == 0:
    return True
  else:
    return False

