import array, cmath, math, subprocess, tempfile, unittest, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from simple_screen_recorder import ffmpeg_exe, preview_audio_args

class MixTests(unittest.TestCase):
    def test_two_different_input_rates_have_independent_gain_and_correct_duration(self):
        ffmpeg=ffmpeg_exe()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); video=root/'video.mp4'; speaker=root/'speaker.wav'; mic=root/'mic.wav'; output=root/'mixed.mp4'
            commands=[
                [ffmpeg,'-v','error','-f','lavfi','-i','color=size=32x32:duration=2:rate=30','-c:v','libx264',str(video)],
                [ffmpeg,'-v','error','-f','lavfi','-i','sine=frequency=330:duration=1.5:sample_rate=44100','-ac','2',str(speaker)],
                [ffmpeg,'-v','error','-f','lavfi','-i','sine=frequency=880:duration=2:sample_rate=48000','-ac','2',str(mic)],
                [ffmpeg,'-v','error','-i',str(video),*preview_audio_args([(speaker,.5),(mic,.25)],2),str(output)]]
            for command in commands: subprocess.run(command,capture_output=True,check=True,creationflags=0x08000000)
            decoded=subprocess.run([ffmpeg,'-v','error','-i',str(output),'-map','0:a:0','-ac','1','-ar','48000','-f','f32le','-'],capture_output=True,check=True,creationflags=0x08000000)
            samples=array.array('f'); samples.frombytes(decoded.stdout); self.assertAlmostEqual(len(samples)/48000,2,delta=.04)
            def amplitude(frequency,start,end):
                chunk=samples[int(start*48000):int(end*48000)]
                return abs(sum(value*cmath.exp(-2j*math.pi*frequency*i/48000) for i,value in enumerate(chunk)))/len(chunk)
            ratio=amplitude(330,.4,.8)/amplitude(880,.4,.8); self.assertAlmostEqual(ratio,2,delta=.15)
            self.assertGreater(amplitude(880,1.7,1.9),.005); self.assertLess(amplitude(330,1.7,1.9),.001)

if __name__=='__main__': unittest.main()
