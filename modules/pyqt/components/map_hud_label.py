from modules._qt_qtwidgets import QtCore, QtGui, QtWidgets


class MapHudLabel(QtWidgets.QLabel):
    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setStyleSheet("background: transparent;")
        self.setMargin(0)
        self.setContentsMargins(0, 0, 0, 0)
        self._image_key = None
        self.hide()

    def set_image(self, image):
        if self._image_key == image.cacheKey():
            return
        self.setPixmap(QtGui.QPixmap.fromImage(image))
        size = image.deviceIndependentSize()
        self.setFixedSize(round(size.width()), round(size.height()))
        self._image_key = image.cacheKey()

    def clear(self):
        self._image_key = None
        super().clear()
