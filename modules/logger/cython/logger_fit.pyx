# cython: language_level=3
# cython: c_string_type=unicode, c_string_encoding=utf8

cdef extern from "logger_fit_c.hpp":
  cdef bint write_log_c(const char* db_file, const char* filename, const char* start_date, const char* end_date) except +
  cdef cppclass config:
    unsigned int G_UNIT_ID_HEX
  cdef void set_config_c(const config& _cfg)

def write_log_cython(str db_file, str filename, str start_date, str end_date):
  return write_log_c(db_file, filename, start_date, end_date)

def set_config(G_CONFIG):
  cdef config cfg
  cfg.G_UNIT_ID_HEX = G_CONFIG.G_UNIT_ID_HEX
  set_config_c(cfg)
