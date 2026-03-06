# Vendored from https://github.com/hishizuka/crdp at commit
# 9359b0ba5a89efca4d30f306dfb250d972d301d8.
# Original project: https://github.com/biran0079/crdp
# License: MIT (see NOTICE and third_party/mit/LICENSE.MIT).

from libc.stdlib cimport malloc, free
from libc.string cimport memset

cdef extern from "math.h":
    double sqrt(double theta)

cdef _c_rdp(double *x, double *y, int n, char* mask, double epsilon):
    stk = [(0, n - 1)]
    cdef int i, st, ed, index
    cdef double d, dmax, p0, p1, p2, dis
    while stk:
        st, ed = stk.pop()
        dis = sqrt((y[st]-y[ed])**2 + (x[st]-x[ed])**2)
        p0 = y[st] - y[ed]
        p1 = x[st] - x[ed]
        p2 = x[st] * y[ed] - y[st] * x[ed]
        dmax = 0.0
        index = st
        for i from st < i < ed:
            if dis:
                d = abs(p0 * x[i] - p1 * y[i] + p2) / dis
            else:
                d = sqrt((y[st]-y[i]) * (y[st]-y[i]) + (x[st]-x[i]) * (x[st]-x[i]))
            if d > dmax:
                index = i
                dmax = d
        if dmax > epsilon:
            stk.append((st, index))
            stk.append((index, ed))
        else:
            for i from st < i < ed:
                mask[i] = 0

def rdp(points, double epsilon=0, return_mask=False):
    cdef int n, i
    n = len(points)
    cdef double *x = <double*> malloc(n * sizeof(double))
    cdef double *y = <double*> malloc(n * sizeof(double))
    cdef char *mask = <char*> malloc(n)
    memset(mask, 1, n)
    for i from 0<=i<n:
        x[i] = points[i][0]
        y[i] = points[i][1]
    _c_rdp(x, y, n, mask, epsilon)
    res = []
    res_mask = []
    for i from 0<=i<n:
        if mask[i]:
            res.append(points[i])
            res_mask.append(True)
        else:
            res_mask.append(False)
    free(x)
    free(y)
    free(mask)
    if return_mask:
      return res_mask
    else:
      return res
