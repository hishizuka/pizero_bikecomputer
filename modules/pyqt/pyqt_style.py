
class PyQtStyle():

  #PyQt button style
  #G_GUI_PYQT_buttonStyle_black = '''
  #  QPushButton{
  #  background-color: #222222;
  #  color: white;
  #  border-color: white;
  #  border-radius: 15px;
  #  border-style: outset;
  #  border-width: 0px;
  #  }
  #  QPushButton:pressed{background-color: white;}
  #'''
  #G_GUI_PYQT_buttonStyle_white = '''
  #  QPushButton{
  #  background-color: #FFFFFF;
  #  color: black;
  #  border-color: black;
  #  border-radius: 15px;
  #  border-style: outset;
  #  border-width: 0px;
  #  }
  #  QPushButton:pressed{background-color: black;}
  #'''

  G_GUI_PYQT_splash_screen = '''
    background-color: black;
  '''

  G_GUI_PYQT_splash_boot_text = '''
    color: white;
    font-size: 20px;
  '''

  G_GUI_PYQT_button_box = '''
    background-color: #CCCCCC;
  '''

  G_GUI_PYQT_buttonStyle_navi = '''
    QPushButton{
      color: none;
      border: 0px solid #FFFFFF;
      border-radius: 15px;
      outline: 0;
    }
    QPushButton:pressed{ background-color: white; }
    QPushButton[style='menu']:focus{ border-color: white; border-width: 3px; }
  '''

  G_GUI_PYQT_buttonStyle_gotoMenu = '''
    QPushButton{
      color: none;
      border-color: none;
      border-radius: 2px;
      border-style: outset;
      border-width: 0px;
    }
    QPushButton:pressed{background-color: white;}
  '''

  G_GUI_PYQT_buttonStyle_timer = '''
    QPushButton{
      background-color: #FF0000;
      color: black;
      border-color: red;
      border-radius: 15px;
      border-style: outset;
      border-width: 0px;
    }
    QPushButton:pressed{background-color: white;}
  '''

  G_GUI_PYQT_menu_topbar = '''
    background-color: #00AA00
  '''

  G_GUI_PYQT_menu_topbar_page_name_label = '''
    color: #FFFFFF;
  '''

  G_GUI_PYQT_menu_topbar_next_button = '''
    border: none;
  '''

  G_GUI_PYQT_buttonStyle_menu = """
    QPushButton{
      border-color: #AAAAAA;
      border-style: outset;
      border-width: 0px 1px 1px 0px;
      text-align: left;
      padding-left: 15%;
    }
    QPushButton:pressed{background-color: black; }
    QPushButton:focus{background-color: black; color: white; }
    QPushButton[style='connect']{ 
      text-align: center;
      padding-left: 0;
      border-width: 1px 0px 0px 0px;
      border-style: solid;
    }
    QPushButton[style='dummy']{ border-width: 0px; }
    QPushButton[style='unavailable']{ color: #AAAAAA; }
  """

  G_GUI_PYQT_menu_list_border = '''
    border-bottom: 1px solid #AAAAAA;
  '''

  G_GUI_PYQT_buttonStyle = '''
    QPushButton{
      border-radius: 15px;
      border-style: outset;
      border-width: 1px;
    }
    QPushButton:pressed{background-color: black;}
  '''
  
  G_GUI_PYQT_buttonStyle_map = '''
    QPushButton{
      border-radius: 15px;
      border-style: outset;
      border-width: 1px;
      font-size: 25px;
      color: rgba(0, 0, 0, 192);
      background: rgba(255, 255, 255, 128);
    }
    QPushButton:pressed{background-color: rgba(0, 0, 0, 128);}
  '''
  
  G_GUI_PYQT_buttonStyle_adjustwidget = '''
    QPushButton{
      font-size: 15px;
      padding: 2px;
      margin: 1px
    }
    QPushButton:pressed{background-color: black;}
    QPushButton:focus{background-color: black; color: white; }
  '''
  G_GUI_PYQT_texteditStyle_adjustwidget = '''
    QLineEdit{
      font-size: 35px;
      padding: 5px;
    }
  '''
  G_GUI_PYQT_labelStyle_adjustwidget = '''
    QLabel{ 
      font-size: 25px;
      padding: 5px;
    }
  '''
  G_GUI_PYQT_dialog = '''
    #background {
      /* transparent black */
      background-color: rgba(0, 0, 0, 64);
      /* transparent white */
      /*
        background-color: rgba(255, 255, 255, 128);
      */
    }
    Container {
      border: 3px solid black;
      border-radius: 5px;
      padding: 15px;
    }
    Container DialogButton{
      border: 2px solid #AAAAAA;
      border-radius: 3px;
      text-align: center;
    }
    Container DialogButton:pressed{background-color: black; }
    Container DialogButton:focus{background-color: black; color: white; }
  '''
  G_GUI_PYQT_item = '''
    border-style: solid;
    border-color: #AAAAAA;
  '''
