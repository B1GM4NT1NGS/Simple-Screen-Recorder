import sys, unittest
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from simple_screen_recorder import AudioRecorder, DEFAULT_AUDIO, DEFAULT_MIC, MainWindow, stop_audio_capture
from PySide6.QtWidgets import QApplication

class AudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])
    def test_windows_default_resolved_again_for_each_recording(self):
        first, second=Mock(), Mock()
        for client,index in [(first,12),(second,15)]:
            client.get_default_wasapi_loopback.return_value={'index':index,'maxInputChannels':2,'defaultSampleRate':48000}
        with patch('pyaudiowpatch.PyAudio',side_effect=[first,second]):
            AudioRecorder(DEFAULT_AUDIO,Path('unused.wav'))
            AudioRecorder(DEFAULT_AUDIO,Path('unused.wav'))
        self.assertEqual(first.open.call_args.kwargs['input_device_index'],12)
        self.assertEqual(second.open.call_args.kwargs['input_device_index'],15)
        first.get_device_info_by_index.assert_not_called()
        second.get_device_info_by_index.assert_not_called()

    def test_unavailable_default_releases_audio_client(self):
        client=Mock(); client.get_default_wasapi_loopback.side_effect=LookupError('No playback device')
        with patch('pyaudiowpatch.PyAudio',return_value=client):
            with self.assertRaises(LookupError): AudioRecorder(DEFAULT_AUDIO,Path('unused.wav'))
        client.terminate.assert_called_once()
    def test_microphone_uses_default_windows_input_and_can_close_before_start(self):
        client=Mock(); client.get_default_wasapi_device.return_value={'index':7,'maxInputChannels':1,'defaultSampleRate':44100}
        with patch('pyaudiowpatch.PyAudio',return_value=client): recorder=AudioRecorder(DEFAULT_MIC,Path('unused.wav'))
        client.get_default_wasapi_device.assert_called_once_with(d_in=True)
        self.assertEqual(client.open.call_args.kwargs['input_device_index'],7); self.assertFalse(client.open.call_args.kwargs['start'])
        recorder.stop(); recorder.stop(); client.open.return_value.close.assert_called_once(); client.terminate.assert_called_once()
    def test_windows_input_options_are_separate_and_default_muted(self):
        client=Mock(); client.get_host_api_info_by_type.return_value={'index':8}; devices=[
            {'index':0,'name':'Speakers [Loopback]','maxInputChannels':2,'hostApi':8,'isLoopbackDevice':True},
            {'index':1,'name':'USB Mic','maxInputChannels':1,'hostApi':8,'isLoopbackDevice':False},
            {'index':2,'name':'Line In','maxInputChannels':2,'hostApi':8,'isLoopbackDevice':False},
            {'index':3,'name':'USB Mic (legacy duplicate)','maxInputChannels':1,'hostApi':0,'isLoopbackDevice':False}]
        client.get_device_count.return_value=len(devices); client.get_device_info_by_index.side_effect=lambda i:devices[i]; client.__enter__=Mock(return_value=client); client.__exit__=Mock(return_value=False)
        with patch('pyaudiowpatch.PyAudio',return_value=client):
            window=MainWindow()
            try:
                self.assertIsNone(window.mic.currentData()); self.assertFalse(window.mic_volume.isEnabled())
                self.assertEqual([window.mic.itemText(i) for i in range(window.mic.count())],['Mute','Windows default input device','USB Mic','Line In'])
                self.assertEqual(window.audio.count(),3)
                window.mic.setCurrentIndex(2); self.assertTrue(window.mic_volume.isEnabled()); window.volume.setValue(25); window.mic_volume.setValue(80)
                self.assertEqual((window.volume.value(),window.mic_volume.value()),(25,80))
                window.refresh_audio_devices(); self.assertEqual(window.mic.currentText(),'USB Mic')
                devices.pop(1); client.get_device_count.return_value=len(devices); window.refresh_audio_devices(); self.assertIsNone(window.mic.currentData())
            finally: window.close()
    def test_cleanup_stops_both_streams_after_one_fails(self):
        first,second=Mock(),Mock(); first.stop.side_effect=RuntimeError('Input disconnected')
        with self.assertRaises(RuntimeError): stop_audio_capture([first,second])
        second.stop.assert_called_once()

if __name__=='__main__': unittest.main()
