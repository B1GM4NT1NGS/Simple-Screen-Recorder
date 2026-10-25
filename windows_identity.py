"""Windows taskbar identity and native window icons for the portable recorder."""
import ctypes
from ctypes import wintypes as W
from pathlib import Path
import subprocess
import uuid

APP_ID='SimpleScreenRecorder.Desktop'

class _GUID(ctypes.Structure):
    _fields_=[('data1',W.DWORD),('data2',W.WORD),('data3',W.WORD),('data4',ctypes.c_ubyte*8)]
    @classmethod
    def parse(cls,text): return cls.from_buffer_copy(uuid.UUID(text).bytes_le)

class _PropertyKey(ctypes.Structure):
    _fields_=[('fmtid',_GUID),('pid',W.DWORD)]

class _Value(ctypes.Union):
    _fields_=[('text',W.LPWSTR),('storage',ctypes.c_void_p*2)]

class _PropVariant(ctypes.Structure):
    _anonymous_=('value',)
    _fields_=[('vt',W.WORD),('reserved1',W.WORD),('reserved2',W.WORD),('reserved3',W.WORD),('value',_Value)]

def _check(result):
    if result<0: raise OSError(f'Windows taskbar identity failed (0x{result & 0xffffffff:08X}).')

def set_process_identity():
    shell=ctypes.WinDLL('shell32')
    shell.SetCurrentProcessExplicitAppUserModelID.argtypes=[W.LPCWSTR]
    shell.SetCurrentProcessExplicitAppUserModelID.restype=ctypes.c_long
    _check(shell.SetCurrentProcessExplicitAppUserModelID(APP_ID))

def _window_properties(hwnd,values):
    shell=ctypes.WinDLL('shell32'); ole=ctypes.WinDLL('ole32')
    ole.CoInitializeEx.argtypes=[ctypes.c_void_p,W.DWORD]; ole.CoInitializeEx.restype=ctypes.c_long
    initialized=ole.CoInitializeEx(None,2)
    if initialized not in (0,1) and initialized!=-2147417850: _check(initialized)
    store=ctypes.c_void_p()
    try:
        iid=_GUID.parse('886d8eeb-8cf2-4446-8d02-cdba1dbdcf99')
        shell.SHGetPropertyStoreForWindow.argtypes=[W.HWND,ctypes.POINTER(_GUID),ctypes.POINTER(ctypes.c_void_p)]
        shell.SHGetPropertyStoreForWindow.restype=ctypes.c_long
        _check(shell.SHGetPropertyStoreForWindow(hwnd,ctypes.byref(iid),ctypes.byref(store)))
        table=ctypes.cast(store,ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        set_value=ctypes.WINFUNCTYPE(ctypes.c_long,ctypes.c_void_p,ctypes.POINTER(_PropertyKey),ctypes.POINTER(_PropVariant))(table[6])
        for pid,text in values:
            key=_PropertyKey(_GUID.parse('9f4c2855-9f79-4b39-a8d0-e1d42de1d5f3'),pid)
            buffer=ctypes.create_unicode_buffer(text)
            value=_PropVariant(); value.vt=31; value.text=ctypes.cast(buffer,W.LPWSTR)
            # SetValue copies the string. The input buffer remains Python-owned.
            _check(set_value(store,ctypes.byref(key),ctypes.byref(value)))
    finally:
        if store.value:
            table=ctypes.cast(store,ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
            ctypes.WINFUNCTYPE(W.ULONG,ctypes.c_void_p)(table[2])(store)
        if initialized in (0,1): ole.CoUninitialize()

class TaskbarIdentity:
    def __init__(self,hwnd,icon_path,executable,script=None):
        self.icons=[]; self.user=ctypes.WinDLL('user32',use_last_error=True)
        self.user.LoadImageW.argtypes=[W.HINSTANCE,W.LPCWSTR,W.UINT,ctypes.c_int,ctypes.c_int,W.UINT]
        self.user.LoadImageW.restype=W.HANDLE
        self.user.DestroyIcon.argtypes=[W.HICON]
        self.user.SendMessageW.argtypes=[W.HWND,W.UINT,ctypes.c_size_t,ctypes.c_ssize_t]
        self.user.SendMessageW.restype=ctypes.c_ssize_t
        self.user.GetSystemMetrics.argtypes=[ctypes.c_int]; self.user.GetSystemMetrics.restype=ctypes.c_int
        try:
            for width,height in [(49,50),(11,12)]:
                icon=self.user.LoadImageW(None,str(icon_path),1,self.user.GetSystemMetrics(width),self.user.GetSystemMetrics(height),0x10)
                if not icon: raise ctypes.WinError(ctypes.get_last_error())
                self.icons.append(icon)
            executable=str(Path(executable).resolve())
            command=subprocess.list2cmdline([executable]+([str(Path(script).resolve())] if script else []))
            # Pinning must reference the persistent EXE, never a one-file extraction folder.
            icon_resource=str(Path(icon_path).resolve())+',0' if script else executable+',-1'
            _window_properties(hwnd,[(2,command),(3,icon_resource),(4,'Simple Screen Recorder'),(5,APP_ID)])
            for kind,icon in enumerate(self.icons): self.user.SendMessageW(hwnd,0x80,kind,icon)
        except Exception:
            self.close(); raise
    def close(self,*args):
        for icon in self.icons: self.user.DestroyIcon(icon)
        self.icons.clear()
