import os,sys,unittest
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint,Qt
from PySide6.QtTest import QTest
from simple_screen_recorder import CaptureFrame

class FrameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.frame=CaptureFrame(); self.frame.setGeometry(100,120,654,399); self.frame.show(); self.app.processEvents()
    def tearDown(self): self.frame.close()
    def test_border_excluded_and_centre_passes_through(self):
        self.assertEqual(self.frame.capture_rect(),(108,128,638,383))
        self.assertTrue(self.frame.mask().contains(QPoint(100,100)))
        self.assertTrue(self.frame.mask().contains(QPoint(100,4)))
        self.assertTrue(self.frame.mask().contains(self.frame.move_handle_rect().center()))
        self.frame.set_locked(True)
        self.assertFalse(self.frame.mask().contains(QPoint(100,100)))
        self.assertFalse(self.frame.mask().contains(self.frame.move_handle_rect().center()))
    def test_move_resize_and_lock(self):
        frame=self.frame
        handle=frame.move_handle_rect().center()
        QTest.mousePress(frame,Qt.LeftButton,pos=handle); QTest.mouseMove(frame,handle+QPoint(80,40)); QTest.mouseRelease(frame,Qt.LeftButton,pos=handle+QPoint(80,40))
        self.assertNotEqual(frame.x(),100)
        old=frame.size(); QTest.mousePress(frame,Qt.LeftButton,pos=QPoint(frame.width()-3,frame.height()-3)); QTest.mouseMove(frame,QPoint(frame.width()+47,frame.height()+27)); QTest.mouseRelease(frame,Qt.LeftButton,pos=QPoint(frame.width()+47,frame.height()+27))
        self.assertGreater(frame.width(),old.width())
        frame.move(-700,100); self.assertLess(frame.capture_rect()[0],0)
        frame.set_locked(True); old=frame.geometry()
        QTest.mousePress(frame,Qt.LeftButton,pos=QPoint(100,15)); QTest.mouseMove(frame,QPoint(200,20)); QTest.mouseRelease(frame,Qt.LeftButton,pos=QPoint(200,20))
        self.assertEqual(frame.geometry(),old)
    def test_drag_from_multiple_interior_points(self):
        for point in [QPoint(40,40),QPoint(550,320),QPoint(110,270)]:
            before=self.frame.pos()
            QTest.mousePress(self.frame,Qt.LeftButton,pos=point)
            QTest.mouseMove(self.frame,point+QPoint(30,20))
            QTest.mouseRelease(self.frame,Qt.LeftButton,pos=point+QPoint(30,20))
            self.assertNotEqual(self.frame.pos(),before)

if __name__=='__main__': unittest.main()
