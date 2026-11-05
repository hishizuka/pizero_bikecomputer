import asyncio
from dataclasses import dataclass
from pathlib import Path
import struct

from modules.app_logger import app_logger
from modules.qt._qt_constants import Signal, Slot
from modules.qt._qt_ver import QtCore, QtGui, USE_PYSIDE6

Property = QtCore.Property if USE_PYSIDE6 else QtCore.pyqtProperty

FONT_EXTENSIONS = {".ttf", ".otf", ".ttc", ".otc"}
WEIGHT_NAMES = {
    100: "Thin",
    200: "ExtraLight",
    300: "Light",
    400: "Regular",
    500: "Medium",
    600: "SemiBold",
    700: "Bold",
    800: "ExtraBold",
    900: "Black",
}
DEFAULT_LABEL = "Default (unspecified)"


def list_font_files(directory):
    return sorted(
        (
            path.relative_to(directory).as_posix()
            for path in directory.rglob("*")
            if path.is_file() and path.suffix.lower() in FONT_EXTENSIONS
        ),
        key=str.casefold,
    )


def font_weights(raw_font):
    table = bytes(raw_font.fontTable("fvar"))
    if table:
        _, _, offset, _, axis_count, axis_size, count, size = struct.unpack_from(
            ">8H", table
        )
        for index in range(axis_count):
            tag, minimum, default, maximum = struct.unpack_from(
                ">4siii", table, offset + index * axis_size
            )
            if tag != b"wght":
                continue
            weights = {
                weight
                for weight in WEIGHT_NAMES
                if minimum <= weight * 65536 <= maximum
            }
            weights.add(round(default / 65536))
            for instance in range(count):
                # Instance coordinates follow a four-byte header in axis order.
                coordinate = offset + axis_count * axis_size + instance * size
                weight = struct.unpack_from(">i", table, coordinate + 4 + index * 4)[0]
                weights.add(round(weight / 65536))
            return tuple(sorted(weights))
    return (raw_font.weight(),)


@dataclass(frozen=True)
class FontFace:
    family: str
    style: QtGui.QFont.Style
    weights: tuple[int, ...]


class FontManager(QtCore.QObject):
    changed = Signal()
    applied = Signal(str)
    files_loaded = Signal()

    def __init__(self, config, app, parent=None):
        super().__init__(parent)
        self.config = config
        self.app = app
        self.directory = Path.cwd() / "fonts"
        self._default_font = QtGui.QFont(app.font())
        self._faces = {}
        self._files = {}
        self._busy = False
        self._error = ""
        self._load_task = None

    @Property("QVariantMap", notify=changed)
    def state(self):
        return {
            "file": self.config.G_FONT_FILE,
            "weight": self.config.G_FONT_WEIGHT,
            "busy": self._busy,
            "error": self._error,
        }

    @Property("QVariantList", notify=changed)
    def files(self):
        return [{"title": k, "value": v} for k, v in self._files.items()]

    @Property("QVariantList", notify=changed)
    def weights(self):
        return [
            {"title": k, "value": v}
            for k, v in self.weight_options(self.config.G_FONT_FILE).items()
        ]

    def face(self, filename):
        if filename not in self._faces:
            path = str((self.directory / filename).resolve())
            raw = QtGui.QRawFont(path, 16)
            if not raw.isValid():
                raise ValueError(f"Cannot load font: {filename}")
            font_id = QtGui.QFontDatabase.addApplicationFont(path)
            if font_id == -1:
                raise ValueError(f"Cannot register font: {filename}")
            self._faces[filename] = FontFace(
                QtGui.QFontDatabase.applicationFontFamilies(font_id)[0],
                raw.style(),
                font_weights(raw),
            )
        return self._faces[filename]

    def weight_options(self, filename):
        weights = self.face(filename).weights if filename else tuple(WEIGHT_NAMES)
        return {DEFAULT_LABEL: None} | {
            (
                f"{weight} ({WEIGHT_NAMES[weight]})"
                if weight in WEIGHT_NAMES
                else str(weight)
            ): weight
            for weight in weights
        }

    @Slot()
    def preprocess(self):
        self.cancel_loading()
        self._files = {}
        self._error = ""
        self.changed.emit()
        self._load_task = asyncio.create_task(self._load_files())

    def cancel_loading(self):
        if self._load_task is not None:
            self._load_task.cancel()

    async def _load_files(self):
        try:
            files = await asyncio.to_thread(list_font_files, self.directory)
            self._files = {"Default": "", **{name: name for name in files}}
        except OSError as error:
            self._error = str(error)
        self.changed.emit()
        self.files_loaded.emit()

    def apply(self):
        filename, weight = self.config.G_FONT_FILE, self.config.G_FONT_WEIGHT
        if filename:
            face = self.face(filename)
            font = QtGui.QFont(face.family)
            font.setStyle(face.style)
        else:
            font = QtGui.QFont(self._default_font)
        if weight is not None:
            font.setStyleName("")
            font.setWeight(QtGui.QFont.Weight(weight))
        self.app.setFont(font)

    @Slot(str, "QVariant")
    def trigger(self, kind, value):
        asyncio.create_task(self.choose(kind, value))

    async def choose(self, kind, value):
        if self._busy:
            return False
        previous = self.config.G_FONT_FILE, self.config.G_FONT_WEIGHT
        previous_font = QtGui.QFont(self.app.font())
        self._busy, self._error = True, ""
        self.changed.emit()
        try:
            filename, weight = previous
            if kind == "file":
                filename = value
                if weight not in self.weight_options(filename).values():
                    weight = None
            else:
                weight = value
            self.config.G_FONT_FILE, self.config.G_FONT_WEIGHT = filename, weight
            self.apply()
            await asyncio.to_thread(self.config.setting.write_config)
        except (OSError, ValueError) as error:
            self.config.G_FONT_FILE, self.config.G_FONT_WEIGHT = previous
            self.app.setFont(previous_font)
            app_logger.exception("Font change failed")
            self._error = str(error)
            return False
        finally:
            self._busy = False
            self.changed.emit()
        self.applied.emit(kind)
        return True
