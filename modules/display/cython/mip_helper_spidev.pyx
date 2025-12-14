# cython: language_level=3

cimport numpy as cnp


cdef extern from "mip_display.hpp":
  cdef cppclass MipDisplay:
    MipDisplay(int spi_clock) except +
    void update(unsigned char* image) except +
    void set_screen_size(int w, int h, int c) except +
    void set_brightness(int b) except +
    void inversion(float sec) except +
    void quit() except +


cdef class MipDisplay_CPP:
  cdef MipDisplay* m

  def __cinit__(self, int spi_clock):
    self.m = new MipDisplay(spi_clock)

  def __dealloc__(self):
    del self.m

  cpdef set_screen_size(self, w, h, c):
    self.m.set_screen_size(w, h, c)

  cpdef update(self, const cnp.uint8_t[:,:,::1] im_array, direct_update):
    self.m.update(<unsigned char*> &im_array[0,0,0])

  cpdef set_brightness(self, b):
    self.m.set_brightness(b)
  
  cpdef inversion(self, sec):
    self.m.inversion(sec)
  
  cpdef quit(self):
    self.m.quit()

