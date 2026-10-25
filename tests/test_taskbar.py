import ctypes,sys,unittest,tempfile
from ctypes import wintypes as W
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from windows_identity import TaskbarIdentity,APP_ID,_GUID,_PropertyKey,_PropVariant

def read_properties(hwnd):
    shell=ctypes.WinDLL('shell32'); ole=ctypes.WinDLL('ole32'); result={}
    initialized=ole.CoInitializeEx(None,2); store=ctypes.c_void_p()
    try:
        iid=_GUID.parse('886d8eeb-8cf2-4446-8d02-cdba1dbdcf99')
        shell.SHGetPropertyStoreForWindow.argtypes=[W.HWND,ctypes.POINTER(_GUID),ctypes.POINTER(ctypes.c_void_p)]
        assert shell.SHGetPropertyStoreForWindow(hwnd,ctypes.byref(iid),ctypes.byref(store))==0
        table=ctypes.cast(store,ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        get=ctypes.WINFUNCTYPE(ctypes.c_long,ctypes.c_void_p,ctypes.POINTER(_PropertyKey),ctypes.POINTER(_PropVariant))(table[5])
        ole.PropVariantClear.argtypes=[ctypes.POINTER(_PropVariant)]
        for pid in [2,3,4,5]:
            key=_PropertyKey(_GUID.parse('9f4c2855-9f79-4b39-a8d0-e1d42de1d5f3'),pid); value=_PropVariant()
            try:
                assert get(store,ctypes.byref(key),ctypes.byref(value))==0
                result[pid]=value.text if value.vt==31 else None
            finally: ole.PropVariantClear(ctypes.byref(value))
        return result
    finally:
        if store.value:
            table=ctypes.cast(store,ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
            ctypes.WINFUNCTYPE(W.ULONG,ctypes.c_void_p)(table[2])(store)
        if initialized in (0,1):ole.CoUninitialize()

class TaskbarTests(unittest.TestCase):
    def setUp(self):
        self.user=ctypes.WinDLL('user32')
        self.user.CreateWindowExW.argtypes=[W.DWORD,W.LPCWSTR,W.LPCWSTR,W.DWORD,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,W.HWND,W.HMENU,W.HINSTANCE,ctypes.c_void_p]
        self.user.CreateWindowExW.restype=W.HWND; self.user.DestroyWindow.argtypes=[W.HWND]
        self.user.SendMessageW.argtypes=[W.HWND,W.UINT,ctypes.c_size_t,ctypes.c_ssize_t];self.user.SendMessageW.restype=ctypes.c_ssize_t
        self.hwnd=self.user.CreateWindowExW(0,'STATIC','Recorder icon test',0,0,0,100,100,None,None,None,None)
        self.assertTrue(self.hwnd); self.identity=None
        self.icon=Path(__file__).resolve().parents[1]/'assets'/'recorder.ico'
    def tearDown(self):
        self.user.DestroyWindow(self.hwnd)
        if self.identity:self.identity.close(); self.identity.close()
    def test_portable_taskbar_icons_and_pinning_use_persistent_executable(self):
        executable=Path(tempfile.gettempdir())/'Recorder with spaces.exe'
        self.identity=TaskbarIdentity(self.hwnd,self.icon,executable)
        properties=read_properties(self.hwnd)
        self.assertEqual(properties[5],APP_ID)
        self.assertEqual(properties[3],str(executable.resolve())+',-1')
        self.assertEqual(properties[2],f'"{executable.resolve()}"')
        self.assertEqual(properties[4],'Simple Screen Recorder')
        for kind,icon in enumerate(self.identity.icons):self.assertEqual(self.user.SendMessageW(self.hwnd,0x7f,kind,0),icon)
    def test_source_launch_keeps_its_script_and_custom_icon(self):
        script=Path(tempfile.gettempdir())/'recorder source'/'simple_screen_recorder.py'
        self.identity=TaskbarIdentity(self.hwnd,self.icon,sys.executable,script)
        properties=read_properties(self.hwnd)
        self.assertEqual(properties[3],str(self.icon)+',0')
        self.assertIn(str(script.resolve()),properties[2]); self.assertEqual(properties[5],APP_ID)

if __name__=='__main__':unittest.main()
