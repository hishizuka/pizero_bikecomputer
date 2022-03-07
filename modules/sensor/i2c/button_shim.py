import buttonshim


#button functions
_FUNC = {
  'A': None, 'A_LONG': None,
  'B': None, 'B_LONG': None,
  'C': None, 'C_LONG': None,
  'D': None, 'D_LONG': None,
  'E': None, 'E_LONG': None,
}

#access from decorator
_HOLD_STATUS = {
  'A': False,
  'B': False,
  'C': False,
  'D': False,
  'E': False,
}


class ButtonShim():

  config = None

  def __init__(self, config):
    self.config = config
    buttonshim.set_pixel(0x00, 0x00, 0x00)
    #update hold_time of buttons
    for b in buttonshim._handlers:
      b.hold_time = self.config.button_config.G_BUTTON_LONG_PRESS
    global _FUNC
    _FUNC['A'] = self.press_A
    _FUNC['A_LONG'] = self.press_A_LONG
    _FUNC['B'] = self.press_B
    _FUNC['B_LONG'] = self.press_B_LONG
    _FUNC['C'] = self.press_C
    _FUNC['C_LONG'] = self.press_C_LONG
    _FUNC['D'] = self.press_D
    _FUNC['D_LONG'] = self.press_D_LONG
    _FUNC['E'] = self.press_E
    _FUNC['E_LONG'] = self.press_E_LONG
  
  def press_button(self, button, index):
    self.config.press_button('Button_Shim', button, index)

  def press_A(self):
    self.press_button('A', 0)
  def press_A_LONG(self):
    self.press_button('A', 1)
  def press_B(self):
    self.press_button('B', 0)
  def press_B_LONG(self):
    self.press_button('B', 1)
  def press_C(self):
    self.press_button('C', 0)
  def press_C_LONG(self):
    self.press_button('C', 1)
  def press_D(self):
    self.press_button('D', 0)
  def press_D_LONG(self):
    self.press_button('D', 1)
  def press_E(self):
    self.press_button('E', 0)
  def press_E_LONG(self):
    self.press_button('E', 1)


  # Button A
  @buttonshim.on_press(buttonshim.BUTTON_A)
  def press_handler_a(button, pressed):
    global _HOLD_STATUS
    _HOLD_STATUS['A'] = False

  @buttonshim.on_release(buttonshim.BUTTON_A)
  def release_handler_a(button, pressed):
    global _FUNC
    if not _HOLD_STATUS['A']:
      _FUNC['A']()

  @buttonshim.on_hold(buttonshim.BUTTON_A)
  def hold_handler_a(button):
    global _HOLD_STATUS, _FUNC
    _HOLD_STATUS['A'] = True
    _FUNC['A_LONG']()

  # Button B
  @buttonshim.on_press(buttonshim.BUTTON_B)
  def press_handler_b(button, pressed):
    global _HOLD_STATUS
    _HOLD_STATUS['B'] = False

  @buttonshim.on_release(buttonshim.BUTTON_B)
  def release_handler_b(button, pressed):
    global _FUNC
    if not _HOLD_STATUS['B']:
      _FUNC['B']()

  @buttonshim.on_hold(buttonshim.BUTTON_B)
  def hold_handler_b(button):
    global _HOLD_STATUS, _FUNC
    _HOLD_STATUS['B'] = True
    _FUNC['B_LONG']()

  # Button C
  @buttonshim.on_press(buttonshim.BUTTON_C)
  def press_handler_c(button, pressed):
    global _HOLD_STATUS
    _HOLD_STATUS['C'] = False

  @buttonshim.on_release(buttonshim.BUTTON_C)
  def release_handler_c(button, pressed):
    global _FUNC
    if not _HOLD_STATUS['C']:
      _FUNC['C']()

  @buttonshim.on_hold(buttonshim.BUTTON_C)
  def hold_handler_c(button):
    global _HOLD_STATUS, _FUNC
    _HOLD_STATUS['C'] = True
    _FUNC['C_LONG']()

  # Button D
  @buttonshim.on_press(buttonshim.BUTTON_D)
  def press_handler_d(button, pressed):
    global _HOLD_STATUS
    _HOLD_STATUS['D'] = False

  @buttonshim.on_release(buttonshim.BUTTON_D)
  def release_handler_d(button, pressed):
    global _FUNC
    if not _HOLD_STATUS['D']:
      _FUNC['D']()

  @buttonshim.on_hold(buttonshim.BUTTON_D)
  def hold_handler_d(button):
    global _HOLD_STATUS, _FUNC
    _HOLD_STATUS['D'] = True
    _FUNC['D_LONG']()

  # Button E
  @buttonshim.on_press(buttonshim.BUTTON_E)
  def press_handler_e(button, pressed):
    global _HOLD_STATUS
    _HOLD_STATUS['E'] = False

  @buttonshim.on_release(buttonshim.BUTTON_E)
  def release_handler_e(button, pressed):
    global _FUNC
    if not _HOLD_STATUS['E']:
      _FUNC['E']()

  @buttonshim.on_hold(buttonshim.BUTTON_E)
  def hold_handler_e(button):
    global _HOLD_STATUS, _FUNC
    _HOLD_STATUS['E'] = True
    _FUNC['E_LONG']()

