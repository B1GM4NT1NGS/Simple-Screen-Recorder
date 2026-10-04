"""Video review, timeline trimming and local export."""
import math, os, re, shutil, subprocess, tempfile, threading
from html import escape
from pathlib import Path
from PySide6.QtCore import Qt, QRectF, QTimer, QUrl, Signal, QObject, QEvent
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap, QPalette
from PySide6.QtWidgets import (QDialog, QWidget, QLabel, QPushButton, QComboBox,
    QDoubleSpinBox, QHBoxLayout, QVBoxLayout, QFileDialog, QMessageBox, QProgressBar, QListView)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QVideoSink

NO_WINDOW=0x08000000
TOOLTIP_STYLE='QToolTip{background-color:#ffffff;color:#243449;border:1px solid #d8e0ea;border-radius:6px;padding:8px;font:13px "Segoe UI";max-width:320px;}'

def tooltip_text(text):
    """Rich text lets Qt wrap long hints and device names onto short lines."""
    return '<qt>'+escape(str(text))+'</qt>'

def video_info(ffmpeg,source):
    result=subprocess.run([ffmpeg,'-hide_banner','-i',str(source)],capture_output=True,creationflags=NO_WINDOW,timeout=30)
    text=result.stderr.decode(errors='replace'); match=re.search(r'Duration: (\d+):(\d+):(\d+\.\d+)',text)
    if not match: raise RuntimeError('The recording duration could not be read.')
    size=re.search(r'Video:.*?\b(\d{2,6})x(\d{2,6})\b',text)
    if not size: raise RuntimeError('The video dimensions could not be read.')
    return int(match[1])*3600+int(match[2])*60+float(match[3]),int(size[1]),int(size[2])

def video_duration(ffmpeg,source): return video_info(ffmpeg,source)[0]

def export_args(ffmpeg,source,target,start,end,ext,crop=None):
    if start<0 or end<=start: raise ValueError('Choose a trim range with an end after its start.')
    if ext not in ['mp4','mkv','avi','webm']: raise ValueError('Choose MP4, MKV, AVI or WebM.')
    video=['-c:v','libvpx-vp9','-deadline','realtime','-cpu-used','6','-crf','31','-b:v','0'] if ext=='webm' else ['-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p']
    audio='libopus' if ext=='webm' else ('pcm_s16le' if ext=='avi' else 'aac')
    filters=[]
    if crop:
        x,y,w,h=crop
        if x<0 or y<0 or w<16 or h<16: raise ValueError('Choose a crop at least 16 pixels wide and high.')
        filters.append(f'crop={w}:{h}:{x}:{y}:exact=1')
    filters.append('pad=ceil(iw/2)*2:ceil(ih/2)*2')
    return [ffmpeg,'-hide_banner','-loglevel','error','-n','-ss',f'{start:.6f}','-i',str(source),'-t',f'{end-start:.6f}',
        '-map','0:v:0','-map','0:a:0?','-vf',','.join(filters),*video,'-c:a',audio,*(['-movflags','+faststart'] if ext=='mp4' else []),str(target)]

def write_export(ffmpeg,source,target,start,end,crop=None):
    target=Path(target); target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists(): raise FileExistsError('A file with this name already exists. Choose a new name.')
    with tempfile.TemporaryDirectory(prefix='.recording-export-',dir=target.parent) as folder:
        partial=Path(folder)/('video'+target.suffix)
        command=export_args(ffmpeg,source,partial,start,end,target.suffix[1:].lower(),crop)
        if crop is None and start==0 and target.suffix.lower() in ['.mp4','.mkv'] and end>=video_duration(ffmpeg,source)-.01:
            command=[ffmpeg,'-v','error','-n','-i',str(source),'-map','0:v:0','-map','0:a:0?','-c','copy',*(['-movflags','+faststart'] if target.suffix.lower()=='.mp4' else []),str(partial)]
        result=subprocess.run(command,capture_output=True,creationflags=NO_WINDOW)
        if result.returncode: raise RuntimeError(result.stderr.decode(errors='replace')[-1800:] or 'Export failed.')
        if not partial.exists() or partial.stat().st_size<100: raise RuntimeError('Export did not produce a video.')
        # Windows rename refuses an existing destination, including a file created during export.
        os.rename(partial,target)

def timestamp(seconds):
    total=max(0,int(seconds*100)); return f'{total//360000:02}:{total//6000%60:02}:{total//100%60:02}.{total%100:02}'

class TrimTimeline(QWidget):
    range_changed=Signal(float,float,str)
    seek_requested=Signal(float)
    def __init__(self,duration):
        super().__init__(); self.duration=duration; self.start=0.; self.end=duration; self.position=0.; self.image=QPixmap(); self.drag=None
        self.setFixedHeight(78); self.setMinimumWidth(300); self.setFocusPolicy(Qt.StrongFocus); self.setMouseTracking(True)
        self.setAccessibleName('Recording trim timeline'); self.setToolTip(tooltip_text('Drag the yellow handles to trim. Click between them to scrub.'))
    def x_for(self,value): return 16+(self.width()-32)*value/self.duration
    def time_for(self,x): return max(0,min(self.duration,(x-16)/(self.width()-32)*self.duration))
    def set_range(self,start,end): self.start=start; self.end=end; self.update()
    def set_position(self,position): self.position=position; self.update()
    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing); track=QRectF(16,8,self.width()-32,60)
        p.setPen(Qt.NoPen); p.setBrush(QColor('#243449')); p.drawRoundedRect(track,6,6)
        if not self.image.isNull(): p.drawPixmap(track.toRect(),self.image)
        left=self.x_for(self.start); right=self.x_for(self.end)
        p.fillRect(QRectF(16,8,max(0,left-16),60),QColor(20,29,42,180)); p.fillRect(QRectF(right,8,max(0,self.width()-16-right),60),QColor(20,29,42,180))
        p.setBrush(Qt.NoBrush); p.setPen(QPen(QColor('#ffcf55'),4)); p.drawRoundedRect(QRectF(left,8,right-left,60),5,5)
        for x in [left,right]:
            p.setPen(Qt.NoPen); p.setBrush(QColor('#ffcf55')); p.drawRoundedRect(QRectF(x-7,6,14,64),4,4)
            p.setPen(QPen(QColor('#806120'),2,Qt.SolidLine,Qt.RoundCap)); p.drawLine(int(x),26,int(x),50)
        if self.start<=self.position<=self.end:
            p.setPen(QPen(Qt.white,2)); x=int(self.x_for(self.position)); p.drawLine(x,12,x,64)
    def mousePressEvent(self,event):
        if event.button()!=Qt.LeftButton: return
        x=event.position().x(); left=self.x_for(self.start); right=self.x_for(self.end)
        self.drag='start' if abs(x-left)<=15 and abs(x-left)<=abs(x-right) else ('end' if abs(x-right)<=15 else 'seek')
        self.mouseMoveEvent(event)
    def mouseMoveEvent(self,event):
        if not self.isEnabled(): return
        if not self.drag:
            x=event.position().x(); self.setCursor(Qt.SizeHorCursor if min(abs(x-self.x_for(self.start)),abs(x-self.x_for(self.end)))<=15 else Qt.PointingHandCursor); return
        value=self.time_for(event.position().x()); minimum=min(.1,self.duration)
        if self.drag=='start': self.start=min(value,self.end-minimum)
        elif self.drag=='end': self.end=max(value,self.start+minimum)
        else: self.seek_requested.emit(max(self.start,min(self.end,value))); return
        self.update(); self.range_changed.emit(self.start,self.end,self.drag)
    def mouseReleaseEvent(self,event): self.drag=None

class ExportEvents(QObject):
    thumbnails=Signal(bytes)
    finished=Signal(str,str)

class VideoPreview(QWidget):
    """Paint video frames in the same surface as the crop controls."""
    def __init__(self):
        super().__init__(); self.frame=None; self.sink=QVideoSink(self); self.sink.videoFrameChanged.connect(self.receive_frame)
    def videoSink(self): return self.sink
    def receive_frame(self,frame):
        image=frame.toImage()
        if not image.isNull(): self.frame=image; self.update()
    def paintEvent(self,event):
        p=QPainter(self); p.fillRect(self.rect(),QColor('#172233'))
        if self.frame is not None:
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            size=self.frame.size().scaled(self.size(),Qt.KeepAspectRatio); left=(self.width()-size.width())//2; top=(self.height()-size.height())//2
            p.drawImage(QRectF(left,top,size.width(),size.height()),self.frame)

class CropOverlay(QWidget):
    changed=Signal()
    def __init__(self,width,height,parent):
        super().__init__(parent); self.source_width=width; self.source_height=height; self.crop=QRectF(0,0,1,1); self.drag=None
        self.setAttribute(Qt.WA_TranslucentBackground); self.setStyleSheet('QWidget{background:transparent;}'+TOOLTIP_STYLE); self.setMouseTracking(True); self.setAccessibleName('Picture crop area')
        self.setToolTip(tooltip_text('Drag inside to move the crop. Drag any edge or corner to resize.'))
    def video_rect(self):
        scale=min(self.width()/self.source_width,self.height()/self.source_height)
        w=self.source_width*scale; h=self.source_height*scale; return QRectF((self.width()-w)/2,(self.height()-h)/2,w,h)
    def selection_rect(self):
        video=self.video_rect(); return QRectF(video.x()+self.crop.x()*video.width(),video.y()+self.crop.y()*video.height(),self.crop.width()*video.width(),self.crop.height()*video.height())
    def pixel_crop(self):
        x=max(0,min(self.source_width-16,round(self.crop.x()*self.source_width))); y=max(0,min(self.source_height-16,round(self.crop.y()*self.source_height)))
        w=max(16,min(self.source_width-x,round(self.crop.width()*self.source_width))); h=max(16,min(self.source_height-y,round(self.crop.height()*self.source_height)))
        return x,y,w,h
    def reset(self): self.crop=QRectF(0,0,1,1); self.update(); self.changed.emit()
    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing); video=self.video_rect(); crop=self.selection_rect()
        from PySide6.QtGui import QPainterPath
        shade=QPainterPath(); shade.addRect(video); cutout=QPainterPath(); cutout.addRect(crop)
        p.fillPath(shade.subtracted(cutout),QColor(12,20,32,155)); p.setPen(QPen(QColor('#ffffff'),1.5)); p.drawRect(crop)
        p.setPen(QPen(QColor(255,255,255,110),1))
        for i in [1,2]:
            x=crop.x()+crop.width()*i/3; y=crop.y()+crop.height()*i/3
            p.drawLine(int(x),int(crop.top()),int(x),int(crop.bottom())); p.drawLine(int(crop.left()),int(y),int(crop.right()),int(y))
        p.setPen(QPen(QColor('#ff705b'),5,Qt.SolidLine,Qt.RoundCap))
        for x,y,dx,dy in [(crop.left(),crop.top(),1,1),(crop.right(),crop.top(),-1,1),(crop.left(),crop.bottom(),1,-1),(crop.right(),crop.bottom(),-1,-1)]:
            p.drawLine(int(x),int(y),int(x+dx*18),int(y)); p.drawLine(int(x),int(y),int(x),int(y+dy*18))
    def hit(self,point):
        r=self.selection_rect(); x,y=point.x(),point.y()
        return (abs(x-r.left())<14,abs(x-r.right())<14,abs(y-r.top())<14,abs(y-r.bottom())<14)
    def mousePressEvent(self,event):
        if event.button()!=Qt.LeftButton or not self.selection_rect().adjusted(-14,-14,14,14).contains(event.position()): return
        self.drag=(event.position(),QRectF(self.crop),self.hit(event.position())); self.grabMouse()
    def mouseMoveEvent(self,event):
        if not self.drag:
            l,r,t,b=self.hit(event.position()); self.setCursor(Qt.SizeFDiagCursor if (l and t) or (r and b) else Qt.SizeBDiagCursor if (r and t) or (l and b) else Qt.SizeHorCursor if l or r else Qt.SizeVerCursor if t or b else Qt.SizeAllCursor); return
        point,original,edges=self.drag; video=self.video_rect(); dx=(event.position().x()-point.x())/video.width(); dy=(event.position().y()-point.y())/video.height(); l,r,t,b=edges
        left,top,right,bottom=original.left(),original.top(),original.right(),original.bottom(); minw=16/self.source_width; minh=16/self.source_height
        if not any(edges): left=max(0,min(1-original.width(),left+dx)); top=max(0,min(1-original.height(),top+dy)); self.crop.moveTo(left,top)
        else:
            if l: left=max(0,min(right-minw,left+dx))
            if r: right=min(1,max(left+minw,right+dx))
            if t: top=max(0,min(bottom-minh,top+dy))
            if b: bottom=min(1,max(top+minh,bottom+dy))
            self.crop=QRectF(left,top,right-left,bottom-top)
        self.update(); self.changed.emit()
    def mouseReleaseEvent(self,event): self.drag=None; self.releaseMouse()

class ExportDialog(QDialog):
    def __init__(self,source,suggested,default_format,ffmpeg,parent=None):
        super().__init__(parent); self.source=Path(source); self.suggested=Path(suggested); self.ffmpeg=ffmpeg; self.saved_path=''; self.exporting=False; self.closing=False
        self.duration,self.video_width,self.video_height=video_info(ffmpeg,source); self.setWindowTitle('Review & export'); self.resize(820,750); self.setMinimumSize(740,710)
        self.setStyleSheet('QWidget{background:#f4f6f9;color:#454b54;font:14px "Segoe UI";} QLabel#title{font-size:23px;font-weight:600;color:#243449;} QLabel#hint{color:#7a8390;font-size:12px;} QPushButton{background:white;border:1px solid #d6dfe9;border-radius:8px;padding:9px 16px;} QPushButton:hover{background:#e7edf5;} QPushButton:checked{background:#ffe6df;border-color:#ff705b;} QPushButton#export{background:#ff705b;color:white;border:0;font-weight:600;} QPushButton#export:disabled{background:#ffb4a7;} QComboBox,QDoubleSpinBox{background:white;border:1px solid #cbd4df;border-radius:6px;padding:7px;} QComboBox QAbstractItemView{background:white;color:#243449;selection-background-color:#edf2f8;selection-color:#243449;padding:6px;} QProgressBar{background:#e4e9f0;border:0;border-radius:4px;max-height:8px;} QProgressBar::chunk{background:#ff705b;border-radius:4px;}'+TOOLTIP_STYLE)
        layout=QVBoxLayout(self); layout.setContentsMargins(24,20,24,20); layout.setSpacing(12)
        title=QLabel('Review your recording'); title.setObjectName('title'); layout.addWidget(title)
        hint=QLabel('Drag the yellow handles to choose the part you want to keep.'); hint.setObjectName('hint'); layout.addWidget(hint)
        self.video=VideoPreview(); self.video.setMinimumHeight(270); layout.addWidget(self.video,1)
        self.crop=CropOverlay(self.video_width,self.video_height,self.video); self.crop.hide(); self.video.installEventFilter(self)
        self.player=QMediaPlayer(self); self.audio_output=QAudioOutput(self); self.audio_output.setVolume(.7); self.player.setAudioOutput(self.audio_output); self.player.setVideoSink(self.video.videoSink())
        self.player.setSource(QUrl.fromLocalFile(str(self.source.resolve())))
        transport=QHBoxLayout(); self.play=QPushButton('Play'); self.play.setFixedWidth(90); self.play.clicked.connect(self.toggle_play); transport.addWidget(self.play)
        self.clock=QLabel(f'{timestamp(0)} / {timestamp(self.duration)}'); self.clock.setObjectName('hint'); transport.addWidget(self.clock); transport.addStretch()
        self.selection=QLabel(); self.selection.setObjectName('hint'); transport.addWidget(self.selection); layout.addLayout(transport)
        self.timeline=TrimTimeline(self.duration); layout.addWidget(self.timeline)
        crop_row=QHBoxLayout(); self.crop_button=QPushButton('Crop picture'); self.crop_button.setCheckable(True); self.crop_button.toggled.connect(self.crop_toggled); crop_row.addWidget(self.crop_button)
        self.reset_crop=QPushButton('Reset crop'); self.reset_crop.clicked.connect(self.crop.reset); self.reset_crop.hide(); crop_row.addWidget(self.reset_crop)
        self.crop_hint=QLabel(f'{self.video_width} × {self.video_height}'); self.crop_hint.setObjectName('hint'); crop_row.addWidget(self.crop_hint); crop_row.addStretch(); layout.addLayout(crop_row); self.crop.changed.connect(self.update_crop_hint)
        trim=QHBoxLayout(); trim.addWidget(QLabel('Start')); self.start_time=QDoubleSpinBox(); self.start_time.setDecimals(2); self.start_time.setRange(0,max(0,self.duration-.1)); self.start_time.setSuffix(' s'); self.start_time.setAccessibleName('Trim start'); trim.addWidget(self.start_time)
        trim.addSpacing(14); trim.addWidget(QLabel('End')); self.end_time=QDoubleSpinBox(); self.end_time.setDecimals(2); self.end_time.setRange(min(.1,self.duration),self.duration); self.end_time.setValue(self.duration); self.end_time.setSuffix(' s'); self.end_time.setAccessibleName('Trim end'); trim.addWidget(self.end_time); trim.addStretch()
        trim.addWidget(QLabel('Format')); self.format=QComboBox(); self.format.addItems(['MP4','MKV','AVI','WebM']); self.format.setCurrentText(default_format); self.format.setAccessibleName('Export format'); trim.addWidget(self.format); layout.addLayout(trim)
        view=QListView(); palette=view.palette()
        for role,color in [(QPalette.Base,'#ffffff'),(QPalette.Window,'#ffffff'),(QPalette.Text,'#243449'),(QPalette.WindowText,'#243449'),(QPalette.Highlight,'#edf2f8'),(QPalette.HighlightedText,'#243449')]: palette.setColor(role,QColor(color))
        view.setPalette(palette); self.format.setView(view)
        destination=QHBoxLayout(); destination.addWidget(QLabel('Save Location:')); self.location=QPushButton(); self.location.setAccessibleName('Export save location'); self.location.clicked.connect(self.browse); destination.addWidget(self.location,1); layout.addLayout(destination)
        self.progress=QProgressBar(); self.progress.setRange(0,0); self.progress.hide(); layout.addWidget(self.progress)
        self.message=QLabel('Closing this window keeps the full recording as MP4.'); self.message.setObjectName('hint'); self.message.setWordWrap(True); layout.addWidget(self.message)
        buttons=QHBoxLayout(); self.keep=QPushButton('Keep original'); self.keep.clicked.connect(self.keep_original); buttons.addWidget(self.keep); buttons.addStretch(); self.export=QPushButton('Export video'); self.export.setObjectName('export'); self.export.clicked.connect(self.begin_export); buttons.addWidget(self.export); layout.addLayout(buttons)
        self.events=ExportEvents(); self.events.thumbnails.connect(self.set_thumbnails); self.events.finished.connect(self.export_finished); self.thumbnail_cancel=threading.Event()
        self.timeline.range_changed.connect(self.trim_changed); self.timeline.seek_requested.connect(self.seek); self.start_time.valueChanged.connect(self.start_changed); self.end_time.valueChanged.connect(self.end_changed)
        self.player.positionChanged.connect(self.position_changed); self.player.playbackStateChanged.connect(lambda state:self.play.setText('Pause' if state==QMediaPlayer.PlayingState else 'Play')); self.player.errorOccurred.connect(self.preview_error)
        self.format.currentTextChanged.connect(self.update_location); self.update_location(); self.trim_changed(0,self.duration,'start')
        threading.Thread(target=self.make_thumbnails,daemon=True).start()
        QTimer.singleShot(200,self.prime_preview)
    def prime_preview(self):
        if not self.closing and not self.exporting: self.player.play(); QTimer.singleShot(120,self.player.pause)
    def eventFilter(self,watched,event):
        if watched is self.video and event.type()==QEvent.Resize: self.crop.setGeometry(self.video.rect())
        return super().eventFilter(watched,event)
    def crop_toggled(self,enabled):
        self.player.pause(); self.crop.setGeometry(self.video.rect()); self.crop.setVisible(enabled); self.crop.raise_(); self.reset_crop.setVisible(enabled); self.update_crop_hint()
    def update_crop_hint(self):
        _,_,w,h=self.crop.pixel_crop() if self.crop_button.isChecked() else (0,0,self.video_width,self.video_height)
        self.crop_hint.setText(f'{w} × {h}'+('  •  Drag edges to crop' if self.crop_button.isChecked() else ''))
    def preview_error(self,error,text): self.message.setText('Preview could not play: '+text+'. Your recording can still be exported.'); self.play.setEnabled(False)
    def set_thumbnails(self,data): self.timeline.image.loadFromData(data); self.timeline.update()
    def make_thumbnails(self):
        images=[]
        try:
            for i in range(8):
                if self.thumbnail_cancel.is_set(): return
                result=subprocess.run([self.ffmpeg,'-v','error','-ss',str(min(self.duration*.98,self.duration*i/8)),'-i',str(self.source),'-frames:v','1','-vf','scale=128:72:force_original_aspect_ratio=decrease,pad=128:72:(ow-iw)/2:(oh-ih)/2','-f','image2pipe','-vcodec','png','-'],capture_output=True,creationflags=NO_WINDOW,timeout=30)
                if result.returncode: return
                from PySide6.QtGui import QImage
                image=QImage.fromData(result.stdout)
                if image.isNull(): return
                images.append(image)
            from PySide6.QtGui import QImage
            from PySide6.QtCore import QBuffer,QIODevice
            strip=QImage(1024,72,QImage.Format_RGB32); strip.fill(Qt.black); p=QPainter(strip)
            for i,image in enumerate(images): p.drawImage(i*128,0,image)
            p.end(); buffer=QBuffer(); buffer.open(QIODevice.WriteOnly); strip.save(buffer,'PNG'); self.events.thumbnails.emit(bytes(buffer.data()))
        except (OSError,subprocess.TimeoutExpired,RuntimeError): pass
    def toggle_play(self):
        if self.player.playbackState()==QMediaPlayer.PlayingState: self.player.pause()
        else:
            if self.player.position()/1000>=self.timeline.end-.05: self.player.setPosition(int(self.timeline.start*1000))
            self.player.play()
    def seek(self,value): self.player.pause(); self.player.setPosition(int(value*1000))
    def position_changed(self,ms):
        value=ms/1000
        if value>=self.timeline.end and self.player.playbackState()==QMediaPlayer.PlayingState: self.player.pause(); self.player.setPosition(int(self.timeline.end*1000))
        self.timeline.set_position(value); self.clock.setText(f'{timestamp(value)} / {timestamp(self.duration)}')
    def trim_changed(self,start,end,handle):
        self.timeline.set_range(start,end)
        for widget,value in [(self.start_time,start),(self.end_time,end)]: widget.blockSignals(True); widget.setValue(value); widget.blockSignals(False)
        self.selection.setText('Keep '+timestamp(end-start)); self.seek(start if handle=='start' else end)
    def start_changed(self,value): self.trim_changed(min(value,self.timeline.end-min(.1,self.duration)),self.timeline.end,'start')
    def end_changed(self,value): self.trim_changed(self.timeline.start,max(value,self.timeline.start+min(.1,self.duration)),'end')
    def target_path(self): return self.suggested.with_suffix('.'+self.format.currentText().lower())
    def update_location(self):
        path=str(self.target_path()); font=self.location.fontMetrics(); self.location.setText(font.elidedText(path,Qt.ElideMiddle,max(200,self.width()-240))); self.location.setToolTip(tooltip_text(path))
    def browse(self):
        path,_=QFileDialog.getSaveFileName(self,'Export video',str(self.target_path()),'Video (*.'+self.format.currentText().lower()+')')
        if path: self.suggested=Path(path); self.update_location()
    def begin_export(self):
        target=self.target_path()
        if target.exists(): QMessageBox.information(self,'Choose a new filename','That file already exists. Choose a different name in Save Location.'); return
        self.player.pause(); self.exporting=True
        for widget in [self.play,self.timeline,self.start_time,self.end_time,self.format,self.location,self.keep,self.export,self.crop_button,self.reset_crop,self.crop]: widget.setEnabled(False)
        self.progress.show(); self.message.setText('Exporting your selection…'); start,end=self.timeline.start,self.timeline.end; crop=self.crop.pixel_crop() if self.crop_button.isChecked() else None
        def run():
            try: write_export(self.ffmpeg,self.source,target,start,end,crop); self.events.finished.emit(str(target),'')
            except Exception as error: self.events.finished.emit('',str(error))
        threading.Thread(target=run,daemon=True).start()
    def export_finished(self,path,error):
        self.exporting=False; self.progress.hide()
        if error:
            self.message.setText('Export failed. Your original is safe. '+error)
            for widget in [self.play,self.timeline,self.start_time,self.end_time,self.format,self.location,self.keep,self.export,self.crop_button,self.reset_crop,self.crop]: widget.setEnabled(True)
            return
        self.saved_path=path; self.release_player(); self.accept()
    def release_player(self): self.closing=True; self.thumbnail_cancel.set(); self.player.stop(); self.player.setSource(QUrl())
    def keep_original(self):
        if self.exporting: return False
        self.release_player(); target=self.suggested.with_suffix('.mp4'); suffix=0
        while target.exists(): suffix+=1; target=self.suggested.with_name(self.suggested.stem+f'-original-{suffix}').with_suffix('.mp4')
        try:
            target.parent.mkdir(parents=True,exist_ok=True)
            with tempfile.TemporaryDirectory(prefix='.recording-original-',dir=target.parent) as folder:
                partial=Path(folder)/'original.mp4'; shutil.copyfile(self.source,partial); os.rename(partial,target)
            self.saved_path=str(target); self.accept(); return True
        except OSError as error:
            self.message.setText('Could not keep the original: '+str(error)); return False
    def reject(self):
        if not self.exporting: self.keep_original()
    def closeEvent(self,event):
        if self.exporting: event.ignore()
        elif self.saved_path or self.keep_original(): event.accept()
        else: event.ignore()
