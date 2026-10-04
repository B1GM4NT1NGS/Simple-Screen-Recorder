"""Optional developer build. Run: python -m pip install pyinstaller; python build_portable.py"""
import ast,os,pathlib,subprocess,sys,tempfile,shutil
import imageio_ffmpeg,PySide6

root=pathlib.Path(__file__).resolve().parent
qt=pathlib.Path(PySide6.__file__).parent
module=ast.parse((root/'simple_screen_recorder.py').read_text(encoding='utf-8'))
version=next(ast.literal_eval(node.value) for node in module.body if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id=='VERSION' for target in node.targets))
version_tuple=tuple(int(part) for part in version.split('.'))+(0,)
with tempfile.TemporaryDirectory(prefix='simple-screen-recorder-build-') as scratch:
    ffmpeg=pathlib.Path(scratch)/'ffmpeg.exe'
    shutil.copy2(imageio_ffmpeg.get_ffmpeg_exe(),ffmpeg)
    version_file=pathlib.Path(scratch)/'version_info.txt'
    version_file.write_text(f'''VSVersionInfo(
  ffi=FixedFileInfo(filevers={version_tuple!r}, prodvers={version_tuple!r}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('FileDescription', 'Simple Screen Recorder'),
    StringStruct('FileVersion', '{version}'),
    StringStruct('InternalName', 'SimpleScreenRecorder'),
    StringStruct('OriginalFilename', 'Simple-Screen-Recorder-{version}.exe'),
    StringStruct('ProductName', 'Simple Screen Recorder'),
    StringStruct('ProductVersion', '{version}')
  ])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])]
)''',encoding='utf-8')
    command=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed','--name','Simple Screen Recorder','--icon',str(root/'assets'/'recorder.ico'),'--add-data',str(root/'assets')+';assets','--distpath',str(root/'dist'),'--workpath',str(pathlib.Path(scratch)/'build'),'--specpath',scratch,'--exclude-module','imageio_ffmpeg','--add-binary',str(ffmpeg)+';.']
    command+=['--version-file',str(version_file)]
    for name in ['VCRUNTIME140.dll','VCRUNTIME140_1.dll','MSVCP140.dll','MSVCP140_1.dll','MSVCP140_2.dll']:
        command+=['--add-binary',str(qt/name)+';.']
    command+=[str(root/'simple_screen_recorder.py')]
    env=os.environ.copy()
    env['PATH']=os.pathsep.join([str(pathlib.Path(sys.executable).parent),str(pathlib.Path(os.environ['SystemRoot'])/'System32'),os.environ['SystemRoot']])
    subprocess.run(command,cwd=root,env=env,check=True)
