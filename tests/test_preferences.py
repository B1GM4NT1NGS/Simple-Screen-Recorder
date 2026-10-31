import os,sys,json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QRect
from PySide6.QtTest import QTest
from simple_screen_recorder import MainWindow,DEFAULT_AUDIO,ALL_SCREENS
from preferences import read_preferences,write_preferences

class PreferencesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(); self.root=Path(self.temporary.name); self.path=self.root/'settings.json'; self.windows=[]
        self.devices=[('Speakers [Loopback]',True),('USB Mic',False)]
        def audio_client():
            client=Mock(); client.get_host_api_info_by_type.return_value={'index':8}
            client.get_device_count.side_effect=lambda:len(self.devices)
            client.get_device_info_by_index.side_effect=lambda i:{'index':i,'name':self.devices[i][0],'maxInputChannels':2,'hostApi':8,'isLoopbackDevice':self.devices[i][1]}
            client.__enter__=Mock(return_value=client); client.__exit__=Mock(return_value=False); return client
        self.audio_patch=patch('pyaudiowpatch.PyAudio',side_effect=audio_client); self.audio_patch.start()
    def tearDown(self):
        for window in self.windows:
            if not window._closed: window.close()
        self.audio_patch.stop(); self.temporary.cleanup()
    def window(self):
        window=MainWindow(config_path=self.path); self.windows.append(window); return window
    def test_first_use_and_legacy_settings_default_to_mp4(self):
        window=self.window(); self.assertEqual(window.format.currentText(),'MP4'); self.assertIsNone(window.mic.currentData()); self.assertEqual(window.audio.currentData(),DEFAULT_AUDIO); window.close()
        write_preferences(self.path,{'folder':str(self.root),'format':'GIF','fps':'30'})
        window=self.window(); self.assertEqual(window.format.currentText(),'MP4'); self.assertEqual(window.folder.text(),str(self.root))
    def test_close_without_recording_remembers_choices_and_device_names(self):
        window=self.window(); window.format.setCurrentText('GIF'); window.folder.setText(str(self.root/'videos'))
        window.mode.setCurrentIndex(window.mode.count()-1); window.frame.setGeometry(40,60,420,280)
        window.volume.setValue(23); window.mic_volume.setValue(67)
        window.audio.setCurrentIndex(window.audio.findData(0)); window.mic.setCurrentIndex(window.mic.findData(1)); window.close()
        self.devices.insert(0,('Another mic',False))
        restored=self.window()
        self.assertEqual(restored.format.currentText(),'MP4'); self.assertEqual(restored.folder.text(),str(self.root/'videos'))
        self.assertTrue(restored.is_area()); self.assertEqual(restored.frame.geometry(),QRect(40,60,420,280))
        self.assertEqual((restored.volume.value(),restored.mic_volume.value()),(23,67))
        self.assertEqual(restored.audio.currentData(),1); self.assertEqual(restored.mic.currentData(),2)
        self.assertTrue(restored.mic_volume.isEnabled())
    def test_selection_changes_are_saved_without_closing_or_recording(self):
        window=self.window(); window.format.setCurrentText('GIF'); window.volume.setValue(41)
        QTest.qWait(450)
        data=read_preferences(self.path); self.assertNotIn('format',data); self.assertEqual(data['speaker_volume'],41)
        self.assertEqual(window.format.currentText(),'GIF')
    def test_previously_saved_format_never_overrides_mp4_on_startup(self):
        for format in ['GIF','WebM','MKV','AVI']:
            write_preferences(self.path,{'preferences_version':1,'format':format,'speaker_volume':29,'folder':str(self.root)})
            window=self.window(); self.assertEqual(window.format.currentText(),'MP4')
            self.assertEqual(window.volume.value(),29); self.assertEqual(window.folder.text(),str(self.root)); window.close()
    def test_disconnected_microphone_falls_back_to_mute_and_returns_when_reconnected(self):
        window=self.window(); window.mic.setCurrentIndex(window.mic.findData(1)); window.close()
        self.devices.pop(); restored=self.window(); self.assertIsNone(restored.mic.currentData())
        self.devices.append(('USB Mic',False)); restored.refresh_audio_devices(); self.assertEqual(restored.mic.currentText(),'USB Mic')
    def test_monitor_serial_is_preferred_when_windows_display_names_change(self):
        def screen(name,serial,x):
            value=Mock(); value.name.return_value=name; value.serialNumber.return_value=serial
            value.geometry.return_value=QRect(x,0,800,600); value.availableGeometry.return_value=QRect(x,0,800,560); return value
        screens=[screen('Display 1','serial-a',0),screen('Display 2','serial-b',800)]
        with patch.object(MainWindow,'connected_screens',lambda window:screens):
            window=self.window(); window.mode.setCurrentIndex(1); window.close()
            screens=[screen('Display 2','serial-a',0),screen('Display 1','serial-b',800)]
            restored=self.window(); self.assertIs(restored.mode.currentData(),screens[1]); restored.close()
            write_preferences(self.path,{'preferences_version':1,'capture':{'kind':'all'}})
            screens=screens[:1]; restored=self.window(); self.assertFalse(restored.is_all_screens()); self.assertIs(restored.mode.currentData(),screens[0])
    def test_invalid_preferences_and_disconnected_frame_are_recoverable(self):
        self.path.write_text('[broken',encoding='utf-8'); window=self.window(); self.assertEqual(window.format.currentText(),'MP4'); window.close()
        write_preferences(self.path,{'preferences_version':1,'format':'bad','speaker_volume':'bad','mic_volume':-30,'frame':[90000,90000,420,280],'capture':{'kind':'area'},'speakers':{'kind':'device','name':'Disconnected speakers'},'mic':{'kind':'device','name':'Disconnected mic'}})
        window=self.window(); self.assertEqual(window.format.currentText(),'MP4'); self.assertEqual(window.audio.currentData(),DEFAULT_AUDIO); self.assertIsNone(window.mic.currentData())
        self.assertEqual((window.volume.value(),window.mic_volume.value()),(100,0))
        self.assertTrue(self.app.primaryScreen().availableGeometry().intersects(window.frame.geometry()))
    def test_failed_atomic_save_preserves_previous_preferences(self):
        write_preferences(self.path,{'format':'MP4'})
        with patch('preferences.os.replace',side_effect=OSError('blocked')):
            with self.assertRaises(OSError):write_preferences(self.path,{'format':'GIF'})
        self.assertEqual(read_preferences(self.path),{'format':'MP4'}); self.assertEqual(list(self.root.glob('.settings-*')),[])

if __name__=='__main__':unittest.main()
