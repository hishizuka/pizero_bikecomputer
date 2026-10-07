"""GLES2 calls for a context made current by the caller; no context creation."""

import ctypes as C
import sys

DARWIN = sys.platform == "darwin"
gl = C.CDLL(
    "/System/Library/Frameworks/OpenGL.framework/OpenGL" if DARWIN else "libGLESv2.so.2"
)


def _bind(name, args, result=None):
    function = getattr(gl, name)
    function.argtypes = args
    function.restype = result


_uint_pointer = C.POINTER(C.c_uint)
_int_pointer = C.POINTER(C.c_int)
for _kind in ("Buffers", "Textures", "Framebuffers", "Renderbuffers"):
    for _action in ("Gen", "Delete"):
        _bind(f"gl{_action}{_kind}", [C.c_int, _uint_pointer])
for _name in (
    "glBindBuffer",
    "glBindTexture",
    "glBindFramebuffer",
    "glBindRenderbuffer",
    "glBlendFunc",
    "glAttachShader",
):
    _bind(_name, [C.c_uint, C.c_uint])
for _name in (
    "glUseProgram",
    "glDeleteProgram",
    "glDeleteShader",
    "glCompileShader",
    "glLinkProgram",
    "glEnable",
    "glDisable",
    "glActiveTexture",
    "glDepthFunc",
    "glEnableVertexAttribArray",
    "glDisableVertexAttribArray",
    "glClear",
    "glBlendEquation",
):
    _bind(_name, [C.c_uint])
_bind("glCreateProgram", [], C.c_uint)
_bind("glBlendFuncSeparate", [C.c_uint] * 4)
_bind("glCreateShader", [C.c_uint], C.c_uint)
_bind("glGetString", [C.c_uint], C.c_char_p)
_bind("glGetIntegerv", [C.c_uint, _int_pointer])
_bind("glGetError", [], C.c_uint)
_bind("glCheckFramebufferStatus", [C.c_uint], C.c_uint)
_bind("glIsFramebuffer", [C.c_uint], C.c_ubyte)
for _name in ("glIsProgram", "glIsBuffer", "glIsTexture"):
    _bind(_name, [C.c_uint], C.c_ubyte)
_bind("glShaderSource", [C.c_uint, C.c_int, C.POINTER(C.c_char_p), _int_pointer])
for _kind in ("Shader", "Program"):
    _bind(f"glGet{_kind}iv", [C.c_uint, C.c_uint, _int_pointer])
    _bind(f"glGet{_kind}InfoLog", [C.c_uint, C.c_int, _int_pointer, C.c_void_p])
_bind("glBindAttribLocation", [C.c_uint, C.c_uint, C.c_char_p])
_bind("glGetUniformLocation", [C.c_uint, C.c_char_p], C.c_int)
for _n in range(1, 5):
    _bind(f"glUniform{_n}f", [C.c_int] + [C.c_float] * _n)
_bind("glUniform1i", [C.c_int, C.c_int])
_bind("glBufferData", [C.c_uint, C.c_ssize_t, C.c_void_p, C.c_uint])
_bind("glBufferSubData", [C.c_uint, C.c_ssize_t, C.c_ssize_t, C.c_void_p])
_bind(
    "glVertexAttribPointer",
    [C.c_uint, C.c_int, C.c_uint, C.c_ubyte, C.c_int, C.c_void_p],
)
_bind("glDrawElements", [C.c_uint, C.c_int, C.c_uint, C.c_void_p])
_bind("glTexParameteri", [C.c_uint, C.c_uint, C.c_int])
_bind("glPixelStorei", [C.c_uint, C.c_int])
_bind(
    "glTexImage2D",
    [
        C.c_uint,
        C.c_int,
        C.c_int,
        C.c_int,
        C.c_int,
        C.c_int,
        C.c_uint,
        C.c_uint,
        C.c_void_p,
    ],
)
_bind(
    "glTexSubImage2D",
    [
        C.c_uint,
        C.c_int,
        C.c_int,
        C.c_int,
        C.c_int,
        C.c_int,
        C.c_uint,
        C.c_uint,
        C.c_void_p,
    ],
)
_bind(
    "glReadPixels", [C.c_int, C.c_int, C.c_int, C.c_int, C.c_uint, C.c_uint, C.c_void_p]
)
_bind("glViewport", [C.c_int] * 4)
_bind("glCopyTexSubImage2D", [C.c_uint] + [C.c_int] * 7)
_bind("glClearColor", [C.c_float] * 4)
_bind("glColorMask", [C.c_ubyte] * 4)
_bind("glDepthMask", [C.c_ubyte])
_bind("glRenderbufferStorage", [C.c_uint, C.c_uint, C.c_int, C.c_int])
_bind("glFramebufferRenderbuffer", [C.c_uint] * 4)
_bind("glFramebufferTexture2D", [C.c_uint, C.c_uint, C.c_uint, C.c_uint, C.c_int])
_bind("glFinish", [])
if DARWIN:
    _bind("glClearDepth", [C.c_double])
    clear_depth = gl.glClearDepth
else:
    _bind("glClearDepthf", [C.c_float])
    clear_depth = gl.glClearDepthf


def gl_check(where):
    error = gl.glGetError()
    if error:
        raise RuntimeError(f"GL error 0x{error:04x} at {where}")


def compile_program(vertex_source, fragment_source, attributes, desktop):
    """Compile ES 1.00 or desktop 1.20 shaders and release temporary shaders."""
    program = gl.glCreateProgram()
    shaders = []
    try:
        for kind, source in ((0x8B31, vertex_source), (0x8B30, fragment_source)):
            if desktop:
                source = "#version 120\n" + "\n".join(
                    line
                    for line in source.splitlines()
                    if not line.strip().startswith("precision ")
                )
            shader = gl.glCreateShader(kind)
            shaders.append(shader)
            encoded = C.c_char_p(source.encode())
            gl.glShaderSource(shader, 1, C.byref(encoded), None)
            gl.glCompileShader(shader)
            status = C.c_int()
            gl.glGetShaderiv(shader, 0x8B81, C.byref(status))
            if not status.value:
                log = C.create_string_buffer(4096)
                gl.glGetShaderInfoLog(shader, len(log), None, log)
                raise RuntimeError(log.value.decode())
            gl.glAttachShader(program, shader)
        for index, name in enumerate(attributes):
            gl.glBindAttribLocation(program, index, name.encode())
        gl.glLinkProgram(program)
        status = C.c_int()
        gl.glGetProgramiv(program, 0x8B82, C.byref(status))
        if not status.value:
            log = C.create_string_buffer(4096)
            gl.glGetProgramInfoLog(program, len(log), None, log)
            raise RuntimeError(log.value.decode())
        return program
    except Exception:
        gl.glDeleteProgram(program)
        raise
    finally:
        for shader in shaders:
            gl.glDeleteShader(shader)
