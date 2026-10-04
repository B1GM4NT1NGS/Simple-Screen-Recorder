import os, sys, unittest
from pathlib import Path
from unittest.mock import Mock, patch
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QRect
from simple_screen_recorder import MainWindow, ALL_SCREENS

class ScreenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        with patch.object(MainWindow,'populate_audio'): self.window=MainWindow()
        self.screens=[]
        self.window.connected_screens=lambda:self.screens
    def tearDown(self): self.window.close()
    def connect(self,count):
        self.screens=[Mock(geometry=Mock(return_value=QRect((i-1)*1920,0,1920,1080))) for i in range(count)]
        self.window.refresh_screens()
    def test_one_two_and_six_monitors_and_capture_target(self):
        w=self.window
        for count in [1,2,6]:
            self.connect(count)
            expected=['Full Screen'] if count==1 else [f'Full Screen {i+1}' for i in range(count)]
            self.assertEqual([w.mode.itemText(i) for i in range(w.mode.count())],expected+(['Record all screens'] if count>1 else [])+['Area'])
            for i in range(count):
                w.mode.setCurrentIndex(i)
                self.assertEqual(w.get_rect(),((i-1)*1920,0,1920,1080))
                self.assertLessEqual(abs(w.screen_labels[i].geometry().center().x()-((i-1)*1920+960)),1)
                self.assertTrue(all(label.isVisible() for label in w.screen_labels))
            w.show_frame(); self.assertTrue(w.is_area()); self.assertTrue(w.frame.isVisible())
            self.assertTrue(all(not label.isVisible() for label in w.screen_labels))
            w.mode.setCurrentIndex(0)
    def test_disconnect_preserves_remaining_screen_or_falls_back(self):
        self.connect(3); w=self.window; selected=self.screens[2]; w.mode.setCurrentIndex(2)
        self.screens=self.screens[1:]; w.refresh_screens()
        self.assertIs(w.mode.currentData(),selected); self.assertEqual(w.mode.currentText(),'Full Screen 2')
        self.screens=self.screens[:1]; w.refresh_screens()
        self.assertIs(w.mode.currentData(),self.screens[0]); self.assertEqual(w.mode.currentText(),'Full Screen')
    def test_identifiers_removed_before_countdown_and_return_on_cancel(self):
        self.connect(2); w=self.window
        with patch('simple_screen_recorder.tempfile.TemporaryFile'), patch.object(Path,'mkdir'), patch.object(Path,'write_text'):
            w.toggle()
        self.assertTrue(w.pending); self.assertTrue(w.countdown.isVisible())
        self.assertTrue(all(not label.isVisible() for label in w.screen_labels))
        w.toggle(); self.assertTrue(all(label.isVisible() for label in w.screen_labels))
    def test_all_screens_preserves_staggered_layout_and_countdown_per_monitor(self):
        self.screens=[Mock(geometry=Mock(return_value=rect)) for rect in [QRect(-1920,300,1920,1080),QRect(0,0,2560,1440),QRect(600,-1200,1600,1200)]]
        w=self.window; w.refresh_screens(); w.mode.setCurrentIndex(w.mode.findData(ALL_SCREENS))
        self.assertEqual(w.get_rect(),(-1920,-1200,4480,2640))
        self.assertTrue(all(label.selected for label in w.screen_labels))
        with patch('simple_screen_recorder.tempfile.TemporaryFile'), patch.object(Path,'mkdir'), patch.object(Path,'write_text'):
            w.toggle()
        overlays=[w.countdown]+w.extra_countdowns
        self.assertEqual(len(overlays),3)
        for overlay,screen in zip(overlays,self.screens):
            self.assertTrue(overlay.isVisible()); self.assertTrue(screen.geometry().contains(overlay.geometry()))
        w.toggle(); self.assertTrue(all(not overlay.isVisible() for overlay in overlays))
        self.screens=self.screens[1:]; w.refresh_screens(); self.assertTrue(w.is_all_screens())
        self.screens=self.screens[:1]; w.refresh_screens(); self.assertEqual(w.mode.currentText(),'Full Screen')

if __name__=='__main__': unittest.main()
