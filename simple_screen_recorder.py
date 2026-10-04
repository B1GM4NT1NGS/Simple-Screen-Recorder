"""Simple Screen Recorder — local Windows screen and audio recording."""
import ctypes
from ctypes import wintypes
import json, os, sys, time, threading, subprocess, tempfile, wave, re, math
from pathlib import Path
from datetime import datetime
from export_dialog import ExportDialog, TOOLTIP_STYLE, tooltip_text
from PySide6.QtCore import Qt, QRect, QPoint, QTimer, QUrl, Signal, QObject, QAbstractNativeEventFilter
from PySide6.QtGui import QPainter, QColor, QPen, QDesktopServices, QRegion, QIcon, QFont, QPalette, QFontMetrics
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel, QPushButton,
    QComboBox, QCheckBox, QSpinBox, QLineEdit, QFileDialog, QMessageBox,
    QVBoxLayout, QHBoxLayout, QMenu, QSlider, QListView, QStyledItemDelegate, QStyle)

NAME = 'Simple Screen Recorder'
VERSION = '1.1.2'
COFFEE = 'https://buymeacoffee.com/bigzz'
GITHUB = 'https://github.com/B1GM4NT1NGS/Simple-Screen-Recorder'
CREATE_NO_WINDOW = 0x08000000
DEFAULT_AUDIO = 'windows-default'
DEFAULT_MIC = 'windows-default-microphone'
ALL_SCREENS = 'all-screens'

def asset_path(name):
    return str((Path(sys._MEIPASS) if getattr(sys,'frozen',False) else Path(__file__).parent)/'assets'/name)

class DropdownDelegate(QStyledItemDelegate):
    def sizeHint(self,option,index):
        size=super().sizeHint(option,index); size.setHeight(42); return size
    def paint(self,painter,option,index):
        painter.save()
        selected=bool(option.state & QStyle.State_Selected)
        painter.fillRect(option.rect,QColor('#edf2f8' if selected else '#ffffff'))
        painter.setPen(QColor('#243449')); font=QFont('Segoe UI'); font.setPixelSize(14); painter.setFont(font)
        text=painter.fontMetrics().elidedText(str(index.data() or ''),Qt.ElideRight,option.rect.width()-32)
        painter.drawText(option.rect.adjusted(16,0,-16,0),Qt.AlignVCenter|Qt.AlignLeft,text)
        painter.restore()

class SelectorCombo(QComboBox):
    """One centred label and an explicit chevron, with native popup/keyboard support."""
    opening=Signal()
    def __init__(self):
        super().__init__(); self.setFixedHeight(36); self.setCursor(Qt.PointingHandCursor)
        self.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(10); self.setMaxVisibleItems(10)
        self.currentIndexChanged.connect(self.update)
        view=QListView(); view.setItemDelegate(DropdownDelegate(view)); view.setTextElideMode(Qt.ElideRight)
        view.setStyleSheet('QListView{background:#ffffff;color:#243449;border:0;padding:4px;outline:0;} QScrollBar:vertical{background:#f2f4f7;width:10px;} QScrollBar::handle:vertical{background:#b6c1ce;border-radius:4px;min-height:20px;}')
        palette=view.palette()
        for role,color in [(QPalette.Base,'#ffffff'),(QPalette.Window,'#ffffff'),(QPalette.Text,'#243449'),(QPalette.WindowText,'#243449'),(QPalette.Highlight,'#edf2f8'),(QPalette.HighlightedText,'#243449')]: palette.setColor(role,QColor(color))
        view.setPalette(palette); self.setView(view)
    def showPopup(self):
        self.opening.emit()
        font=QFont('Segoe UI'); font.setPixelSize(14); metrics=QFontMetrics(font)
        desired=max([self.width()]+[metrics.horizontalAdvance(self.itemText(i))+52 for i in range(self.count())])
        available=self.screen().availableGeometry(); width=min(desired,available.width()-24,640)
        self.view().setMinimumWidth(width); super().showPopup()
        popup=self.view().window(); popup.setObjectName('recorderDropdownPopup'); popup.setStyleSheet('QWidget#recorderDropdownPopup{background:#ffffff;color:#243449;border:1px solid #d8e0ea;border-radius:8px;}'+TOOLTIP_STYLE)
        palette=self.view().palette(); popup.setPalette(palette); popup.setAutoFillBackground(True)
        popup.resize(max(popup.width(),width),popup.height())
        x=max(available.left()+8,min(self.mapToGlobal(QPoint(0,0)).x(),available.right()-popup.width()-8)); popup.move(x,popup.y())
    def paintEvent(self,event):
        painter=QPainter(self); painter.setRenderHint(QPainter.Antialiasing)
        font=QFont('Segoe UI'); font.setPixelSize(14 if self.width()<140 else 15); painter.setFont(font)
        text=self.currentData(Qt.UserRole+1) or self.currentText()
        metrics=painter.fontMetrics(); text=metrics.elidedText(text,Qt.ElideRight,self.width()-26)
        text_width=metrics.horizontalAdvance(text); group_width=text_width+23
        left=(self.width()-group_width)//2
        color=QColor('#464d57' if self.isEnabled() else '#9ca3ad')
        painter.setPen(color); painter.drawText(QRect(left,0,text_width,self.height()),Qt.AlignVCenter|Qt.AlignLeft,text)
        x=left+text_width+13; y=self.height()//2
        painter.setPen(QPen(color,1.7,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin)); painter.drawLine(x-4,y-2,x,y+2); painter.drawLine(x,y+2,x+4,y-2)
        if self.hasFocus():
            painter.setPen(QPen(QColor('#a8b9ce'),1)); painter.drawRoundedRect(self.rect().adjusted(2,2,-2,-2),6,6)

def ffmpeg_exe():
    if getattr(sys, 'frozen', False):
        return str(Path(sys._MEIPASS) / 'ffmpeg.exe')
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()

def encoder_args(ext, quality='High'):
    crf = {'High':18, 'Balanced':23, 'Small file':28}[quality]
    if ext == 'webm':
        return ['-c:v','libvpx-vp9','-deadline','realtime','-cpu-used','6','-crf',str(crf+8),'-b:v','0']
    return ['-c:v','libx264','-preset','ultrafast','-crf',str(crf),'-pix_fmt','yuv420p']

def desktop_gaps(rect,screens):
    x,y,w,h=rect; xs=sorted({x,x+w,*[v for sx,sy,sw,sh in screens for v in (sx,sx+sw)]}); ys=sorted({y,y+h,*[v for sx,sy,sw,sh in screens for v in (sy,sy+sh)]})
    gaps=[]
    for top,bottom in zip(ys,ys[1:]):
        start=None
        for left,right in zip(xs,xs[1:]):
            covered=any(sx<=left and right<=sx+sw and sy<=top and bottom<=sy+sh for sx,sy,sw,sh in screens)
            if not covered and start is None: start=left
            if covered and start is not None: gaps.append((start-x,top-y,left-start,bottom-top)); start=None
        if start is not None: gaps.append((start-x,top-y,x+w-start,bottom-top))
    return gaps

def capture_args(rect, fps, cursor, ext, quality, target, screen_rects=None):
    x,y,w,h = rect
    if w < 16 or h < 16: raise ValueError('Select an area at least 16 × 16 pixels.')
    filters=[f'drawbox=x={x}:y={y}:w={w}:h={h}:color=black:t=fill' for x,y,w,h in desktop_gaps(rect,screen_rects)] if screen_rects else []
    filters.append('pad=ceil(iw/2)*2:ceil(ih/2)*2')
    return [ffmpeg_exe(),'-hide_banner','-loglevel','warning','-n','-f','gdigrab',
        '-framerate',str(fps),'-draw_mouse',str(int(cursor)),'-offset_x',str(x),
        '-offset_y',str(y),'-video_size',f'{w}x{h}','-i','desktop',
        '-vf',','.join(filters),*encoder_args(ext,quality),str(target)]

class AudioRecorder:
    def __init__(self,device,path):
        import pyaudiowpatch as pa
        self.pa=pa.PyAudio(); self.path=path; self.error=None
        try:
            # Resolve this at each recording so a Windows playback-device change is respected.
            info=self.pa.get_default_wasapi_loopback() if device==DEFAULT_AUDIO else (self.pa.get_default_wasapi_device(d_in=True) if device==DEFAULT_MIC else self.pa.get_device_info_by_index(device))
            self.channels=min(2,int(info['maxInputChannels'])); self.rate=int(info['defaultSampleRate'])
            self.stream=self.pa.open(format=pa.paInt16,channels=self.channels,rate=self.rate,input=True,input_device_index=int(info['index']),frames_per_buffer=1024,start=False)
        except Exception:
            self.pa.terminate(); raise
        self.done=threading.Event(); self.started=False; self.stopped=False
        self.thread=threading.Thread(target=self.run,daemon=True)
    def run(self):
        try:
            with wave.open(str(self.path),'wb') as out:
                out.setnchannels(self.channels); out.setsampwidth(2); out.setframerate(self.rate)
                start=self.epoch; written=0
                while not self.done.is_set():
                    available=self.stream.get_read_available()
                    if available:
                        count=min(available,4096)
                        out.writeframesraw(self.stream.read(count,exception_on_overflow=False)); written+=count
                    else:
                        # WASAPI loopback supplies no packets when speakers are silent.
                        expected=int((time.monotonic()-start)*self.rate)
                        gap=expected-written-int(self.rate*.05)
                        if gap>self.rate*.1:
                            out.writeframesraw(bytes(gap*self.channels*2)); written+=gap
                        self.done.wait(.01)
                gap=max(0,int((time.monotonic()-start)*self.rate)-written)
                if gap: out.writeframesraw(bytes(gap*self.channels*2))
        except Exception as e: self.error=str(e)
    def start(self,epoch=None):
        self.epoch=time.monotonic() if epoch is None else epoch; self.stream.start_stream(); self.thread.start(); self.started=True
    def stop(self):
        if self.stopped: return
        self.done.set()
        if self.started: self.thread.join(5)
        self.stream.close(); self.pa.terminate()
        self.stopped=True
        if self.thread.is_alive(): raise RuntimeError('Audio capture did not stop.')
        if self.error: raise RuntimeError('Audio capture failed: '+self.error)

def stop_audio_capture(recorders):
    errors=[]
    for recorder in recorders:
        try: recorder.stop()
        except Exception as error: errors.append(str(error))
    if errors: raise RuntimeError('; '.join(errors))

def preview_audio_args(tracks,duration):
    """Mix independently scaled speaker and microphone tracks onto the video timeline."""
    args=[]; filters=[]
    for i,(path,gain) in enumerate(tracks):
        args+=['-i',str(path)]
        filters.append(f'[{i+1}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,volume={gain},apad,atrim=duration={duration},asetpts=PTS-STARTPTS[a{i}]')
    if len(tracks)>1:
        filters.append(''.join(f'[a{i}]' for i in range(len(tracks)))+f'amix=inputs={len(tracks)}:duration=longest:normalize=0:dropout_transition=0,alimiter=limit=0.95:level=false:latency=1[mixed]'); output='[mixed]'
    else: output='[a0]'
    return args+['-filter_complex',';'.join(filters),'-map','0:v:0','-map',output,'-c:v','copy','-t',str(duration),'-c:a','aac']

class Events(QObject):
    finished=Signal(str,str)

class HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self,window):
        super().__init__(); self.window=window
    def nativeEventFilter(self,event_type,message):
        msg=wintypes.MSG.from_address(int(message))
        if msg.message==0x0312 and msg.wParam==0x5352:
            if self.window.proc or self.window.pending: QTimer.singleShot(0,self.window.toggle)
            return True,0
        return False,0

class CardIcon(QWidget):
    def __init__(self,kind):
        super().__init__(); self.kind=kind; self.setFixedHeight(52)
    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing); p.translate(self.width()/2-22,3)
        p.setPen(QPen(QColor('#44484d'),2.5)); p.setBrush(Qt.NoBrush)
        if self.kind=='capture':
            for x,y,dx,dy in [(0,0,1,1),(44,0,-1,1),(0,44,1,-1),(44,44,-1,-1)]:
                p.drawLine(x,y,x+11*dx,y); p.drawLine(x,y,x,y+11*dy)
            p.drawRoundedRect(10,13,24,18,2,2); p.drawEllipse(17,17,9,9)
        elif self.kind=='audio':
            from PySide6.QtGui import QPolygon
            p.drawPolygon(QPolygon([QPoint(3,16),QPoint(13,16),QPoint(25,6),QPoint(25,38),QPoint(13,28),QPoint(3,28)]))
            p.drawArc(22,11,14,24,-70*16,140*16); p.drawArc(23,4,24,38,-65*16,130*16)
        elif self.kind=='mic':
            p.drawRoundedRect(15,0,14,27,7,7); p.drawArc(7,11,30,29,180*16,180*16)
            p.drawLine(22,40,22,46); p.drawLine(13,46,31,46)
        else:
            p.drawRoundedRect(3,0,38,44,3,3)
            p.drawLine(11,0,11,44); p.drawLine(33,0,33,44)
            for y in [11,22,33]: p.drawLine(3,y,41,y)

class CaptureFrame(QWidget):
    changed=Signal()
    stop_requested=Signal()
    BORDER=8
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Recording frame')
        self.setWindowFlags(Qt.FramelessWindowHint|Qt.WindowStaysOnTopHint|Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True); self.setMinimumSize(180,140)
        g=QApplication.primaryScreen().availableGeometry()
        self.setGeometry(g.x()+160,g.y()+160,656,376)
        self.locked=False; self.drag=None; self.apply_mask()
    def inner_rect(self): return self.rect().adjusted(self.BORDER,self.BORDER,-self.BORDER,-self.BORDER)
    def move_handle_rect(self):
        width=min(520,self.width()-40)
        return QRect((self.width()-width)//2,self.height()//2-40,width,100)
    def capture_rect(self):
        r=self.inner_rect(); point=self.mapToGlobal(r.topLeft()); return (point.x(),point.y(),r.width(),r.height())
    def apply_mask(self):
        region=QRegion(self.rect())
        if self.locked: region=region.subtracted(QRegion(self.inner_rect()))
        self.setMask(region)
    def set_locked(self,locked):
        self.locked=locked; self.apply_mask(); self.update()
    def resizeEvent(self,event):
        if hasattr(self,'locked'): self.apply_mask()
        self.changed.emit()
    def moveEvent(self,event): self.changed.emit()
    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        # A nearly invisible fill lets Windows hit-test the entire interior while positioning.
        if not self.locked: p.fillRect(self.inner_rect(),QColor(0,0,0,1))
        color=QColor('#ff4b40'); pen=QPen(color,4)
        pen.setDashPattern([12.5,12.5]); pen.setCapStyle(Qt.FlatCap)
        p.setPen(pen); p.drawRect(self.rect().adjusted(4,4,-4,-4))
        if self.locked: return
        p.setPen(color); font=p.font(); font.setFamily('Segoe UI'); font.setPointSize(15 if self.width()>=520 else 11); p.setFont(font)
        handle=self.move_handle_rect()
        p.drawText(handle.adjusted(0,0,0,-42),Qt.AlignCenter|Qt.TextWordWrap,'Drag anywhere inside to move • drag the border to resize')
        centre=QPoint(self.width()//2,handle.bottom()-20)
        p.setPen(QPen(color,2)); p.drawLine(centre+QPoint(-15,0),centre+QPoint(15,0)); p.drawLine(centre+QPoint(0,-15),centre+QPoint(0,15))
        from PySide6.QtGui import QPolygon
        p.setBrush(color)
        for dx,dy in [(1,0),(-1,0),(0,1),(0,-1)]:
            tip=centre+QPoint(dx*19,dy*19); base=centre+QPoint(dx*12,dy*12)
            p.drawPolygon(QPolygon([tip,base+QPoint(dy*5,dx*5),base-QPoint(dy*5,dx*5)]))
    def hit(self,point):
        x,y=point.x(),point.y(); margin=12
        return (x<margin,x>self.width()-margin,y<margin,y>self.height()-margin)
    def mousePressEvent(self,event):
        if self.locked or event.button()!=Qt.LeftButton: return
        point=event.position().toPoint(); edges=self.hit(point)
        if self.inner_rect().adjusted(5,5,-5,-5).contains(point): edges=(False,False,False,False)
        self.drag=(event.globalPosition().toPoint(),self.geometry(),edges); self.grabMouse()
    def mouseMoveEvent(self,event):
        if self.locked: self.setCursor(Qt.ArrowCursor); return
        if not self.drag:
            l,r,t,b=self.hit(event.position().toPoint())
            self.setCursor(Qt.SizeFDiagCursor if (l and t) or (r and b) else Qt.SizeBDiagCursor if (r and t) or (l and b) else Qt.SizeHorCursor if l or r else Qt.SizeVerCursor if t or b else Qt.SizeAllCursor); return
        origin,g,edges=self.drag; delta=event.globalPosition().toPoint()-origin; l,r,t,b=edges
        if not any(edges): self.move(g.topLeft()+delta); return
        left,top,width,height=g.x(),g.y(),g.width(),g.height()
        if l: left=min(g.x()+delta.x(),g.right()+1-self.minimumWidth()); width=g.right()+1-left
        if r: width=max(self.minimumWidth(),g.width()+delta.x())
        if t: top=min(g.y()+delta.y(),g.bottom()+1-self.minimumHeight()); height=g.bottom()+1-top
        if b: height=max(self.minimumHeight(),g.height()+delta.y())
        self.setGeometry(left,top,width,height)
    def mouseReleaseEvent(self,event): self.drag=None; self.releaseMouse(); self.changed.emit()

class CountdownOverlay(QWidget):
    def __init__(self):
        super().__init__(); self.number=3
        self.setWindowTitle('Recording countdown')
        self.setWindowFlags(Qt.FramelessWindowHint|Qt.WindowStaysOnTopHint|Qt.Tool|Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground); self.setAttribute(Qt.WA_TransparentForMouseEvents); self.setAttribute(Qt.WA_ShowWithoutActivating)
    def show_number(self,number,rect):
        self.number=number; x,y,w,h=rect; side=max(48,min(160,w-16,h-16))
        self.setGeometry(x+(w-side)//2,y+(h-side)//2,side,side); self.show(); self.raise_(); self.update()
    def paintEvent(self,event):
        painter=QPainter(self); painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor('#ff6b59'),4)); painter.setBrush(QColor(32,44,62,235)); painter.drawEllipse(self.rect().adjusted(4,4,-4,-4))
        font=QFont('Segoe UI'); font.setPixelSize(int(self.width()*.52)); font.setBold(True); painter.setFont(font); painter.setPen(Qt.white)
        painter.drawText(self.rect(),Qt.AlignCenter,str(self.number))

class ScreenLabel(QWidget):
    def __init__(self):
        super().__init__(); self.number=1; self.selected=False
        self.setWindowTitle('Screen identifier')
        self.setWindowFlags(Qt.FramelessWindowHint|Qt.WindowStaysOnTopHint|Qt.Tool|Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground); self.setAttribute(Qt.WA_TransparentForMouseEvents); self.setAttribute(Qt.WA_ShowWithoutActivating)
    def place(self,screen,number,selected):
        self.number=number; self.selected=selected; g=screen.geometry()
        self.setGeometry(g.x()+(g.width()-180)//2,g.y()+18,180,52); self.update()
    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor('#26364b')); p.setPen(QPen(QColor('#ff705b' if self.selected else '#687b91'),2))
        p.drawRoundedRect(self.rect().adjusted(2,2,-2,-2),10,10)
        font=QFont('Segoe UI'); font.setPixelSize(21); font.setBold(True); p.setFont(font); p.setPen(Qt.white)
        p.drawText(self.rect(),Qt.AlignCenter,f'Screen {self.number}')

class SaveLocationButton(QPushButton):
    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor('#ffffff' if self.isEnabled() else '#f0f2f5')); p.setPen(QPen(QColor('#cbd4df'),1))
        p.drawRoundedRect(self.rect().adjusted(1,1,-1,-1),5,5)
        QIcon(asset_path('folder.svg')).paint(p,QRect(12,(self.height()-18)//2,18,18))
        font=QFont('Segoe UI'); font.setPixelSize(13); p.setFont(font); p.setPen(QColor('#454b54' if self.isEnabled() else '#949ca6'))
        text=p.fontMetrics().elidedText(self.text(),Qt.ElideMiddle,max(0,self.width()-52))
        p.drawText(self.rect().adjusted(40,0,-12,0),Qt.AlignVCenter|Qt.AlignLeft,text)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle(NAME); self.setWindowIcon(QIcon(asset_path('recorder.png'))); self.setFixedSize(1000,340)
        self.proc=None; self.audio_rec=None; self.mic_rec=None; self.region=None; self.pending=False; self.busy=False; self.last_file=None
        self.launch_scheduled=False; self.countdown=CountdownOverlay(); self.extra_countdowns=[]; self.capture_screens=None; self.screen_labels=[]; self.screen_connections=[]
        self.events=Events(); self.events.finished.connect(self.completed)
        self.config=Path(os.environ.get('APPDATA',str(Path.home()))) / 'SimpleScreenRecorder' / 'settings.json'
        self.frame=CaptureFrame(); self.frame.changed.connect(self.update_frame_label)
        self.frame.stop_requested.connect(self.toggle)
        self.setStyleSheet('QWidget{background:#f4f6f9;color:#454b54;font:14px "Segoe UI";} QPushButton,QComboBox{background:#f8f9fb;border:1px solid white;border-radius:12px;padding:8px;} QPushButton:hover{background:#e7edf5;} QComboBox QAbstractItemView{background:white;border:1px solid #dce2ea;selection-background-color:#edf1f7;selection-color:#333d4b;padding:6px;} QPushButton#record{background:#ff705b;color:white;font-size:30px;border:6px solid #ffe6df;border-radius:66px;} QPushButton#coffee{background:#ffdd70;border:0;border-radius:9px;font-size:13px;padding:8px 14px;} QLabel#status{color:#737c88;font-size:13px;} QPushButton#footer{border:0;background:white;color:#606976;font-size:14px;padding:10px 12px;}'+TOOLTIP_STYLE)
        body=QWidget(); self.setCentralWidget(body); layout=QVBoxLayout(body); layout.setContentsMargins(28,14,28,0); layout.setSpacing(0)
        header=QHBoxLayout(); header.setSpacing(10); header.setContentsMargins(0,0,0,12); name=QLabel(NAME); name.setStyleSheet('color:#707985;font-size:14px;font-weight:600;'); header.addWidget(name); header.addStretch()
        coffee=QPushButton('Buy me a coffee'); coffee.setIcon(QIcon(asset_path('coffee.svg'))); coffee.setObjectName('coffee'); coffee.clicked.connect(lambda:QDesktopServices.openUrl(QUrl(COFFEE))); header.addWidget(coffee)
        self.github=QPushButton('GitHub'); self.github.setIcon(QIcon(asset_path('github.svg'))); self.github.setObjectName('github'); self.github.setStyleSheet('background:#26364b;color:white;border:0;border-radius:9px;font-size:13px;padding:8px 14px;'); self.github.clicked.connect(lambda:QDesktopServices.openUrl(QUrl(GITHUB))); header.addWidget(self.github); layout.addLayout(header)
        row=QHBoxLayout(); row.setSpacing(14); row.setContentsMargins(0,4,0,18)
        self.mode=SelectorCombo(); self.mode.setAccessibleName('Capture area'); self.mode.setToolTip(tooltip_text('Choose a connected screen or a movable recording area'))
        self.audio=SelectorCombo(); self.audio.addItem('Windows default playback device',DEFAULT_AUDIO); self.audio.setItemData(0,'Windows default',Qt.UserRole+1); self.audio.addItem('Mute',None); self.audio.setAccessibleName('Speaker source'); self.audio.setToolTip(tooltip_text('Follows the Windows playback device by default; choose another speaker device or Mute'))
        self.mic=SelectorCombo(); self.mic.addItem('Mute',None); self.mic.setAccessibleName('Microphone source'); self.mic.setToolTip(tooltip_text('Microphone is muted by default. Choose a Windows input device to record narration.')); self.populate_audio()
        self.format=SelectorCombo(); self.format.addItems(['MP4','MKV','AVI','WebM']); self.format.setAccessibleName('File type')
        for title,icon,combo in [('Capture','capture',self.mode),('Speakers','audio',self.audio),('Mic','mic',self.mic),('Format','video',self.format)]:
            card=QWidget(); card.setFixedSize(152,146); card.setObjectName('captureCard'); card.setStyleSheet('QWidget#captureCard{background:#f8f9fb;border:1px solid white;border-radius:14px;}')
            stack=QVBoxLayout(card); stack.setContentsMargins(12,12,12,10); stack.setSpacing(4)
            label=QLabel(title); label.setAlignment(Qt.AlignCenter); label.setStyleSheet('background:transparent;color:#7a8390;font-size:12px;'); stack.addWidget(label)
            symbol=CardIcon(icon); stack.addWidget(symbol)
            combo.setStyleSheet('QComboBox{border:0;background:transparent;border-radius:0px;padding:0;}'+TOOLTIP_STYLE); stack.addWidget(combo); row.addWidget(card)
        self.volume,self.sound_label=self.volume_column(row,'Speakers'); self.mic_volume,self.mic_sound_label=self.volume_column(row,'Mic'); row.addStretch()
        self.record=QPushButton('Start'); self.record.setObjectName('record'); self.record.setStyleSheet('border-radius:60px;'); self.record.setFixedSize(126,126); self.record.clicked.connect(self.toggle); row.addWidget(self.record,0,Qt.AlignVCenter); layout.addLayout(row)
        info=QHBoxLayout(); info.setContentsMargins(0,0,0,14); info.setSpacing(14); self.folder=QLineEdit(str(Path.home()/'Videos')); self.folder.hide()
        save_label=QLabel('Save Location:'); save_label.setStyleSheet('color:#727c89;font-size:13px;'); info.addWidget(save_label)
        self.folder_button=SaveLocationButton(); self.folder_button.setAccessibleName('Save location'); self.folder_button.setFixedHeight(36); self.folder_button.setMinimumWidth(240); self.folder_button.setMaximumWidth(480); self.folder_button.setCursor(Qt.PointingHandCursor); self.folder_button.clicked.connect(self.browse); info.addWidget(self.folder_button,1)
        self.space=QLabel(''); self.space.setStyleSheet('color:#727c89;font-size:13px;'); info.addWidget(self.space)
        self.status=QLabel('Ready'); self.status.setObjectName('status'); info.addStretch(); info.addWidget(self.status); layout.addLayout(info)
        footer=QWidget(); footer.setStyleSheet('background:white;'); bottom=QHBoxLayout(footer); bottom.setContentsMargins(0,1,0,1); bottom.setSpacing(8)
        for label,icon,callback in [('Media','folder.svg',self.open_folder),('Show frame','frame.svg',self.show_frame),('Help','help.svg',self.help)]:
            button=QPushButton(label); button.setIcon(QIcon(asset_path(icon))); button.setObjectName('footer'); button.clicked.connect(callback); bottom.addWidget(button)
        bottom.addStretch(); hint=QLabel('Ctrl + Shift + F10 to stop'); hint.setStyleSheet('color:#8e97a3;font-size:12px;'); bottom.addWidget(hint); layout.addStretch(); layout.addWidget(footer)
        # Sensible defaults keep the recorder toolbar compact.
        self.quality=QComboBox(); self.quality.addItem('Balanced'); self.quality.hide()
        self.fps=QComboBox(); self.fps.addItem('30'); self.fps.hide()
        self.delay=QSpinBox(); self.delay.setValue(3); self.delay.hide()
        self.cursor=QCheckBox(); self.cursor.setChecked(True); self.cursor.hide()
        self.minimize=QCheckBox(); self.minimize.setChecked(True); self.minimize.hide()
        self.select=QPushButton(); self.select.hide(); self.target=QLabel(); self.target.hide()
        self.audio.currentIndexChanged.connect(self.update_audio_controls); self.mic.currentIndexChanged.connect(self.update_audio_controls); self.update_audio_controls()
        self.audio.opening.connect(self.refresh_audio_devices); self.mic.opening.connect(self.refresh_audio_devices)
        try:
            data=json.loads(self.config.read_text()); self.folder.setText(data['folder']); self.format.setCurrentText(data.get('format','MP4'))
        except (OSError,ValueError,KeyError): pass
        self.update_save_location()
        self.mode.currentIndexChanged.connect(self.mode_changed); self.refresh_screens()
        QApplication.instance().screenAdded.connect(self.refresh_screens); QApplication.instance().screenRemoved.connect(self.refresh_screens)
        self.timer=QTimer(self); self.timer.timeout.connect(self.tick); self.timer.start(250)
        self.hotkey=bool(ctypes.windll.user32.RegisterHotKey(None,0x5352,0x4000|0x0002|0x0004,0x79))
        self.hotkey_filter=HotkeyFilter(self); QApplication.instance().installNativeEventFilter(self.hotkey_filter)
        if not self.hotkey: self.status.setText('Use Stop button')
        self.update_space()
    def open_folder(self): QDesktopServices.openUrl(QUrl.fromLocalFile(self.folder.text()))
    def volume_column(self,row,title):
        column=QVBoxLayout(); column.addStretch(); slider=QSlider(Qt.Vertical); slider.setRange(0,100); slider.setValue(100); slider.setFixedSize(24,72); slider.setAccessibleName(title+' recording volume'); slider.setToolTip(tooltip_text(title+' recording volume'))
        slider.setStyleSheet('QSlider::groove:vertical{background:#dde1e6;width:3px;} QSlider::handle:vertical{background:white;border:1px solid #d4dce6;height:10px;margin:0 -4px;border-radius:5px;} QSlider::handle:vertical:disabled{background:#e7ebf0;} QSlider::sub-page:vertical{background:#ffb4a6;}')
        column.addWidget(slider,0,Qt.AlignHCenter); label=QLabel(title); label.setFixedWidth(54); label.setAlignment(Qt.AlignCenter); label.setStyleSheet('font-size:11px;color:#7a8390;'); column.addWidget(label); column.addStretch(); row.addLayout(column); return slider,label
    def update_audio_controls(self):
        locked=bool(self.proc or self.pending or self.busy)
        self.volume.setEnabled(not locked and self.audio.currentData() is not None); self.mic_volume.setEnabled(not locked and self.mic.currentData() is not None)
    def active_recorders(self): return [recorder for recorder in [self.audio_rec,self.mic_rec] if recorder is not None]
    def update_save_location(self):
        self.folder_button.setText(self.folder.text()); self.folder_button.setToolTip(tooltip_text(self.folder.text())); self.folder_button.update()
    def update_space(self):
        try:
            import shutil
            free=shutil.disk_usage(self.folder.text()).free/1024**3; self.space.setText(f'Space  {free:.0f} GB')
        except OSError: self.space.setText('')
    def browse(self):
        if self.proc or self.pending or self.busy: return
        path=QFileDialog.getExistingDirectory(self,'Choose recording folder',self.folder.text())
        if path: self.folder.setText(path); self.update_save_location(); self.update_space()
    def help(self):
        QMessageBox.information(self,NAME,'Choose Full Screen 1, Full Screen 2, etc. to record that monitor, or Area for a floating recording frame. Choose Record all screens to save one video matching the Windows monitor layout. Gaps between monitors appear black. With one monitor, choose Full Screen. The screen numbers appear at the top of each monitor before recording. Click the bordered Save Location field to choose where recordings are saved.\n\nDrag anywhere inside the frame to move it. Drag any edge or corner to resize it. Move it to any monitor. The clear inside area is recorded. The border stays outside it, and the central guide disappears before recording.\n\nClick Start for a large 3-2-1 countdown over the capture area. The frame locks while recording. Stop with Ctrl + Shift + F10, the recorder Stop button.\n\nSpeakers follows the Windows playback device by default. The separate Mic selector starts muted; choose a Windows input to include narration. Speakers and Mic have independent recording-volume sliders and can be recorded together. Keep CCTV visible and uncovered. MP4 is the usual choice. Media opens your output folder. Video records at 30 FPS. After Stop, review the preview, trim the yellow timeline handles, enable Crop picture if needed, and choose the export format. Export video saves your edits; Keep original or closing the export window keeps the full recording as MP4.')
    def connected_screens(self): return QApplication.screens()
    def is_area(self): return self.mode.currentData() is None
    def is_all_screens(self): return self.mode.currentData()==ALL_SCREENS
    def screen_rects(self):
        return [(g.x(),g.y(),g.width(),g.height()) for g in [screen.geometry() for screen in self.connected_screens()]]
    def refresh_screens(self,*args):
        previous=self.mode.currentData(); area=self.mode.count()>0 and self.is_area(); screens=self.connected_screens()
        if self.pending and previous is not None and (previous==ALL_SCREENS or previous not in screens): self.toggle()
        for screen in self.screen_connections:
            try: screen.geometryChanged.disconnect(self.update_screen_labels)
            except (RuntimeError,TypeError): pass
        self.screen_connections=list(screens)
        for screen in screens: screen.geometryChanged.connect(self.update_screen_labels)
        self.mode.blockSignals(True); self.mode.clear()
        for i,screen in enumerate(screens): self.mode.addItem('Full Screen' if len(screens)==1 else f'Full Screen {i+1}',screen)
        if len(screens)>1:
            self.mode.addItem('Record all screens',ALL_SCREENS); self.mode.setItemData(self.mode.count()-1,'All screens',Qt.UserRole+1)
        self.mode.addItem('Area',None)
        self.mode.setCurrentIndex(self.mode.count()-1 if area else (self.mode.findData(ALL_SCREENS) if previous==ALL_SCREENS and len(screens)>1 else (screens.index(previous) if previous in screens else 0))); self.mode.blockSignals(False)
        for label in self.screen_labels: label.close(); label.deleteLater()
        self.screen_labels=[ScreenLabel() for screen in screens]
        self.mode_changed()
    def update_screen_labels(self,*args):
        visible=not self.is_area() and not (self.pending or self.proc or self.busy)
        for i,(screen,label) in enumerate(zip(self.connected_screens(),self.screen_labels)):
            label.place(screen,i+1,self.is_all_screens() or screen==self.mode.currentData()); label.setVisible(visible)
    def mode_changed(self):
        if self.is_area(): self.frame.show(); self.frame.raise_(); self.update_frame_label()
        else:
            self.frame.hide()
            if not (self.pending or self.proc or self.busy): self.status.setText(self.mode.currentText())
        self.update_screen_labels()
    def show_frame(self):
        if self.proc or self.pending or self.busy:
            if self.is_area(): self.frame.show(); self.frame.raise_()
            return
        self.mode.setCurrentIndex(self.mode.count()-1); self.frame.show(); self.frame.raise_()
    def update_frame_label(self):
        if self.is_area() and not (self.proc or self.pending or self.busy):
            r=self.frame.capture_rect(); self.status.setText(f'Box  {r[2]} × {r[3]}')
    def get_rect(self):
        if self.is_all_screens():
            screens=self.screen_rects()
            if not screens: raise RuntimeError('No connected screens are available.')
            left=min(x for x,y,w,h in screens); top=min(y for x,y,w,h in screens)
            return (left,top,max(x+w for x,y,w,h in screens)-left,max(y+h for x,y,w,h in screens)-top)
        if not self.is_area():
            screen=self.mode.currentData()
            if screen not in self.connected_screens(): raise RuntimeError('The selected screen is no longer connected.')
            g=screen.geometry(); return (g.x(),g.y(),g.width(),g.height())
        return self.frame.capture_rect()
    def hide_countdown(self):
        self.countdown.hide()
        for overlay in self.extra_countdowns: overlay.hide()
    def show_countdown(self,number):
        rects=self.capture_screens or [self.region]
        while len(self.extra_countdowns)<len(rects)-1: self.extra_countdowns.append(CountdownOverlay())
        for overlay,rect in zip([self.countdown]+self.extra_countdowns,rects): overlay.show_number(number,rect)
    def lock(self,locked):
        for widget in [self.mode,self.audio,self.mic,self.format,self.folder_button,self.volume,self.mic_volume]: widget.setEnabled(not locked)
        self.update_audio_controls()
        self.frame.set_locked(locked)
        self.update_screen_labels()
        if not locked: self.record.setText('Start')
    def populate_audio(self):
        try:
            import pyaudiowpatch as pa
            with pa.PyAudio() as p:
                counts={}; wasapi=p.get_host_api_info_by_type(pa.paWASAPI)['index']; inputs=[]
                for i in range(p.get_device_count()):
                    d=p.get_device_info_by_index(i)
                    if d['maxInputChannels']>0 and (d.get('isLoopbackDevice') or d['hostApi']==wasapi):
                        kind='Speakers' if d.get('isLoopbackDevice') else 'Microphone'; combo=self.audio if kind=='Speakers' else self.mic
                        name=d['name'].replace(' [Loopback]','').strip(); key=(kind,name); counts[key]=counts.get(key,0)+1
                        suffix=f' ({counts[key]})' if counts[key]>1 else ''
                        combo.addItem(name+suffix,i); combo.setItemData(combo.count()-1,kind,Qt.UserRole+1); combo.setItemData(combo.count()-1,tooltip_text(d['name']),Qt.ToolTipRole)
                        if kind=='Microphone': inputs.append(i)
                if inputs:
                    self.mic.insertItem(1,'Windows default input device',DEFAULT_MIC); self.mic.setItemData(1,'Windows default',Qt.UserRole+1)
                else: self.mic.setToolTip(tooltip_text('No Windows microphone/input devices are connected. Microphone recording is muted.'))
        except Exception as e:
            self.audio.setToolTip(tooltip_text('Speaker audio unavailable: '+str(e))); self.mic.setToolTip(tooltip_text('Microphone input unavailable: '+str(e)))
    def refresh_audio_devices(self):
        previous=[(combo.currentData(),combo.currentText()) for combo in [self.audio,self.mic]]
        for combo in [self.audio,self.mic]: combo.blockSignals(True); combo.clear()
        self.audio.addItem('Windows default playback device',DEFAULT_AUDIO); self.audio.setItemData(0,'Windows default',Qt.UserRole+1); self.audio.addItem('Mute',None)
        self.mic.addItem('Mute',None); self.populate_audio()
        for combo,(data,text) in zip([self.audio,self.mic],previous):
            index=combo.findData(data) if not isinstance(data,int) else combo.findText(text)
            combo.setCurrentIndex(index if index>=0 else 0); combo.blockSignals(False); combo.update()
        self.update_audio_controls()
    def toggle(self):
        if self.busy: return
        if self.pending:
            self.pending=False; self.launch_scheduled=False; self.hide_countdown(); self.lock(False); self.status.setText('Countdown cancelled'); return
        if self.proc: self.stop(); return
        try:
            self.refresh_audio_devices()
            rect=self.get_rect(); self.region=rect; self.capture_screens=self.screen_rects() if self.is_all_screens() else None; folder=Path(self.folder.text()).expanduser(); folder.mkdir(parents=True,exist_ok=True)
            with tempfile.TemporaryFile(dir=folder): pass
            self.config.parent.mkdir(parents=True,exist_ok=True); self.config.write_text(json.dumps({'folder':str(folder),'format':self.format.currentText(),'fps':self.fps.currentText()}))
            self.deadline=time.monotonic()+self.delay.value(); self.pending=True; self.launch_scheduled=False; self.lock(True); self.record.setText('Cancel')
            if self.delay.value()>0: self.show_countdown(self.delay.value())
        except Exception as e: QMessageBox.warning(self,NAME,str(e))
    def start(self):
        self.pending=False; self.launch_scheduled=False; self.hide_countdown()
        try:
            self.volume_gain=self.volume.value()/100; self.mic_gain=self.mic_volume.value()/100
            rect=self.region; self.scratch=tempfile.TemporaryDirectory(prefix='screen-recorder-'); scratch=Path(self.scratch.name)
            ext='mp4'; self.output=Path(self.folder.text())/f'Recording-{datetime.now():%Y-%m-%d_%H-%M-%S-%f}.{self.format.currentText().lower()}'
            self.video=scratch/('capture.'+ext); self.wav=scratch/'audio.wav'; self.mic_wav=scratch/'microphone.wav'; self.audio_rec=None; self.mic_rec=None
            if self.audio.currentData() is not None: self.audio_rec=AudioRecorder(self.audio.currentData(),self.wav)
            if self.mic.currentData() is not None: self.mic_rec=AudioRecorder(self.mic.currentData(),self.mic_wav)
            self.log=open(scratch/'capture.log','wb')
            epoch=time.monotonic()
            for recorder in self.active_recorders(): recorder.start(epoch)
            self.proc=subprocess.Popen(capture_args(rect,int(self.fps.currentText()),self.cursor.isChecked(),ext,self.quality.currentText(),self.video,self.capture_screens),stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=self.log,creationflags=CREATE_NO_WINDOW)
            self.started=time.monotonic(); self.record.setText('Stop'); self.status.setText('Recording…')
            if self.minimize.isChecked(): self.showMinimized()
        except Exception as e:
            try: stop_audio_capture(self.active_recorders())
            except Exception: pass
            self.audio_rec=None; self.mic_rec=None; self.proc=None; self.lock(False); QMessageBox.critical(self,NAME,str(e))
    def tick(self):
        if self.pending:
            if self.launch_scheduled: return
            left=self.deadline-time.monotonic()
            if left<=0:
                self.hide_countdown(); self.launch_scheduled=True
                # Let the desktop compositor remove the countdown before the first captured frame.
                QTimer.singleShot(120,lambda:self.start() if self.pending and self.launch_scheduled else None)
            else:
                number=math.ceil(left); self.status.setText(f'Starting in {number}…'); self.show_countdown(number)
        elif self.proc and not self.busy:
            elapsed=int(time.monotonic()-self.started); self.status.setText(f'● {elapsed//3600:02}:{elapsed//60%60:02}:{elapsed%60:02}')
            if self.proc.poll() is not None: self.stop()
    def stop(self):
        if self.busy: return
        self.busy=True; self.record.setEnabled(False); self.status.setText('Preparing preview…'); self.showNormal()
        threading.Thread(target=self.finish,daemon=True).start()
    def finish(self):
        error=''; path=''
        try:
            if self.proc.poll() is None:
                try: self.proc.stdin.write(b'q\n'); self.proc.stdin.flush()
                except BrokenPipeError: pass
            try: code=self.proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.proc.kill(); self.proc.wait(); raise RuntimeError('Recorder timed out. Temporary footage has been retained.')
            stop_audio_capture(self.active_recorders())
            self.log.close()
            if code!=0 or not self.video.exists() or self.video.stat().st_size<100:
                raise RuntimeError((Path(self.scratch.name)/'capture.log').read_text(errors='replace')[-2200:] or 'No footage captured. Wait a few seconds before stopping.')
            cmd=[ffmpeg_exe(),'-hide_banner','-loglevel','error','-n','-i',str(self.video)]
            if self.active_recorders():
                probe=subprocess.run([ffmpeg_exe(),'-hide_banner','-i',str(self.video)],capture_output=True,creationflags=CREATE_NO_WINDOW,timeout=15)
                match=re.search(r'Duration: (\d+):(\d+):(\d+\.\d+)',probe.stderr.decode(errors='replace'))
                if not match: raise RuntimeError('Cannot determine recording duration for audio saving.')
                duration=int(match[1])*3600+int(match[2])*60+float(match[3])
                tracks=[]
                if self.audio_rec: tracks.append((self.wav,self.volume_gain))
                if self.mic_rec: tracks.append((self.mic_wav,self.mic_gain))
                cmd+=preview_audio_args(tracks,duration)
            else: cmd+=['-c','copy']
            preview=Path(self.scratch.name)/'preview.mp4'; cmd+=['-movflags','+faststart',str(preview)]
            result=subprocess.run(cmd,capture_output=True,creationflags=CREATE_NO_WINDOW,timeout=300)
            if result.returncode: raise RuntimeError(result.stderr.decode(errors='replace')[-2000:])
            path=str(preview)
        except Exception as e:
            try: stop_audio_capture(self.active_recorders())
            except Exception: pass
            error=str(e)
            # Retain recoverable footage after a save failure.
            if hasattr(self,'scratch'):
                self.scratch._finalizer.detach(); error+='\nRecovery files: '+self.scratch.name
        self.events.finished.emit(path,error)
    def completed(self,path,error):
        self.proc=None; self.audio_rec=None; self.mic_rec=None
        if error:
            self.status.setText('Recording could not be prepared'); QMessageBox.critical(self,NAME,error)
        else:
            self.frame.hide()
            try:
                dialog=ExportDialog(path,self.output,self.format.currentText(),ffmpeg_exe(),self); self.export_dialog=dialog; dialog.exec()
                if dialog.saved_path:
                    self.last_file=dialog.saved_path; self.status.setText('Saved'); self.status.setToolTip(tooltip_text(dialog.saved_path))
                    try: self.scratch.cleanup()
                    except OSError: self.scratch._finalizer.detach()
                else: self.scratch._finalizer.detach(); self.status.setText('Recording retained'); self.status.setToolTip(tooltip_text(path))
                dialog.deleteLater(); self.export_dialog=None
            except Exception as failure:
                self.scratch._finalizer.detach(); QMessageBox.critical(self,NAME,f'{failure}\nYour recording is safe at:\n{path}')
        self.busy=False; self.record.setEnabled(True); self.lock(False); self.update_space()
        if self.is_area(): self.frame.show()
    def closeEvent(self,e):
        if self.busy: e.ignore(); return
        if self.proc:
            self.stop(); e.ignore(); return
        if self.pending: self.pending=False
        if self.hotkey: ctypes.windll.user32.UnregisterHotKey(None,0x5352)
        QApplication.instance().removeNativeEventFilter(self.hotkey_filter)
        self.frame.close()
        self.countdown.close()
        for overlay in self.extra_countdowns: overlay.close()
        for label in self.screen_labels: label.close()
        QApplication.instance().screenAdded.disconnect(self.refresh_screens); QApplication.instance().screenRemoved.disconnect(self.refresh_screens)
        for screen in self.screen_connections:
            try: screen.geometryChanged.disconnect(self.update_screen_labels)
            except (RuntimeError,TypeError): pass
        e.accept()

def main():
    # Physical-pixel coordinates are necessary for desktop capture on mixed-DPI monitors.
    os.environ['QT_ENABLE_HIGHDPI_SCALING']='0'
    os.environ['QT_AUTO_SCREEN_SCALE_FACTOR']='0'
    os.environ['QT_SCALE_FACTOR']='1'
    try: ctypes.windll.user32.SetProcessDPIAware()
    except Exception: pass
    try: ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('SimpleScreenRecorder.Desktop')
    except Exception: pass
    app=QApplication(sys.argv); app.setApplicationName(NAME); app.setApplicationVersion(VERSION)
    app.setWindowIcon(QIcon(asset_path('recorder.png')))
    window=MainWindow(); window.show(); sys.exit(app.exec())

if __name__=='__main__': main()
