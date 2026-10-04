import os, sys, subprocess, tempfile, unittest
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from simple_screen_recorder import ffmpeg_exe
from export_dialog import export_args, write_export, video_info, TrimTimeline, CropOverlay

class ExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([]); cls.folder=tempfile.TemporaryDirectory(); cls.ffmpeg=ffmpeg_exe(); cls.source=Path(cls.folder.name)/'source.mp4'
        command=[cls.ffmpeg,'-v','error','-f','lavfi','-i','color=red:size=320x180:rate=30:duration=4','-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=4','-vf','drawbox=x=160:y=0:w=160:h=180:color=blue:t=fill','-c:v','libx264','-crf','0','-c:a','aac','-t','4',str(cls.source)]
        subprocess.run(command,check=True,creationflags=0x08000000,capture_output=True)
    @classmethod
    def tearDownClass(cls): cls.folder.cleanup()
    def test_trim_crop_and_audio_in_each_export_format(self):
        for ext in ['mp4','mkv','avi','webm']:
            target=Path(self.folder.name)/('trimmed.'+ext); write_export(self.ffmpeg,self.source,target,.75,2.25,(170,30,100,100))
            duration,w,h=video_info(self.ffmpeg,target); self.assertAlmostEqual(duration,1.5,delta=.09); self.assertEqual((w,h),(100,100))
            frame=subprocess.run([self.ffmpeg,'-v','error','-i',str(target),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'],capture_output=True,creationflags=0x08000000,check=True)
            r,g,b=frame.stdout[(50*100+50)*3:(50*100+50)*3+3]; self.assertLess(r,30); self.assertLess(g,30); self.assertGreater(b,200)
            audio=subprocess.run([self.ffmpeg,'-v','error','-i',str(target),'-map','0:a:0','-f','s16le','-'],capture_output=True,creationflags=0x08000000,check=True)
            self.assertGreater(len(audio.stdout),10000)
    def test_existing_file_is_preserved(self):
        target=Path(self.folder.name)/'existing.mp4'; target.write_bytes(b'preserve this')
        with self.assertRaises(FileExistsError): write_export(self.ffmpeg,self.source,target,0,4)
        self.assertEqual(target.read_bytes(),b'preserve this')
    def test_invalid_trim_and_crop_rejected(self):
        with self.assertRaises(ValueError): export_args(self.ffmpeg,self.source,'a.mp4',2,1,'mp4')
        with self.assertRaises(ValueError): export_args(self.ffmpeg,self.source,'a.mp4',0,1,'mp4',(-1,0,100,100))
    def test_timeline_drag_keeps_nonempty_range(self):
        timeline=TrimTimeline(10); timeline.resize(600,78); timeline.show(); self.app.processEvents()
        QTest.mousePress(timeline,Qt.LeftButton,pos=QPoint(16,40)); QTest.mouseMove(timeline,QPoint(200,40)); QTest.mouseRelease(timeline,Qt.LeftButton,pos=QPoint(200,40))
        self.assertGreater(timeline.start,3)
        QTest.mousePress(timeline,Qt.LeftButton,pos=QPoint(584,40)); QTest.mouseMove(timeline,QPoint(50,40)); QTest.mouseRelease(timeline,Qt.LeftButton,pos=QPoint(50,40))
        self.assertAlmostEqual(timeline.end-timeline.start,.1); timeline.close()
    def test_crop_coordinates_account_for_letterboxing(self):
        parent=QWidget(); parent.resize(800,400); crop=CropOverlay(320,180,parent); crop.setGeometry(parent.rect()); parent.show(); crop.show(); self.app.processEvents()
        r=crop.selection_rect(); start=QPoint(round(r.right()),round(r.center().y())); end=QPoint(round(r.center().x()),round(r.center().y()))
        QTest.mousePress(crop,Qt.LeftButton,pos=start); QTest.mouseMove(crop,end); QTest.mouseRelease(crop,Qt.LeftButton,pos=end)
        x,y,w,h=crop.pixel_crop(); self.assertEqual((x,y,h),(0,0,180)); self.assertAlmostEqual(w,160,delta=1)
        start=crop.selection_rect().center().toPoint(); end=start+QPoint(70,0)
        QTest.mousePress(crop,Qt.LeftButton,pos=start); QTest.mouseMove(crop,end); QTest.mouseRelease(crop,Qt.LeftButton,pos=end)
        self.assertGreater(crop.pixel_crop()[0],20); self.assertEqual(crop.pixel_crop()[2],w); parent.close()

if __name__=='__main__': unittest.main()
