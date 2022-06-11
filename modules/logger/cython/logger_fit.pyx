cdef extern from "logger_fit_c.hpp":
  cdef bint write_log_c(const char* db_file) except +
  #cdef bint write_log_c(const char* db_file)
  cdef cppclass config:
    unsigned int G_UNIT_ID_HEX
    char* G_LOG_START_DATE
    char* G_LOG_DIR
    char* G_STRAVA_UPLOAD_FILE
  cdef void set_config_c(const config& _cfg)
  cdef char* get_upload_file_name_c()
  cdef char* get_start_date_str_c()

def write_log_cython(str db_file):
  py_byte_string = db_file.encode('UTF-8')
  cdef char* c_db_file = py_byte_string
  return write_log_c(c_db_file)

def set_config(G_CONFIG):
  cdef config cfg
  py_byte_string = G_CONFIG.G_LOG_DIR.encode('UTF-8')
  cfg.G_LOG_DIR = py_byte_string
  cfg.G_UNIT_ID_HEX = G_CONFIG.G_UNIT_ID_HEX
  set_config_c(cfg)

def get_upload_file_name():
  return get_upload_file_name_c().decode('UTF-8')
  
def get_start_date_str():
  return get_start_date_str_c().decode('UTF-8')
  
  
  