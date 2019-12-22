import sqlite3
import time
import datetime


class config_local():
  G_LOG_DB = "./log.db~"
  G_LOG_DIR = "./"
  G_PRODUCT = "Pizero Bikecomputer"
  G_VERSION_MAJOR = 0
  G_VERSION_MINOR = 1
  G_UNIT_ID = "0000000000000000"


class LoggerTcx():
  
  config = None

  #for DB
  con = None
  cur = None
  
  def __init__(self, config):
    self.config = config
    
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
    filename = self.config.G_LOG_DIR + self.config.G_LOG_START_DATE + ".tcx"

    #get Max Laps
    cur.execute("SELECT MAX(LAP) FROM BIKECOMPUTER_LOG")
    max_lap = (cur.fetchone())[0]
    
    #write header
    f = open(filename, "w", encoding="UTF-8")
    buf = \
"""<?xml version="1.0" encoding="UTF-8"?>
<TrainingCenterDatabase
 xsi:schemaLocation="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2 http://www.garmin.com/xmlschemas/TrainingCenterDatabasev2.xsd"
 xmlns:ns5="http://www.garmin.com/xmlschemas/ActivityGoals/v1"
 xmlns:ns3="http://www.garmin.com/xmlschemas/ActivityExtension/v2"
 xmlns:ns2="http://www.garmin.com/xmlschemas/UserProfile/v2"
 xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:ns4="http://www.garmin.com/xmlschemas/ProfileExtension/v1">
 <Activities>
  <Activity Sport="Biking">
"""
    f.write(buf)
    buf = \
"""   <Id>%s</Id>
""" % (first_row[0])
    f.write(buf)

    #Write out by Lap
    for lap_num in range(max_lap+1):

      # get 1st Record
      cur.execute("SELECT timestamp FROM BIKECOMPUTER_LOG WHERE LAP = %s LIMIT 1" % lap_num)
      lap_first_row = cur.fetchone()

      #get statistics
        
      # TotalTimeSeconds
      cur.execute("SELECT MIN(TIMER) FROM BIKECOMPUTER_LOG WHERE LAP = %s" % lap_num)
      min_timer = (cur.fetchone())[0]
      cur.execute("SELECT MAX(TIMER) FROM BIKECOMPUTER_LOG WHERE LAP = %s" % lap_num)
      max_timer = (cur.fetchone())[0]
      timer = max_timer - min_timer
      # DistanceMeters
      cur.execute("SELECT MIN(DISTANCE) FROM BIKECOMPUTER_LOG WHERE LAP = %s" % lap_num)
      min_dist = (cur.fetchone())[0]
      cur.execute("SELECT MAX(DISTANCE) FROM BIKECOMPUTER_LOG WHERE LAP = %s" % lap_num)
      max_dist = (cur.fetchone())[0]
      dist = None
      #unit: km -> m
      #if min_dist != None and max_dist != None: dist = (max_dist - min_dist)*1000
      #unit: m
      if min_dist != None and max_dist != None: dist = (max_dist - min_dist)
      
      each_stats = {\
       'max_speed':["MAX(speed)",None],\
       'avg_speed':["AVG(speed)",None],\
       'max_hr':["MAX(heart_rate)",None],\
       'avg_hr':["AVG(heart_rate)",None],\
       'max_cad':["MAX(cadence)",None],\
       'avg_cad':["AVG(cadence)",None],\
       'max_power':["MAX(power)",None],\
       'avg_power':["AVG(power)",None]\
      }
      for k,v in each_stats.items():
        cur.execute("SELECT %s FROM BIKECOMPUTER_LOG WHERE LAP = %s" % (v[0],lap_num))
        value = (cur.fetchone())[0]
        if value != None:
          v[1] = int(value)
          ##if k.find("speed") == -1: v[1] = int(v[1])
          #if "speed" not in k: v[1] = int(v[1])
          ##else: v[1] = v[1]/3.6 #from km/h to m/s
          #else: v[1] = v[1] #unit: m/s
      
      buf = \
"""   <Lap StartTime="%s">
    <TotalTimeSeconds>%f</TotalTimeSeconds>
""" % (lap_first_row[0],timer)
      if dist != None: buf = buf + \
"""    <DistanceMeters>%f</DistanceMeters>
""" % (dist)
      if each_stats['max_speed'][1] != None: buf = buf + \
"""    <MaximumSpeed>%f</MaximumSpeed>
""" % (each_stats['max_speed'][1])
      if each_stats['avg_hr'][1] != None: buf = buf + \
"""    <AverageHeartRateBpm>
     <Value>%d</Value>
    </AverageHeartRateBpm>
""" % (each_stats['avg_hr'][1])
      if each_stats['max_hr'][1] != None: buf = buf + \
"""    <MaximumHeartRateBpm>
     <Value>%d</Value>
    </MaximumHeartRateBpm>
""" % (each_stats['max_hr'][1])
      buf = buf + \
"""    <Intensity>Active</Intensity>
"""
      if each_stats['avg_cad'][1] != None: buf = buf + \
"""    <Cadence>%d</Cadence>
""" % (each_stats['avg_cad'][1])
      buf = buf + \
"""    <TriggerMethod>Manual</TriggerMethod>
    <Track>
"""
      f.write(buf)

      # get Lap Records
      r = "lap,timer,timestamp,heart_rate,speed,cadence,power,distance,accumulated_power,position_lat,position_long,altitude"
      for row in cur.execute("SELECT %s FROM BIKECOMPUTER_LOG WHERE LAP = %s" % (r,lap_num)):
        buf = \
"""     <Trackpoint>
      <Time>%s</Time>
""" % (row[2])
        if row[9] != None and row[10] != None: buf = buf +\
"""      <Position>
       <LatitudeDegrees>%s</LatitudeDegrees>
       <LongitudeDegrees>%s</LongitudeDegrees>
      </Position>
""" % (row[9],row[10])
        if row[11] != None: buf = buf +\
"""      <AltitudeMeters>%s</AltitudeMeters>
""" % (row[11])
        if row[7] != None: buf = buf +\
"""      <DistanceMeters>%s</DistanceMeters>
""" % (row[7]) #(float(row[7])*1000)
        if row[3] != None: buf = buf +\
"""      <HeartRateBpm>
       <Value>%s</Value>
      </HeartRateBpm>
""" % (row[3])
        if row[5] != None: buf = buf +\
"""      <Cadence>%s</Cadence>
""" % (row[5])
        if row[4] != None or row[6] != None:
          buf = buf +\
"""      <Extensions>
       <ns3:TPX>
"""
          if row[4] != None: buf = buf +\
"""        <ns3:Speed>%f</ns3:Speed>
""" % (row[4]) #(float(row[4])/3.6)
          if row[6] != None: buf = buf +\
"""        <ns3:Watts>%s</ns3:Watts>
""" % (row[6])
          buf = buf +\
"""       </ns3:TPX>
      </Extensions>
"""
        buf = buf +\
"""     </Trackpoint>
"""
        f.write(buf)
        #print(row)
      
      # End of Lap(statistics)
      buf = \
"""    </Track>
"""
      if each_stats['avg_speed'][1] != None or\
        each_stats['max_cad'][1] != None or\
        each_stats['avg_power'][1] != None or\
        each_stats['max_power'][1] != None:
        buf = buf + \
"""    <Extensions>
     <ns3:LX>
"""
        if each_stats['avg_speed'][1] != None: buf = buf + \
"""      <ns3:AvgSpeed>%f</ns3:AvgSpeed>
""" % (each_stats['avg_speed'][1])
        if each_stats['max_cad'][1] != None: buf = buf + \
"""      <ns3:MaxBikeCadence>%d</ns3:MaxBikeCadence>
""" % (each_stats['max_cad'][1])
        if each_stats['avg_power'][1] != None: buf = buf + \
"""      <ns3:AvgWatts>%d</ns3:AvgWatts>
""" % (each_stats['avg_power'][1])
        if each_stats['max_power'][1] != None: buf = buf + \
"""      <ns3:MaxWatts>%d</ns3:MaxWatts>
""" % (each_stats['max_power'][1])
        buf = buf + \
"""     </ns3:LX>
    </Extensions>
"""
      buf = buf + \
"""   </Lap>
"""
      f.write(buf)
    
    # End of File
    buf = \
"""   <Creator xsi:type="Device_t">
    <Name>%s</Name>
    <UnitId>%s</UnitId>
    <ProductID>001</ProductID>
    <Version>
     <VersionMajor>%s</VersionMajor>
     <VersionMinor>%s</VersionMinor>
     <BuildMajor>0</BuildMajor>
     <BuildMinor>0</BuildMinor>
    </Version>
   </Creator>
  </Activity>
 </Activities>
</TrainingCenterDatabase>
""" % (\
     self.config.G_PRODUCT, \
     self.config.G_UNIT_ID, \
     self.config.G_VERSION_MAJOR, \
     self.config.G_VERSION_MINOR\
    )
    f.write(buf)

    f.close()
    cur.close() 
    con.close() 
    
    #success
    return True


if __name__=="__main__":
    c = config_local()
    t = LoggerTcx(c)
    t.write_log()
