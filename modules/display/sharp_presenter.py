"""Sharp DRM DMA-BUF presenter binding shared by Qt frontends."""

import ctypes
import os
from pathlib import Path

RENDER_NODE = "/dev/dri/by-path/platform-soc:gpu-render"
VC4_CARD = "/dev/dri/by-path/platform-soc:gpu-card"
SHARP_CARD = "/dev/dri/by-path/platform-3f204000.spi-cs-0-card"
DMABUF_LIBRARY = "/usr/local/lib/libsharp_presenter.so"


def presenter_paths():
    return {
        "render_node": Path(os.environ.get("PIZERO_QML_RENDER_NODE", RENDER_NODE)),
        "sharp_card": Path(os.environ.get("PIZERO_QML_SHARP_CARD", SHARP_CARD)),
        "library": Path(os.environ.get("PIZERO_QML_DMABUF_LIBRARY", DMABUF_LIBRARY)),
    }


class PresenterStats(ctypes.Structure):
    _fields_ = [
        ("submitted_frames", ctypes.c_uint64),
        ("presented_frames", ctypes.c_uint64),
        ("replaced_pending_frames", ctypes.c_uint64),
        ("busy_acquires", ctypes.c_uint64),
        ("commit_errors", ctypes.c_uint64),
        ("unchanged_frames", ctypes.c_uint64),
        ("damage_rows", ctypes.c_uint64),
    ]


class SharpPresenter:
    ACQUIRED = 0
    BUSY = 1

    def __init__(self, width, height):
        paths = presenter_paths()
        self.library = ctypes.CDLL(str(paths["library"]))
        self.library.sharp_presenter_last_error.argtypes = [ctypes.c_void_p]
        self.library.sharp_presenter_last_error.restype = ctypes.c_char_p
        self.library.sharp_presenter_create.argtypes = [
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
        ]
        self.library.sharp_presenter_create.restype = ctypes.c_void_p
        self.library.sharp_presenter_acquire.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(ctypes.c_uint32),
        ]
        self.library.sharp_presenter_acquire.restype = ctypes.c_int
        self.library.sharp_presenter_submit.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_uint32,
        ]
        self.library.sharp_presenter_submit.restype = ctypes.c_int
        self.library.sharp_presenter_submit_auto_damage.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
        ]
        self.library.sharp_presenter_submit_auto_damage.restype = ctypes.c_int
        self.library.sharp_presenter_event_fd.argtypes = [ctypes.c_void_p]
        self.library.sharp_presenter_event_fd.restype = ctypes.c_int
        self.library.sharp_presenter_dispatch.argtypes = [ctypes.c_void_p]
        self.library.sharp_presenter_dispatch.restype = ctypes.c_int
        self.library.sharp_presenter_stride.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
        ]
        self.library.sharp_presenter_stride.restype = ctypes.c_uint32
        self.library.sharp_presenter_modifier.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
        ]
        self.library.sharp_presenter_modifier.restype = ctypes.c_uint64
        self.library.sharp_presenter_dump_active_ppm.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
        ]
        self.library.sharp_presenter_dump_active_ppm.restype = ctypes.c_int
        self.library.sharp_presenter_get_stats.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(PresenterStats),
        ]
        self.library.sharp_presenter_get_stats.restype = ctypes.c_int
        self.library.sharp_presenter_restore.argtypes = [ctypes.c_void_p]
        self.library.sharp_presenter_restore.restype = ctypes.c_int
        self.library.sharp_presenter_destroy.argtypes = [ctypes.c_void_p]
        self.context = self.library.sharp_presenter_create(
            str(paths["render_node"]).encode(),
            str(paths["sharp_card"]).encode(),
            width,
            height,
        )
        if not self.context:
            raise RuntimeError(self.last_error())

    def last_error(self):
        error = self.library.sharp_presenter_last_error(self.context)
        return error.decode() if error else "Unknown Sharp presenter error"

    def acquire(self):
        buffer_index = ctypes.c_uint32()
        renderbuffer = ctypes.c_uint32()
        result = self.library.sharp_presenter_acquire(
            self.context,
            ctypes.byref(buffer_index),
            ctypes.byref(renderbuffer),
        )
        if result == self.BUSY:
            return None
        if result != self.ACQUIRED:
            raise RuntimeError(self.last_error())
        return buffer_index.value, renderbuffer.value

    def submit(self, buffer_index):
        if (
            self.library.sharp_presenter_submit_auto_damage(
                self.context,
                buffer_index,
            )
            != 0
        ):
            raise RuntimeError(self.last_error())

    @property
    def event_fd(self):
        return self.library.sharp_presenter_event_fd(self.context)

    def dispatch(self):
        if self.library.sharp_presenter_dispatch(self.context) != 0:
            raise RuntimeError(self.last_error())

    def stride(self, buffer_index):
        return self.library.sharp_presenter_stride(self.context, buffer_index)

    def modifier(self, buffer_index):
        return self.library.sharp_presenter_modifier(self.context, buffer_index)

    def dump_active_ppm(self, path):
        if (
            self.library.sharp_presenter_dump_active_ppm(
                self.context,
                str(path).encode(),
            )
            != 0
        ):
            raise RuntimeError(self.last_error())

    def get_stats(self):
        stats = PresenterStats()
        if (
            self.library.sharp_presenter_get_stats(
                self.context,
                ctypes.byref(stats),
            )
            != 0
        ):
            raise RuntimeError(self.last_error())
        return stats

    def restore(self):
        if self.context and self.library.sharp_presenter_restore(self.context) != 0:
            raise RuntimeError(self.last_error())

    def close(self):
        if self.context:
            self.library.sharp_presenter_destroy(self.context)
            self.context = None
