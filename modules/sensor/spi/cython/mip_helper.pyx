import numpy as np
cimport numpy as cnp
cimport cython
from libcpp cimport bool
import datetime


cdef extern from "mip_display.hpp":
  cdef cppclass MipDisplay:
    MipDisplay(int spi_clock)
    void update(unsigned char* image)
    void set_screen_size(int w, int h)
    void set_brightness(int b)
    void set_refresh_count(int r)
    void inversion(float sec)
    void quit()


cdef class MipDisplay_CPP:
  cdef MipDisplay* m

  def __cinit__(self, int spi_clock):
    self.m = new MipDisplay(spi_clock)

  def __dealloc__(self):
    del self.m

  cpdef set_screen_size(self, w, h):
    self.m.set_screen_size(w, h)

  cpdef update(self, cnp.ndarray[cnp.uint8_t, ndim=3] im_array):
    self.m.update(<unsigned char*> im_array.data)

  cpdef set_brightness(self, b):
    self.m.set_brightness(b)
  
  cpdef set_refresh_count(self, r):
    self.m.set_refresh_count(r)
  
  cpdef inversion(self, sec):
    self.m.inversion(sec)
  
  cpdef quit(self):
    self.m.quit()
    

@cython.boundscheck(False)
@cython.wraparound(False)
@cython.nonecheck(False)
cpdef conv_3bit_color(cnp.ndarray[cnp.uint8_t, ndim=3] im_array):
  cdef Py_ssize_t i, j, k, h, w, d, bit_count
  cdef bool bool_i, bool_j
  h = im_array.shape[0]
  w = im_array.shape[1]
  d = im_array.shape[2]
  
  im_bits = np.zeros((h,w*d/8), dtype=np.uint8)
  cdef cnp.uint8_t[:,::1] im_bits_view = im_bits

  bool_i = False
  bool_j = False
  for i in range(h):
    bool_i = not bool_i
    bit_count = 0
    for j in range(w):
      bool_j = not bool_j
      for k in range(d):
        if((bool_i != bool_j and im_array[i,j,k] >= 128) or (bool_i == bool_j and im_array[i,j,k] >= 216)):
          im_bits_view[i, (bit_count/8)] |= (1 << 7-(bit_count%8))
        bit_count += 1
  return im_bits




