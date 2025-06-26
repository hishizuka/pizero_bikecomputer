# cython: language_level=3

#cimport cython


cdef extern from "i2c_bmm150.h":
  signed char i2c_bmm150_init()
  void i2c_bmm150_read_mag(float* mag)
  void i2c_bmm150_close()

cdef extern from "i2c_bmm350.h":
  int i2c_bmm350_init()
  void i2c_bmm350_read_mag(float* mag)
  void i2c_bmm350_close()

cdef extern from "i2c_bmi270.h":
  int i2c_bmi270_init()
  void i2c_bmi270_read_data(float* acc, float* gyro)
  void i2c_bmi270_close()

cdef extern from "i2c_bmp5.h":
  int i2c_bmp5_init()
  void i2c_bmp5_read_data(float* value)
  void i2c_bmp5_close()


cdef class BMM150_C:
  cdef float mag[3]
  cdef public bint status

  def __cinit__(self, int bus):
    self.status = rslt_to_bool(i2c_bmm150_init())
    self.reset_value()
  
  def __dealloc__(self):
    i2c_bmm150_close()

  cdef reset_value(self):
    self.mag = [0.0, 0.0, 0.0]
  
  cpdef read_mag(self):
    if self.status:
      i2c_bmm150_read_mag(&self.mag[0])
  
  @property
  def magnetic(self):
    self.read_mag()
    return [self.mag[0], self.mag[1], self.mag[2]]


cdef class BMM350_C:
  cdef float mag[3]
  cdef public bint status

  def __cinit__(self, int bus):
    self.status = rslt_to_bool(i2c_bmm350_init())
    self.reset_value()
  
  def __dealloc__(self):
    i2c_bmm350_close()

  cdef reset_value(self):
    self.mag = [0.0, 0.0, 0.0]
  
  cpdef read_mag(self):
    if self.status:
      i2c_bmm350_read_mag(&self.mag[0])
  
  @property
  def magnetic(self):
    self.read_mag()
    return [self.mag[0], self.mag[1], self.mag[2]]


cdef class BMI270_C:
  cdef float acc[3]
  cdef float gyro[3]
  cdef public bint status

  def __cinit__(self, int bus):
    self.status = rslt_to_bool(i2c_bmi270_init())
    self.reset_value()
  
  def __dealloc__(self):
    i2c_bmi270_close()

  cdef reset_value(self):
    self.acc = [0.0, 0.0, 0.0]
    self.gyro = [0.0, 0.0, 0.0]
  
  cpdef read_data(self):
    if self.status:
      i2c_bmi270_read_data(&self.acc[0], &self.gyro[0])

  @property
  def acceleration(self):
    self.read_data()
    return [self.acc[0], self.acc[1], self.acc[2]]

  @property
  def gyro(self):
    #self.read_data()
    return [self.gyro[0], self.gyro[1], self.gyro[2]]


cdef class BMP5_C:
  cdef float value[2]
  cdef public bint status

  def __cinit__(self, int bus):
    self.status = rslt_to_bool(i2c_bmp5_init())
    self.reset_value()
  
  def __dealloc__(self):
    i2c_bmp5_close()

  cdef reset_value(self):
    self.value = [0.0, 0.0]
  
  cpdef read_value(self):
    if self.status:
      i2c_bmp5_read_data(&self.value[0])
  
  @property
  def pressure(self):
    self.read_value()
    return self.value[0]
  
  @property
  def temperature(self):
    #self.read_value()
    return self.value[1]
  
cpdef rslt_to_bool(int rslt):
  if rslt == 0:
    return True
  else:
    return False

