import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from simple_screen_recorder import capture_args, encoder_args, desktop_gaps

class Commands(unittest.TestCase):
    def test_negative_monitor_and_odd_area(self):
        cmd=capture_args((-1280,-100,641,359),25,False,'mp4','High','output with spaces.mp4')
        self.assertEqual(cmd[cmd.index('-offset_x')+1],'-1280')
        self.assertEqual(cmd[cmd.index('-video_size')+1],'641x359')
        self.assertIn('pad=ceil(iw/2)*2:ceil(ih/2)*2',cmd)
        self.assertEqual(cmd[-1],'output with spaces.mp4')
        self.assertIn('-n',cmd)
    def test_invalid_region(self):
        with self.assertRaises(ValueError): capture_args((0,0,0,30),30,True,'mkv','High','out.mkv')
    def test_webm_codec(self):
        self.assertIn('libvpx-vp9',encoder_args('webm'))
        self.assertNotIn('libx264',encoder_args('webm'))
    def test_all_screens_blanks_only_gaps_in_windows_layout(self):
        rect=(-100,-50,200,150); screens=[(-100,0,100,100),(0,-50,100,100)]
        gaps=desktop_gaps(rect,screens)
        self.assertEqual(gaps,[(0,0,100,50),(100,100,100,50)])
        cmd=capture_args(rect,30,True,'mp4','Balanced','all.mp4',screens)
        self.assertEqual(cmd[cmd.index('-offset_x')+1],'-100')
        self.assertEqual(cmd[cmd.index('-video_size')+1],'200x150')
        self.assertIn('drawbox=x=100:y=100:w=100:h=50:color=black:t=fill',cmd[cmd.index('-vf')+1])

if __name__=='__main__': unittest.main()
