# PyQt GPU map with the Sharp DRM presenter

The `GPU_MAP` page can draw directly into DMA-BUFs for a Sharp MIP display while
the rest of the application stays in the PyQt GUI. The map and its PyQt controls
are composed before the presenter submits each frame. QML is not required.

Install `memory-lcd-drm` and its optional DMA-BUF presenter through `install.sh`,
or build `libsharp_presenter.so` from the driver repository. Use the normal
`QT_QPA_PLATFORM=linuxfb:fb=/dev/fb0` startup. The installer does not switch
the service to QML.

The map uses an OpenGL ES 2 context on VC4 GBM without an EGL surface
(`EGL_KHR_surfaceless_context`). It renders into DMA-BUF framebuffer objects
directly, so it does not require pbuffer-capable EGL configs or CPU readback
for presentation. Mesa GBM can expose only window-capable configs.

The cycling and paragliding layouts include `GPU_MAP: {STATUS: false}`. Set its
`STATUS` to `true` in the layout you use (`layout.yaml` by default) to enable the page.
While disabled, the PyQt GUI does not import the GPU map widget.
In `setting.conf`, the default
`[DISPLAY_PARAM]` option `use_pyqt_gpu_map_presenter = True` enables direct
presentation when Raspberry Pi, sharp-drm, the VC4 render node, and the
presenter library are available. Set it to `False` to force the QImage path.

The presenter takes over the Sharp DRM primary plane only while the GPU map
page is visible. Buffers use the full display size, while the map viewport
excludes the status bar. The status bar and map controls are composed into the
same buffer. Buffers are created after the visible page's layout is applied.
It restores the framebuffer on page exit. If initialization or rendering
fails, the page falls back to its QImage path and logs the error.
The direct path is disabled when the separate PyQt button box is shown, since
that box cannot be composed into the map page's buffer.

Screenshots on the direct path read the completed full-display buffer, including
the map, controls, HUD and status bar, and save it as PNG. The intermediate PPM
uses a Linux memory file; PNG encoding and disk writes run in a worker thread.
Other pages and the QImage map path keep using the existing QWidget capture.
Normal rendering does not read back the GPU buffer.

This path requires the VC4 KMS driver, `/dev/dri/by-path/platform-soc:gpu-render`,
the Sharp DRM card, and `/usr/local/lib/libsharp_presenter.so`. The application
user needs `video` and `render` group access. Direct presentation must be
verified on the Raspberry Pi: check the log for
`PyQt GPU map Sharp presenter enabled`, navigate to the page, verify the map,
HUD and buttons, then leave the page and confirm the ordinary PyQt framebuffer
returns. The macOS/Linux desktop fallback does not exercise DMA-BUF scanout.

Screenshot capture was verified on `bikecomputer01` on 2026-10-12: Raspberry Pi
Compute Module 0 Rev 1.0, Debian 13.7 (Trixie), Python 3.13.5 and Qt 6.8.2.
The Sharp DRM path saved the full 272x451 display with real OpenStreetMap tiles,
the position marker, course, controls and status bar. Ordinary PyQt capture and
GPU map capture after leaving and re-entering the page also passed.
