import os

try:
  import PyQt6.QtCore as QtCore
  import PyQt6.QtWidgets as QtWidgets
  import PyQt6.QtGui as QtGui
except:
  import PyQt5.QtCore as QtCore
  import PyQt5.QtWidgets as QtWidgets
  import PyQt5.QtGui as QtGui

import oyaml as yaml

class GUI_Config():

  config = None

  G_LAYOUT = {}

  G_GUI_INDEX = {
    'boot':0,
    'Main':1,
  }

  G_UNIT ={
    "HeartRate":"{:.0f}bpm",
    "Cadence":"{:.0f}rpm",
    "Speed":"{:.1f}km/h",
    "Distance":"{:.1f}km",
    "Power":"{:.0f}w",
    "Work":"{:.0f}kJ",
    "Position":"{:.5f}",
    "Altitude":"{:.0f}m",
    "Grade":"{:.0f}%",
    "GPS_error":"{:.0f}m",
    "GPS_DOP":"{:.1f}",
    "String":"{:s}",
  }

  G_ITEM_DEF = {
    #integrated
    "Power":(G_UNIT["Power"],"self.sensor.values['integrated']['power']"),
    "Speed":(G_UNIT["Speed"],"self.sensor.values['integrated']['speed']"),
    "Dist.":(G_UNIT["Distance"],"self.sensor.values['integrated']['distance']"),
    "Cad.":(G_UNIT["Cadence"],"self.sensor.values['integrated']['cadence']"),
    "HR":(G_UNIT["HeartRate"],"self.sensor.values['integrated']['heart_rate']"),
    "Work":(G_UNIT["Work"],"self.sensor.values['integrated']['accumulated_power']"),
    "W'bal":("{:.0f}kJ","self.sensor.values['integrated']['w_prime_balance']"),
    "W'bal(Norm)":("{:d}%","self.sensor.values['integrated']['w_prime_balance_normalized']"),
    "Grade":(G_UNIT["Grade"],"self.sensor.values['integrated']['grade']"),
    "Grade(spd)":(G_UNIT["Grade"],"self.sensor.values['integrated']['grade_spd']"),
    "GlideRatio":("{:.0f}m","self.sensor.values['integrated']['glide_ratio']"),
    #average_values
    "Power(3s)":(G_UNIT["Power"],"self.sensor.values['integrated']['ave_power_3s']"),
    "Power(30s)":(G_UNIT["Power"],"self.sensor.values['integrated']['ave_power_30s']"),
    "Power(60s)":(G_UNIT["Power"],"self.sensor.values['integrated']['ave_power_60s']"),
    #GPS raw
    "Latitude":(G_UNIT["Position"],"self.sensor.values['GPS']['lat']"),
    "Longitude":(G_UNIT["Position"],"self.sensor.values['GPS']['lon']"),
    "Alt.(GPS)":(G_UNIT["Altitude"],"self.sensor.values['GPS']['alt']"),
    "Speed(GPS)":(G_UNIT["Speed"],"self.sensor.values['GPS']['speed']"),
    "Dist.(GPS)":(G_UNIT["Distance"],"self.sensor.values['GPS']['distance']"),
    "Heading(GPS)":(G_UNIT["String"],"self.sensor.values['GPS']['track_str']"),
    "Satellites":(G_UNIT["String"],"self.sensor.values['GPS']['used_sats_str']"),
    "Error(x)":(G_UNIT["GPS_error"],"self.sensor.values['GPS']['epx']"),
    "Error(y)":(G_UNIT["GPS_error"],"self.sensor.values['GPS']['epy']"),
    "Error(alt)":(G_UNIT["GPS_error"],"self.sensor.values['GPS']['epv']"),
    "PDOP":(G_UNIT["GPS_DOP"],"self.sensor.values['GPS']['pdop']"),
    "HDOP":(G_UNIT["GPS_DOP"],"self.sensor.values['GPS']['hdop']"),
    "VDOP":(G_UNIT["GPS_DOP"],"self.sensor.values['GPS']['vdop']"),
    "GPSTime":(G_UNIT["String"],"self.sensor.values['GPS']['utctime']"),
    "GPS Fix":("{:d}","self.sensor.values['GPS']['mode']"),
    "Course Dist.":(G_UNIT["Distance"],"self.sensor.values['GPS']['course_distance']"),
    #ANT+ raw
    "HR(ANT+)":(G_UNIT["HeartRate"],\
      "self.sensor.values['ANT+'][self.config.G_ANT['ID_TYPE']['HR']]['heart_rate']"),
    "Speed(ANT+)":(G_UNIT["Speed"],\
      "self.sensor.values['ANT+'][self.config.G_ANT['ID_TYPE']['SPD']]['speed']"),
    "Dist.(ANT+)":(G_UNIT["Distance"],\
      "self.sensor.values['ANT+'][self.config.G_ANT['ID_TYPE']['SPD']]['distance']"),
    "Cad.(ANT+)":(G_UNIT["Cadence"],\
      "self.sensor.values['ANT+'][self.config.G_ANT['ID_TYPE']['CDC']]['cadence']"),
    #get from sensor as powermeter pairing
    # (cannot get from other pairing not including power sensor pairing)
    "Power16(ANT+)":(G_UNIT["Power"],\
      "self.sensor.values['ANT+'][self.config.G_ANT['ID_TYPE']['PWR']][0x10]['power']"),
    "Power16s(ANT+)":(G_UNIT["Power"],\
      "self.sensor.values['ANT+'][self.config.G_ANT['ID_TYPE']['PWR']][0x10]['power_16_simple']"),
    "Cad.16(ANT+)":(G_UNIT["Cadence"],\
      "self.sensor.values['ANT+'][self.config.G_ANT['ID_TYPE']['PWR']][0x10]['cadence']"),
    "Work16(ANT+)":(G_UNIT["Work"],\
      "self.sensor.values['ANT+'][self.config.G_ANT['ID_TYPE']['PWR']][0x10]['accumulated_power']"),
    "Power R(ANT+)":(G_UNIT["Power"],\
      "self.sensor.values['ANT+'][self.config.G_ANT['ID_TYPE']['PWR']][0x10]['power_r']"),
    "Power L(ANT+)":(G_UNIT["Power"],\
      "self.sensor.values['ANT+'][self.config.G_ANT['ID_TYPE']['PWR']][0x10]['power_l']"),
    "Balance(ANT+)":(G_UNIT["String"],\
      "self.sensor.values['ANT+'][self.config.G_ANT['ID_TYPE']['PWR']][0x10]['lr_balance']"),
    "Power17(ANT+)":(G_UNIT["Power"],\
      "self.sensor.values['ANT+'][self.config.G_ANT['ID_TYPE']['PWR']][0x11]['power']"),
    "Speed17(ANT+)":(G_UNIT["Speed"],\
      "self.sensor.values['ANT+'][self.config.G_ANT['ID_TYPE']['PWR']][0x11]['speed']"),
    "Dist.17(ANT+)":(G_UNIT["Distance"],\
      "self.sensor.values['ANT+'][self.config.G_ANT['ID_TYPE']['PWR']][0x11]['distance']"),
    "Work17(ANT+)":(G_UNIT["Work"],\
      "self.sensor.values['ANT+'][self.config.G_ANT['ID_TYPE']['PWR']][0x11]['accumulated_power']"),
    "Power18(ANT+)":(G_UNIT["Power"],\
      "self.sensor.values['ANT+'][self.config.G_ANT['ID_TYPE']['PWR']][0x12]['power']"),
    "Cad.18(ANT+)":(G_UNIT["Cadence"],\
      "self.sensor.values['ANT+'][self.config.G_ANT['ID_TYPE']['PWR']][0x12]['cadence']"),
    "Work18(ANT+)":(G_UNIT["Work"],\
      "self.sensor.values['ANT+'][self.config.G_ANT['ID_TYPE']['PWR']][0x12]['accumulated_power']"),
    "Torque Ef.(ANT+)":(G_UNIT["String"],\
      "self.sensor.values['ANT+'][self.config.G_ANT['ID_TYPE']['PWR']][0x13]['torque_eff']"),
    "Pedal Sm.(ANT+)":(G_UNIT["String"],\
      "self.sensor.values['ANT+'][self.config.G_ANT['ID_TYPE']['PWR']][0x13]['pedal_sm']"),
    "Light(ANT+)":(G_UNIT["String"],\
      "self.sensor.values['ANT+'][self.config.G_ANT['ID_TYPE']['LGT']]['lgt_state']"),
    #ANT+ multi
    "PWR1":(G_UNIT["Power"],"None"),
    "PWR2":(G_UNIT["Power"],"None"),
    "PWR3":(G_UNIT["Power"],"None"),
    "HR1":(G_UNIT["HeartRate"],"None"),
    "HR2":(G_UNIT["HeartRate"],"None"),
    "HR3":(G_UNIT["HeartRate"],"None"),
    #Sensor raw
    "Temp":("{:3.0f}C","self.sensor.values['integrated']['temperature']"),
    "Pressure":("{:4.0f}hPa","self.sensor.values['I2C']['pressure']"),
    "Altitude":(G_UNIT["Altitude"],"self.sensor.values['I2C']['altitude']"),
    "Humidity":("{:3.0f}%","self.sensor.values['I2C']['humidity']"),
    "Accum.Alt.":(G_UNIT["Altitude"],"self.sensor.values['I2C']['accumulated_altitude']"),
    "Vert.Spd":("{:3.1f}m/s","self.sensor.values['I2C']['vertical_speed']"),
    "Ascent":(G_UNIT["Altitude"],"self.sensor.values['I2C']['total_ascent']"),
    "Descent":(G_UNIT["Altitude"],"self.sensor.values['I2C']['total_descent']"),
    "Light":("{:.0f}","self.sensor.values['I2C']['light']"),
    "Infrared":("{:.0f}","self.sensor.values['I2C']['infrared']"),
    "UVI":("{:.0f}","self.sensor.values['I2C']['uvi']"),
    "VOC_Index":("{:.0f}","self.sensor.values['I2C']['voc_index']"),
    "Raw_Gas":("{:.0f}","self.sensor.values['I2C']['raw_gas']"),
    "Motion":("{:1.1f}","self.sensor.values['I2C']['motion']"),
    "M_Stat":("{:1.1f}","self.sensor.values['I2C']['m_stat']"),
    "ACC_X":("{:1.1f}","self.sensor.values['I2C']['acc'][0]"),
    "ACC_Y":("{:1.1f}","self.sensor.values['I2C']['acc'][1]"),
    "ACC_Z":("{:1.1f}","self.sensor.values['I2C']['acc'][2]"),
    "Battery":("{:1.0f}%","self.sensor.values['I2C']['battery_percentage']"),
    "Heading":(G_UNIT["String"],"self.sensor.values['I2C']['heading_str']"),
    "Pitch":("{:1.0f}","self.sensor.values['I2C']['modified_pitch']"),
    #General
    "Timer":("timer","self.logger.values['count']"),
    "LapTime":("timer","self.logger.values['count_lap']"),
    "Lap":("{:d}","self.logger.values['lap']"),
    "Time":("time","0"),
    "ElapsedTime":("timer","self.logger.values['elapsed_time']"),
    "GrossAveSPD":(G_UNIT["Speed"],"self.logger.values['gross_ave_spd']"),
    "GrossDiffTime":(G_UNIT["String"],"self.logger.values['gross_diff_time']"),
    "CPU_MEM":(G_UNIT["String"],"self.sensor.values['integrated']['CPU_MEM']"),
    "Send Time":(G_UNIT["String"],"self.sensor.values['integrated']['send_time']"),
    #Statistics
    #Pre Lap Average or total
    "PLap HR":(G_UNIT["HeartRate"],"self.logger.record_stats['pre_lap_avg']['heart_rate']"),
    "PLap CAD":(G_UNIT["Cadence"],"self.logger.record_stats['pre_lap_avg']['cadence']"),
    "PLap DIST":(G_UNIT["Distance"],"self.logger.record_stats['pre_lap_avg']['distance']"),
    "PLap SPD":(G_UNIT["Speed"],"self.logger.record_stats['pre_lap_avg']['speed']"),
    "PLap PWR":(G_UNIT["Power"],"self.logger.record_stats['pre_lap_avg']['power']"),
    "PLap WRK":(G_UNIT["Work"],"self.logger.record_stats['pre_lap_avg']['accumulated_power']"),
    "PLap ASC":(G_UNIT["Altitude"],"self.logger.record_stats['pre_lap_avg']['total_ascent']"),
    "PLap DSC":(G_UNIT["Altitude"],"self.logger.record_stats['pre_lap_avg']['total_descent']"),
    #Lap Average or total
    "Lap HR":(G_UNIT["HeartRate"],"self.logger.record_stats['lap_avg']['heart_rate']"),
    "Lap CAD":(G_UNIT["Cadence"],"self.logger.record_stats['lap_avg']['cadence']"),
    "Lap DIST":(G_UNIT["Distance"],"self.logger.record_stats['lap_avg']['distance']"),
    "Lap SPD":(G_UNIT["Speed"],"self.logger.record_stats['lap_avg']['speed']"),
    "Lap PWR":(G_UNIT["Power"],"self.logger.record_stats['lap_avg']['power']"),
    "Lap WRK":(G_UNIT["Work"],"self.logger.record_stats['lap_avg']['accumulated_power']"),
    "Lap ASC":(G_UNIT["Altitude"],"self.logger.record_stats['lap_avg']['total_ascent']"),
    "Lap DSC":(G_UNIT["Altitude"],"self.logger.record_stats['lap_avg']['total_descent']"),
    #Entire Average
    "Ave HR":(G_UNIT["HeartRate"],"self.logger.record_stats['entire_avg']['heart_rate']"),
    "Ave CAD":(G_UNIT["Cadence"],"self.logger.record_stats['entire_avg']['cadence']"),
    "Ave SPD":(G_UNIT["Speed"],"self.logger.record_stats['entire_avg']['speed']"),
    "Ave PWR":(G_UNIT["Power"],"self.logger.record_stats['entire_avg']['power']"),
    #Max
    "Max HR":(G_UNIT["HeartRate"],"self.logger.record_stats['entire_max']['heart_rate']"),
    "Max CAD":(G_UNIT["Cadence"],"self.logger.record_stats['entire_max']['cadence']"),
    "Max SPD":(G_UNIT["Speed"],"self.logger.record_stats['entire_max']['speed']"),
    "Max PWR":(G_UNIT["Power"],"self.logger.record_stats['entire_max']['power']"),
    "LMax HR":(G_UNIT["HeartRate"],"self.logger.record_stats['lap_max']['heart_rate']"),
    "LMax CAD":(G_UNIT["Cadence"],"self.logger.record_stats['lap_max']['cadence']"),
    "LMax SPD":(G_UNIT["Speed"],"self.logger.record_stats['lap_max']['speed']"),
    "LMax PWR":(G_UNIT["Power"],"self.logger.record_stats['lap_max']['power']"),
    "PLMax HR":(G_UNIT["HeartRate"],"self.logger.record_stats['pre_lap_max']['heart_rate']"),
    "PLMax CAD":(G_UNIT["Cadence"],"self.logger.record_stats['pre_lap_max']['cadence']"),
    "PLMax SPD":(G_UNIT["Speed"],"self.logger.record_stats['pre_lap_max']['speed']"),
    "PLMax PWR":(G_UNIT["Power"],"self.logger.record_stats['pre_lap_max']['power']")
  }

  G_LANG = {
    "JA": {
      "Power":"パワー",
      "Speed":"スピード",
      "Dist.":"距離",
      "Cad.":"ケイデンス",
      "HR":"心拍",
      "Work":"仕事量",
      "Timer":"タイマー",
      "Ascent":"獲得標高",
      #"":"",
    },
  }

  def __init__(self, config):
    self.config = config
    
    #read layout
    if os.path.exists(self.config.G_LAYOUT_FILE):
      self.read_layout()
    
    self.icon_dir = ""
    if self.config.G_IS_RASPI:
      self.icon_dir = self.config.G_INSTALL_PATH

  def set_qt5_or_qt6_constants(self, USE_PYQT6):
    self.key_space = QtCore.Qt.Key.Key_Space if USE_PYQT6 else QtCore.Qt.Key_Space
    self.key_press = QtCore.QEvent.Type.KeyPress if USE_PYQT6 else QtCore.QEvent.KeyPress
    self.key_release = QtCore.QEvent.Type.KeyRelease if USE_PYQT6 else QtCore.QEvent.KeyRelease
    self.no_modifier = QtCore.Qt.KeyboardModifier.NoModifier if USE_PYQT6 else QtCore.Qt.NoModifier

    self.align_left = QtCore.Qt.AlignmentFlag.AlignLeft if USE_PYQT6 else QtCore.Qt.AlignLeft
    self.align_center = QtCore.Qt.AlignmentFlag.AlignCenter if USE_PYQT6 else QtCore.Qt.AlignCenter
    self.align_h_center = QtCore.Qt.AlignmentFlag.AlignHCenter if USE_PYQT6 else QtCore.Qt.AlignHCenter
    self.align_v_center = QtCore.Qt.AlignmentFlag.AlignVCenter if USE_PYQT6 else QtCore.Qt.AlignVCenter
    self.align_right = QtCore.Qt.AlignmentFlag.AlignRight if USE_PYQT6 else QtCore.Qt.AlignRight
    self.align_bottom = QtCore.Qt.AlignmentFlag.AlignBottom if USE_PYQT6 else QtCore.Qt.AlignBottom
    self.align_top = QtCore.Qt.AlignmentFlag.AlignTop if USE_PYQT6 else QtCore.Qt.AlignTop
    self.expanding = QtWidgets.QSizePolicy.Policy.Expanding if USE_PYQT6 else QtWidgets.QSizePolicy.Expanding
    self.fixed = QtWidgets.QSizePolicy.Policy.Fixed if USE_PYQT6 else QtWidgets.QSizePolicy.Fixed

    self.no_focus = QtCore.Qt.FocusPolicy.NoFocus if USE_PYQT6 else QtCore.Qt.NoFocus
    self.strong_focus = QtCore.Qt.FocusPolicy.StrongFocus if USE_PYQT6 else QtCore.Qt.StrongFocus
    self.tab_focus_reason = QtCore.Qt.FocusReason.TabFocusReason if USE_PYQT6 else QtCore.Qt.TabFocusReason
    self.backtab_focus_reason = QtCore.Qt.FocusReason.BacktabFocusReason if USE_PYQT6 else QtCore.Qt.BacktabFocusReason

    self.scrollbar_alwaysoff = QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff if USE_PYQT6 else QtCore.Qt.ScrollBarAlwaysOff
    self.qtextedit_nowrap = QtWidgets.QTextEdit.LineWrapMode.NoWrap if USE_PYQT6 else QtWidgets.QTextEdit.NoWrap

    self.stackingmode_stackone = QtWidgets.QStackedLayout.StackingMode.StackOne if USE_PYQT6 else QtWidgets.QStackedLayout.StackOne
    self.stackingmode_stackall = QtWidgets.QStackedLayout.StackingMode.StackAll if USE_PYQT6 else QtWidgets.QStackedLayout.StackAll
    
    self.PE_Widget = QtWidgets.QStyle.PrimitiveElement.PE_Widget if USE_PYQT6 else QtWidgets.QStyle.PE_Widget
    self.WA_TranslucentBackground = QtCore.Qt.WidgetAttribute.WA_TranslucentBackground if USE_PYQT6 else QtCore.Qt.WA_TranslucentBackground
    self.WA_TransparentForMouseEvents = QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents if USE_PYQT6 else QtCore.Qt.WA_TransparentForMouseEvents

    #for draw_display
    self.format_rgb888 = QtGui.QImage.Format.Format_RGB888 if USE_PYQT6 else QtGui.QImage.Format_RGB888
    self.format_mono = QtGui.QImage.Format.Format_Mono if USE_PYQT6 else QtGui.QImage.Format_Mono
    if self.config.display.has_color():
      self.format = self.format_rgb888
    else:
      self.format = self.format_mono

  def get_screen_shape(self, p):
    screen_shape = None
    remove_bytes = 0
    if self.config.display.has_color():
      screen_shape = (p.height(), p.width(), 3)
    else:
      screen_shape = (p.height(), int(p.width()/8))
      remove_bytes = p.bytesPerLine() - int(p.width()/8)
    return screen_shape, remove_bytes
  
  def read_layout(self):
    text = None
    with open(self.config.G_LAYOUT_FILE) as file:
      text = file.read()
      self.G_LAYOUT = yaml.safe_load(text)

