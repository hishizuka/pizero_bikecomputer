#ifndef __LOGGER_FIT_C
#define __LOGGER_FIT_C

#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include <cstring>
#include <string>
#include <algorithm>
#include <vector>
#include <unordered_map>

//sudo apt-get install libsqlite3-dev
#include <sqlite3.h>

static std::vector<uint8_t> fit_data;

static  int message_num, local_message_num;

static  std::unordered_map<int, std::vector<int> > profile_indexes;
//for lap and session, divide profile_indexes into 2 group
static std::unordered_map<int, std::vector<std::vector<int> > > sql_indexes;
static std::unordered_map<int, std::unordered_map<int, std::vector<std::string> > > profile_name_type;
static std::unordered_map<int, std::unordered_map<int, int> > data_scale;

static std::unordered_map<int, int> local_num;
static std::unordered_map<int, std::vector<int> > struct_def_cache;
static std::unordered_map<int, std::vector<int> > local_num_field;
static std::unordered_map<std::string, uint8_t> base_type_id;
static std::vector<int> base_type_size;

static std::unordered_map<int, std::unordered_map<int, std::string> > sql;
static std::unordered_map<int, std::vector<std::string> > sql_items;
static std::unordered_map<int, std::vector<std::string> > base_sql;

static time_t epoch_datetime_sec;

struct lap_summary_data{
  bool is_null = false;
  std::string data;
};

struct config {
  unsigned int G_UNIT_ID_HEX = 0;
  char* G_LOG_START_DATE;
  char* G_LOG_DIR;
  char* G_UPLOAD_FILE;
};
static config cfg;

constexpr double LAT_LON_CONST = ((unsigned int)(1 << 31))/180.0; //pow(2,31) / 180;


void set_config_c(const config& _cfg);
void reset();
char* get_upload_file_name_c();
char* get_start_date_str_c();

inline uint8_t base_type_id_from_string(std::string base_type_name) {
  return base_type_id[base_type_name];
}
inline uint8_t base_type_size_from_id(uint8_t base_type_id) {
  return base_type_size[base_type_id & 0xf];
}

bool exit_with_error(const char* message, sqlite3* db);
unsigned int crc16(std::vector<uint8_t>& data);

unsigned int convert_value(const char* value_str, const int data_type);

static int parse_single_str(void *user_data, int argc, char **argv, char **azColName);
static int parse_single_num(void *user_data, int argc, char **argv, char **azColName);

void add_fit_data(std::vector<uint8_t>& _bytes, std::vector<int>& _data, std::vector<int>& _size);
void get_struct_def(std::vector<int>& _size, int l_num, bool l_num_used);
int get_local_message_num(std::vector<int>& available_fields);
void write_definition();

static int parse_records_message_num_18_19(void *user_data, int argc, char **argv, char **azColName);
static int parse_records_message_num_20(void *user_data, int argc, char **argv, char **azColName);

bool get_summary(int lap_num, sqlite3 *db);

bool write_log_c(const char* db_file);

int main(int argc, char *argv[]);

#endif
