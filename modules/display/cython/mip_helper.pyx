# cython: language_level=3

import numpy as np
cimport numpy as cnp
cimport cython
from libcpp cimport bool

@cython.boundscheck(False)
@cython.wraparound(False)
@cython.nonecheck(False)
cpdef conv_3bit_8colors_cy(const cnp.uint8_t[:,:,::1] im_array):
  cdef int i, j, k, h, w, d, bit_count
  cdef int bit_index = 0
  cdef int[2] thresholds = [216, 128]
  cdef int[8] add_bit = [128, 64, 32, 16, 8, 4, 2, 1]
  cdef bool t_index = True
  h = im_array.shape[0]
  w = im_array.shape[1]
  d = im_array.shape[2]
  
  im_bits = np.zeros((h, int(w*d/8)), dtype=np.uint8)
  cdef cnp.uint8_t[:,::1] im_bits_view = im_bits

  for i in range(h):
    bit_count = 0
    bit_index = 0

    for j in range(w):
      if(im_array[i,j,0] >= thresholds[t_index]):
        im_bits_view[i, bit_index] |= add_bit[bit_count]
      bit_count = (bit_count+1)&7
      bit_index += 1 - <bool>bit_count

      if(im_array[i,j,1] >= thresholds[t_index]):
        im_bits_view[i, bit_index] |= add_bit[bit_count]
      bit_count = (bit_count+1)&7
      bit_index += 1 - <bool>bit_count

      if(im_array[i,j,2] >= thresholds[t_index]):
        im_bits_view[i, bit_index] |= add_bit[bit_count]
      bit_count = (bit_count+1)&7
      bit_index += 1 - <bool>bit_count
      
      t_index = not t_index

    t_index = not t_index

  return im_bits
