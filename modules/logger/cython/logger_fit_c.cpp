#include "logger_fit_c.hpp"

void set_config_c(const config& _cfg) {
  cfg.G_UNIT_ID_HEX = _cfg.G_UNIT_ID_HEX;
  cfg.G_LOG_DIR = (char *)malloc(sizeof(char) * strlen(_cfg.G_LOG_DIR)+1);
  strncpy(cfg.G_LOG_DIR, _cfg.G_LOG_DIR, strlen(_cfg.G_LOG_DIR));
  cfg.G_LOG_DIR[strlen(_cfg.G_LOG_DIR)] = '\0';
}

char* get_upload_file_name_c() {
  return cfg.G_UPLOAD_FILE;
}
char* get_start_date_str_c() {
  return cfg.G_LOG_START_DATE;
}

void reset() {
  fit_data.clear();
  struct_def_cache.clear();
  message_num = 0;

  profile_indexes = {
    {0,  {0,1,2,3,4,5,7,8}}, //file_id
    {18, {253,2,5,7,8,9,14,15,16,17,18,19,20,21,22,23,26,48}}, //session
    {19, {253,2,7,8,9,13,14,15,16,17,18,19,20,21,22,42}}, //lap
    {20, {253,0,1,2,3,4,5,6,7,13,29}}, //record
    {21, {0,1,2,3,4,5,6,253}}, //activity
    {49, {0,1}}, //file_creator
  };

  sql_indexes = {
    {18, 
      {
        {253,8,9,14,16,18,20,22,23,26,48},
        {2,15,17,19,21}
      }
    },
    {19, 
      {
        {253,8,9,13,15,17,19,21,22,42},
        {2,14,16,18,20}
      }
    }
  };

  profile_name_type = {
    {0, 
      {
        {0, {"type","enum"}},
        {1, {"manufacturer","uint16"}},
        {3, {"serial_number","uint32z"}},
        {4, {"time_created","uint32"}},
      }
    },
    {18, 
      {
        {253, {"timestamp","uint32"}},
        {2, {"start_time","uint32"}},
        {5, {"sport","enum"}},
        {7, {"total_elapsed_time","uint32"}},
        {8, {"total_timer_time","uint32"}},
        {9, {"total_distance","uint32"}},
        {14, {"avg_speed","uint16"}},
        {15, {"max_speed","uint16"}},
        {16, {"avg_heart_rate","uint8"}},
        {17, {"max_heart_rate","uint8"}},
        {18, {"avg_cadence","uint8"}},
        {19, {"max_cadence","uint8"}},
        {20, {"avg_power","uint16"}},
        {21, {"max_power","uint16"}},
        {22, {"total_ascent","uint16"}},
        {23, {"total_descent","uint16"}},
        {26, {"num_laps","uint16"}},
        {48, {"total_work","uint32"}},
      }
    },
    {19, 
      {
        {253, {"timestamp","uint32"}},
        {2, {"start_time","uint32"}},
        {7, {"total_elapsed_time","uint32"}},
        {8, {"total_timer_time","uint32"}},
        {9, {"total_distance","uint32"}},
        {13, {"avg_speed","uint16"}},
        {14, {"max_speed","uint16"}},
        {15, {"avg_heart_rate","uint8"}},
        {16, {"max_heart_rate","uint8"}},
        {17, {"avg_cadence","uint8"}},
        {18, {"max_cadence","uint8"}},
        {19, {"avg_power","uint16"}},
        {20, {"max_power","uint16"}},
        {21, {"total_ascent","uint16"}},
        {22, {"total_descent","uint16"}},
        {42, {"total_work","uint32"}},
      }
    },
    {20, 
      {
        {253, {"timestamp","uint32"}},
        {0, {"position_lat","sint32"}},
        {1, {"position_long","sint32"}},
        {2, {"altitude","uint16"}},
        {3, {"heart_rate","uint8"}},
        {4, {"cadence","uint8"}},
        {5, {"distance","uint32"}},
        {6, {"speed","uint16"}},
        {7, {"power","uint16"}},
        {13, {"temperature","sint8"}},
        {29, {"accumulated_power","uint32"}},
      }
    },
    {34, 
      {
        {0, {"total_timer_time","uint32"}},
        {1, {"num_sessions","uint16"}},
        {2, {"type","enum"}},
        {3, {"event","enum"}},
        {4, {"event_type","enum"}},
        {5, {"local_timestamp","uint32"}},
        {6, {"event_group","uint8"}},
        {253, {"timestamp","uint32"}},
      }
    },
    {49, 
      {
        {0, {"software_version","uint16"}},
        {1, {"hardware_version","uint8"}},
      }
    },
  };

  sql_items = {
    {18,
      {
        {"timestamp,total_timer_time,distance,avg_speed,avg_heart_rate,avg_cadence,avg_power,total_ascent,total_descent,lap,accumulated_power"},
        {"MIN(timestamp),MAX(speed),MAX(heart_rate),MAX(cadence),MAX(power)"},
      }
    },
    {19,
      {
        {"timestamp,timer,lap_distance,lap_speed,lap_heart_rate,lap_cadence,lap_power,lap_total_ascent,lap_total_descent,lap_accumulated_power"},
        {"MIN(timestamp),MAX(speed),MAX(heart_rate),MAX(cadence),MAX(power)"},
      }
    },
    {20,
      {
        {"timestamp,position_lat,position_long,altitude,heart_rate,cadence,distance,speed,power,temperature,accumulated_power"} 
      }
    },
  };
  base_sql = {
    {18,
      { 
        {"SELECT %s FROM BIKECOMPUTER_LOG WHERE total_timer_time = (SELECT MAX(total_timer_time) FROM BIKECOMPUTER_LOG)"},
        {"SELECT %s FROM BIKECOMPUTER_LOG"}
      }
    },
    {19,
      { 
        {"SELECT %s FROM BIKECOMPUTER_LOG WHERE LAP = %d AND TIMER = (SELECT MAX(TIMER) FROM BIKECOMPUTER_LOG WHERE LAP = %d)"},
        {"SELECT %s FROM BIKECOMPUTER_LOG WHERE LAP = %d"}
      }
    },
    {20,
      {
        {"SELECT %s FROM BIKECOMPUTER_LOG WHERE lap = %d"} 
      }
    },
  };

  local_num[0] = 0;
  local_num_field[0] = {3,4,1,0};
  local_num[1] = 49;
  local_num_field[1] = {0,1};

  data_scale[18][7] = 1000;
  data_scale[18][8] = 1000;
  data_scale[18][9] = 100;
  data_scale[18][14] = 1000;
  data_scale[18][15] = 1000;
  data_scale[19][7] = 1000;
  data_scale[19][8] = 1000;
  data_scale[19][9] = 100;
  data_scale[19][13] = 1000;
  data_scale[19][14] = 1000;
  data_scale[20][2] = 5;
  data_scale[20][5] = 100;
  data_scale[20][6] = 1000;

  base_type_id = {
    {"enum", 0x00}, // 0
    {"sint8", 0x01}, // 1
    {"uint8", 0x02}, // 2
    {"bool", 0x02}, // 2
    {"sint16", 0x83}, // 3
    {"uint16", 0x84}, // 4
    {"sint32", 0x85}, // 5
    {"uint32", 0x86}, // 6
    {"string", 0x07}, // 7
    {"float32", 0x88}, // 8
    {"float64", 0x89}, // 9
    {"uint8z", 0x0a}, // 10
    {"uint16z", 0x8b}, // 11
    {"uint32z", 0x8c}, // 12
    {"byte", 0x0d},
  };
  base_type_size = {1,1,1,2,2,4,4,1,4,8,1,2,4,1};

  struct tm epoch_datetime = {0,0,0,31,11,1989-1900}; //"1989-12-31 00:00:00"
  epoch_datetime_sec = mktime(&epoch_datetime);
}

bool exit_with_error(const char* message, sqlite3* db) {
  fprintf(stderr, "%s: %s\n", message, sqlite3_errmsg(db));
  sqlite3_close(db);
  return false;
}

unsigned int crc16(std::vector<uint8_t>& data) {
  unsigned int crc = 0;
  //uint8_t byte, d;
  uint8_t byte;
  unsigned int tmp;
  unsigned int crc_table[16] = {
    0x0000, 0xCC01, 0xD801, 0x1400, 
    0xF001, 0x3C00, 0x2800, 0xE401,
    0xA001, 0x6C00, 0x7800, 0xB401, 
    0x5000, 0x9C01, 0x8801, 0x4400,
  };

  for(uint8_t d: data) {
    byte = d;
    //compute checksum of lower four bits of byte
    tmp = crc_table[crc & 0xF];
    crc = (crc >> 4) & 0x0FFF;
    crc = crc ^ tmp ^ crc_table[byte & 0xF];
    //now compute checksum of upper four bits of byte
    tmp = crc_table[crc & 0xF];
    crc = (crc >> 4) & 0x0FFF;
    crc = crc ^ tmp ^ crc_table[(byte >> 4) & 0xF];
  }
  return crc;
}

unsigned int convert_value(const char* value_str, const int data_type) {
  unsigned int value = 0;
  //latitude(0) longitude(1)
  if(message_num == 20 and (data_type == 0 or data_type == 1)) {
    value = (unsigned int)int(atof(value_str) * LAT_LON_CONST); //int(atof(value_str) / 180 * pow(2,31));
  }
  //timestamp(253), local_timestamp, start_time
  else if (
    (message_num == 0 and data_type == 4) or 
    ((message_num == 18 or message_num == 19) and (data_type == 253 or data_type == 2)) or 
    (message_num == 20 and data_type == 253)
  ) {
    std::string s(value_str);
    struct tm t = {
      atoi(s.substr(17,2).c_str()),
      atoi(s.substr(14,2).c_str()),
      atoi(s.substr(11,2).c_str()),
      atoi(s.substr(8,2).c_str()),
      atoi(s.substr(5,2).c_str())-1,
      atoi(s.substr(0,4).c_str())-1900,
    };
    value = (unsigned int)int(difftime(mktime(&t), epoch_datetime_sec));
  }
  //altitude(2): with scale and offset
  else if (message_num == 20 and data_type == 2) {
    value = (unsigned int)int(data_scale[message_num][data_type] * (atof(value_str) + 500));
  }
  //distance(5), speed(6): with scale
  else if (
    (message_num == 18 and (data_type == 8 or data_type == 9 or data_type == 14 or data_type == 15)) or 
    (message_num == 19 and (data_type == 8 or data_type == 9 or data_type == 13 or data_type == 14)) or 
    (message_num == 20 and (data_type == 5 or data_type == 6))
  ) {
    value = (unsigned int)data_scale[message_num][data_type] * atof(value_str);
  }
  else {
    value = (unsigned int)int(atof(value_str));
  }
  return value;
}

static int parse_single_str(void *user_data, int argc, char **argv, char **azColName) {
  char *data_str = (char*)user_data;
  for(int i = 0; i < argc; ++i) {
    strcpy(data_str, argv[i]);
  }
  return 0;
}

static int parse_single_num(void *user_data, int argc, char **argv, char **azColName) {
  int *num = (int*)user_data;
  for(int i = 0; i < argc; ++i) {
    (*num) = int(atof(argv[i]));
  }
  return 0;
}

void add_fit_data(std::vector<uint8_t>& _bytes, std::vector<unsigned int>& _data, std::vector<int>& _size) {
  for(int i = 0, n = _data.size(); i < n; ++i) {
    uint8_t *h = (uint8_t *)&_data[i];
    for(int j = 0; j < _size[i]; ++j) {
      _bytes.push_back(h[j]);
    }
  }
}

void get_struct_def(std::vector<int>& _size, int l_num, bool l_num_used) {
  if(l_num_used and struct_def_cache.find(l_num) != struct_def_cache.end()){
    _size = struct_def_cache[l_num];
  }
  else {
    _size.clear();
    for (int f_id: local_num_field[l_num]) {
      std::string f_type = profile_name_type[local_num[l_num]][f_id][1];
      int base_type_id = base_type_id_from_string(f_type);
      _size.push_back(base_type_size_from_id(base_type_id));
    }
    struct_def_cache[l_num] = _size;
  }
  //write data header(0x00)
  fit_data.push_back(uint8_t(l_num+0x00));
}

int get_local_message_num(std::vector<int>& available_fields) {
  int index = -1;
  for(auto pair:local_num) {
    if(local_num[pair.first] == message_num and local_num_field[pair.first] == available_fields) {
      index = pair.first;
    }
  }
  return index;
}

void write_definition() {
  int m_num = local_num[local_message_num];
  std::vector<int>& l_field = local_num_field[local_message_num];
  std::vector<int> _size = {1,1,2,1};
  std::vector<unsigned int> _data = {0,0,(unsigned int)m_num,(unsigned int)l_field.size()};

  //write definition header(0x40)
  fit_data.push_back(uint8_t(local_message_num+0x40));
  add_fit_data(fit_data, _data, _size);

  for (int f_id: l_field) {
    unsigned int base_type_id = base_type_id_from_string(profile_name_type[message_num][f_id][1]);
    unsigned int base_type_size = base_type_size_from_id(base_type_id);
    _size = {1,1,1};
    _data = {(unsigned int)f_id, base_type_size, base_type_id};
    add_fit_data(fit_data, _data, _size);
  }

}

static int parse_records_message_num_18_19(void *user_data, int argc, char **argv, char **azColName) {
  std::vector<lap_summary_data> *_data = (std::vector<lap_summary_data>*)user_data;
  for(int i = 0; i < argc; ++i) {
    lap_summary_data d;
    if(argv[i] == NULL) {
      d.is_null = true;
      d.data = "";
    }
    else {
      d.data = std::string(argv[i]);
    }
    (*_data).push_back(d);
  }
  return 0;
}

static int parse_records_message_num_20(void *user_data, int argc, char **argv, char **azColName) {
  //int *counter = (int*)user_data;
  std::vector<int> available_fields, _size;
  std::vector<unsigned int> available_data;
  available_fields.reserve(argc*sizeof(int));
  available_data.reserve(argc*sizeof(int));

  int index;
  for(int i = 0; i < argc; ++i) {
    if(argv[i] == NULL) continue;
    index = profile_indexes[message_num][i];
    available_fields.push_back(index);
    available_data.push_back(convert_value(argv[i], index));
  }

  int l_num = get_local_message_num(available_fields);
  bool l_num_used = true;
  if(l_num == -1) {
    l_num_used = false;
    //write header if need
    local_message_num = (local_message_num + 1)%16;
    local_num[local_message_num] = message_num;
    local_num_field[local_message_num] = available_fields;
    write_definition();
    l_num = local_message_num;
  }
  get_struct_def(_size, l_num, l_num_used);

  //write data
  add_fit_data(fit_data, available_data, _size);

  return 0;
}

bool get_summary(int lap_num, sqlite3 *db) {
  int rc;
  char *zErrMsg = 0;
  std::unordered_map<int, std::vector<lap_summary_data> > _ret_data;
  std::vector<int> available_fields, _size;
  std::vector<unsigned int> available_data;
  _ret_data[0].reserve(profile_indexes[message_num].size());
  _ret_data[1].reserve(profile_indexes[message_num].size());
  
  char _sql_ave[strlen(base_sql[message_num][0].c_str())+strlen(sql_items[message_num][0].c_str())+10];
  char _sql_MAX_MIN[strlen(base_sql[message_num][1].c_str())+strlen(sql_items[message_num][1].c_str())+10];
  if(message_num == 19) {
    sprintf(_sql_ave, base_sql[message_num][0].c_str(), sql_items[message_num][0].c_str(), lap_num, lap_num);
    sprintf(_sql_MAX_MIN, base_sql[message_num][1].c_str(), sql_items[message_num][1].c_str(), lap_num);
  }
  else if (message_num == 18) {
    sprintf(_sql_ave, base_sql[message_num][0].c_str(), sql_items[message_num][0].c_str());
    sprintf(_sql_MAX_MIN, base_sql[message_num][1].c_str(), sql_items[message_num][1].c_str());
  }

  rc = sqlite3_exec(db, _sql_ave, parse_records_message_num_18_19, &_ret_data[0], &zErrMsg);
  if(rc) { return exit_with_error("SQL error(lap_session_ave)", db); }
  rc = sqlite3_exec(db, _sql_MAX_MIN, parse_records_message_num_18_19, &_ret_data[1], &zErrMsg);
  if(rc) { return exit_with_error("SQL error(lap_session_MAX_MIN)", db); }

  for(int i: profile_indexes[message_num]){
    //sport = 2(cycling) in session(message_num = 18)
    if(i == 5 and message_num == 18) continue;
    //total_elapsed_time
    else if(i == 7 and available_data.size() >= 2) {
      //253 - 2
      available_fields.push_back(i);
      available_data.push_back((unsigned int)(data_scale[message_num][i]*(available_data[0]-available_data[1])));
      continue;
    }

    int ave_or_MAX_MIN = -1;
    int index = -1;

    //get data
    for(int j = 0; j < 2; ++j) {
      auto res = std::find(sql_indexes[message_num][j].begin(), sql_indexes[message_num][j].end(), i);
      if(res != sql_indexes[message_num][j].end()) {
        ave_or_MAX_MIN = j;
        index = res - sql_indexes[message_num][j].begin();
        break;
      }
    }
    
    if(_ret_data[ave_or_MAX_MIN][index].is_null) continue;
    
    available_fields.push_back(i);
    available_data.push_back(convert_value(_ret_data[ave_or_MAX_MIN][index].data.c_str(), i));
  }

  if(message_num == 18) {
    available_fields.push_back(5);
    available_data.push_back(2);
  }

  int l_num = get_local_message_num(available_fields);
  bool l_num_used = true;
  if(l_num == -1) {
    l_num_used = false;
    //write header if need
    local_message_num = (local_message_num + 1)%16;
    local_num[local_message_num] = message_num;
    local_num_field[local_message_num] = available_fields;
    write_definition();
    l_num = local_message_num;
  }
  get_struct_def(_size, l_num, l_num_used);

  //write data
  add_fit_data(fit_data, available_data, _size);

  return true;
}

bool write_log_c(const char* db_file) {
  sqlite3 *db;
  char *zErrMsg = 0;
  int rc, max_lap, rows;
  char start_date[30], end_date[30];
  std::vector<int> _size;
  std::vector<unsigned int> _data;
  reset();

  FILE* fp_db = fopen(db_file, "r");
  if (fp_db == NULL) {
    fprintf(stderr, "db file doesn't exist\n");
    return false;
  }
  rc = sqlite3_open(db_file, &db);
  if(rc) { return exit_with_error("Can't open database", db); }

  //get start_date and end_date
  message_num = 0;
  rc = sqlite3_exec(db, "SELECT MIN(timestamp) FROM BIKECOMPUTER_LOG", parse_single_str, &start_date, &zErrMsg);
  if(rc) { return exit_with_error("SQL error(start_date)", db); }
  time_t start_date_epoch = convert_value(start_date, 4);
  rc = sqlite3_exec(db, "SELECT MAX(timestamp) FROM BIKECOMPUTER_LOG", parse_single_str, &end_date, &zErrMsg);
  if(rc) { return exit_with_error("SQL error(end_date)", db); }
  time_t end_date_epoch = convert_value(end_date, 4);

  //file_id (message_num:0)
  message_num = 0;
  local_message_num = 0;
  write_definition(); //need message_num, local_message_num
  get_struct_def(_size, local_message_num, true);
  _data = {
    cfg.G_UNIT_ID_HEX,     // serial_number: XXXXXXXXXX
    (unsigned int)start_date_epoch, //timestamp()
    255,                   //manufacturer (255: development)
    4                      //type
  };
  add_fit_data(fit_data, _data, _size);

  //file_creator (message_num:49)
  message_num = 49;
  local_message_num += 1;
  write_definition();
  get_struct_def(_size, local_message_num, true);
  _data = {
    100, //software version
    1    //hardware version
  };
  add_fit_data(fit_data, _data, _size);
  //printf("header: %d\n", (int)crc16(fit_data));

  //get records
  message_num = 20;
  rc = sqlite3_exec(db, "SELECT COUNT(*) FROM BIKECOMPUTER_LOG", parse_single_num, &rows, &zErrMsg);
  if(rc) { return exit_with_error("SQL error(rows)", db); }
  printf("rows: %d, size: %d\n", rows, int(rows * profile_indexes[message_num].size() * sizeof(int)));
  fit_data.reserve(rows * profile_indexes[message_num].size() * sizeof(int));

  //get Max Lap
  rc = sqlite3_exec(db, "SELECT MAX(lap) FROM BIKECOMPUTER_LOG", parse_single_num, &max_lap, &zErrMsg);
  if(rc) { return exit_with_error("SQL error(max_lap)", db); }
  ++max_lap;
  printf("max_lap: %d\n", max_lap);

  //get log records by laps
  for(int lap_num = 0; lap_num < max_lap; ++lap_num) {
    //get log records
    message_num = 20;
    char _sql[strlen(base_sql[message_num][0].c_str())+strlen(sql_items[message_num][0].c_str())+10];
    sprintf(_sql, base_sql[message_num][0].c_str(), sql_items[message_num][0].c_str(), lap_num);
    message_num = 20;
    rc = sqlite3_exec(db, _sql, parse_records_message_num_20, NULL, &zErrMsg);
    if(rc) { return exit_with_error("SQL error(record)", db); }
    //printf("records: %d\n", (int)crc16(fit_data));

    //make lap summary
    message_num = 19;
    if(!get_summary(lap_num, db)) return false;
    //printf("lap: %d\n", (int)crc16(fit_data));
  }
  
  //make sesson summary
  message_num = 18;
  if(!get_summary(0, db)) return false;
  //printf("session: %d\n", (int)crc16(fit_data));
  
  //make activity
  message_num = 34;
  local_message_num = (local_message_num + 1)%16;
  local_num[local_message_num] = message_num;
  local_num_field[local_message_num] = {253,0,1,2,3,4,5};
  
  //get offset of localtime (use lt.tm_gmtoff)
  time_t lt_t = time(NULL);
  struct tm lt = {0};
  localtime_r(&lt_t, &lt);

  write_definition();
  get_struct_def(_size, local_message_num, false);
  _data = {
    (unsigned int)end_date_epoch,
    (unsigned int)((end_date_epoch-start_date_epoch)*1000),
    1,  //num of sessions: 1(fix)
    0,  //activity_type: general
    26, //event: activity 
    1,  //event_type: stop
    (unsigned int)(end_date_epoch + lt.tm_gmtoff)
  };
  add_fit_data(fit_data, _data, _size);
  //printf("footer: %d\n", (int)crc16(fit_data));
  
  sqlite3_close(db);

  //write fit file
  time_t startdate_local_epoch = start_date_epoch+epoch_datetime_sec+lt.tm_gmtoff;
  char startdate_local[15], filename[100], startdate_str[20];
  strftime(startdate_local, sizeof(startdate_local), "%Y%m%d%H%M%S", localtime(&startdate_local_epoch));
  strftime(startdate_str, sizeof(startdate_str), "%Y%m%d%H%M%S.fit", localtime(&startdate_local_epoch));
  sprintf(filename, "%s%s", cfg.G_LOG_DIR, startdate_str);
  
  //make file header
  std::vector<uint8_t> file_header, header_crc, total_crc;
  _data = {
    14,       // size
    0x10,     //protocol ver
    2014,     //profile ver
    (unsigned int)fit_data.size(),
    0x2E, 0x46, 0x49, 0x54 //b'.',b'F',b'I',b'T'
  };
  _size = {1,1,2,4,1,1,1,1};
  add_fit_data(file_header, _data, _size);

  //make header crc
  _data = {(unsigned int)crc16(file_header)};
  _size = {2};
  add_fit_data(header_crc, _data, _size);

  FILE *fp;
  if((fp=fopen(filename,"w")) != NULL ) {
    fwrite(file_header.data(), sizeof(uint8_t), file_header.size(), fp);
    fwrite(header_crc.data(), sizeof(uint8_t), header_crc.size(), fp);
    fwrite(fit_data.data(), sizeof(uint8_t), fit_data.size(), fp);

    //file_header+crc+write_data
    fit_data.insert(fit_data.begin(), header_crc.begin(), header_crc.end());
    fit_data.insert(fit_data.begin(), file_header.begin(), file_header.end());
    _data = {(unsigned int)crc16(fit_data)};
    //printf("crc: %d\n", (int)crc16(fit_data));

    add_fit_data(total_crc, _data, _size);
    fwrite(total_crc.data(), sizeof(uint8_t), total_crc.size(), fp);
    fclose(fp);
  }
  else { 
    fprintf(stderr, "file write error\n");
    return false;
  }
  printf("%s %s %d\n", startdate_local, filename, _data[0]);

  reset();

  cfg.G_LOG_START_DATE = (char *)malloc(sizeof(char) * strlen(startdate_local));
  strcpy(cfg.G_LOG_START_DATE, startdate_local);
  cfg.G_UPLOAD_FILE = (char *)malloc(sizeof(char) * strlen(filename));
  strcpy(cfg.G_UPLOAD_FILE, filename);

  return true;
}

int main(int argc, char *argv[]) {

  if( argc!=2 ){
    fprintf(stderr, "Usage: %s DATABASE\n", argv[0]);
    exit(1);
  }
  
  cfg.G_UNIT_ID_HEX = 0;
  const char* log_dir = "./";
  cfg.G_LOG_DIR = (char *)malloc(sizeof(char) * strlen(log_dir));
  strncpy(cfg.G_LOG_DIR, log_dir, sizeof(*cfg.G_LOG_DIR)-1);
  cfg.G_LOG_DIR[sizeof(*cfg.G_LOG_DIR) - 1] = '\0';

  bool res = !write_log_c(argv[1]);

  return (int)res;
}

