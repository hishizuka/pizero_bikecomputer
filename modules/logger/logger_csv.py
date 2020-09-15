import sqlite3
import time
import datetime

from .logger import Logger


class config_local():
  G_LOG_DB = "./log.db~"
  G_LOG_DIR = "./"
  G_PRODUCT = "Pizero BIKECOMPUTER"
  G_VERSION_MAJOR = 0
  G_VERSION_MINOR = 1
  G_UNIT_ID = "0000000000000000"


class LoggerCsv(Logger):

  def write_log(self):
    
    #get start date
    start_date = None
    start_date_str = "errordate"
    ## SQLite
    con = sqlite3.connect(self.config.G_LOG_DB)
    cur = con.cursor()
    cur.execute("SELECT timestamp,MAX(timestamp) FROM BIKECOMPUTER_LOG LIMIT 1")
    #cur.execute("SELECT timestamp FROM BIKECOMPUTER_LOG LIMIT 1")
    first_row = cur.fetchone()
    if first_row != None:
      start_date = self.config.datetime_myparser(first_row[0])
      start_date_str = start_date.strftime("%Y%m%d%H%M%S")
    else:
      return False
    
    offset = time.localtime().tm_gmtoff
    startdate_local = start_date + datetime.timedelta(seconds=offset)
    self.config.G_LOG_START_DATE = startdate_local.strftime("%Y%m%d%H%M%S")
    filename = self.config.G_LOG_DIR + self.config.G_LOG_START_DATE + ".csv"

    #file open
    f = open(filename, "w", encoding="UTF-8")
    # get Lap Records
    r = "\
lap,timer,timestamp,heart_rate,speed,cadence,power,distance,accumulated_power,\
position_lat,position_long,altitude,gps_altitude,gps_distance,gps_mode,gps_used_sats,gps_total_sats,\
total_ascent,total_descent,pressure,temperature,heading,gps_track,motion,acc_x,acc_y,acc_z,\
voltage_battery,current_battery,voltage_out,current_out,battery_percentage\
"
    f.write(r+"\n")
    for row in cur.execute("SELECT %s FROM BIKECOMPUTER_LOG" % r):
      f.write(','.join(map(str, row))+"\n")
    
    f.close()
    cur.close()
    con.close()

    #success
    return True

if __name__=="__main__":
    c = config_local()
    d = LoggerCsv(c)
    d.write_log()
