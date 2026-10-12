"""Ask MediaInfo's own library what it says about a frame, a sequence and a folder.

**Why through the DLL.** MediaInfo here is an MSIX package -- `MediaInfo_26.10.0.0_neutral__0z25jj8eabac0` under
`C:\\Program Files\\WindowsApps` -- and `E:\\MediaInfo\\MediaInfo.exe` is the launcher for it. Running that launcher
from a shell activates the packaged app rather than running a console program, so it returns **exit code 0 and prints
nothing**, which is what it did three times before this file existed. `MediaInfo.dll` beside it is the real library and
answers the same questions in process.

**The signature that matters**: `MediaInfo_Get(handle, StreamKind, StreamNumber, Parameter, InfoKind, SearchKind)`,
where `Parameter` is a **name** like `FileSize` and not an index. Passing an integer there is an access violation,
which is how the first attempt at this failed.

    python ask_mediainfo.py
"""
import ctypes
import os

DLL = r'E:\MediaInfo\MediaInfo.dll'

GENERAL, VIDEO = 0, 1
NAME, TEXT, MEASURE = 0, 1, 2

PARAMS = ('Format', 'FileSize', 'FrameCount', 'Duration', 'OverallBitRate', 'StreamCount', 'ImageCount')


def load():
    dll = ctypes.WinDLL(DLL)
    dll.MediaInfo_New.restype = ctypes.c_void_p
    dll.MediaInfo_Open.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
    dll.MediaInfo_Get.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_size_t,
                                  ctypes.c_wchar_p, ctypes.c_int, ctypes.c_int]
    dll.MediaInfo_Get.restype = ctypes.c_wchar_p
    dll.MediaInfo_Close.argtypes = [ctypes.c_void_p]
    dll.MediaInfo_Delete.argtypes = [ctypes.c_void_p]
    return dll


def ask(dll, path, stream=GENERAL, name='Format', kind=TEXT):
    handle = dll.MediaInfo_New()
    try:
        dll.MediaInfo_Open(handle, path)
        return dll.MediaInfo_Get(handle, stream, 0, name, kind, 0)
    finally:
        dll.MediaInfo_Close(handle)
        dll.MediaInfo_Delete(handle)


def main():
    dll = load()
    targets = [
        (r'G:\lineweight-video\frames\fracture-38849349120\000001.png', 'one frame'),
        (r'G:\lineweight-video\frames\fracture-38849349120\002041.png', 'the last frame'),
        (r'G:\lineweight-video\frames\fracture-38849349120', 'the whole folder'),
    ]
    for path, what in targets:
        kind = 'a file' if os.path.isfile(path) else ('a folder' if os.path.isdir(path) else 'MISSING')
        print('=== %s  (%s, %s)' % (os.path.basename(path) or path, what, kind))
        for name in PARAMS:
            v = ask(dll, path, GENERAL, name)
            if v:
                print('    %-14s %s' % (name, v))
        for name in ('Format', 'Width', 'Height', 'BitDepth'):
            v = ask(dll, path, VIDEO, name)
            if v:
                print('    video.%-8s %s' % (name, v))
        print()
    print('  ** what it reports for a folder of numbered PNGs is the question this answers. **')


if __name__ == '__main__':
    main()
