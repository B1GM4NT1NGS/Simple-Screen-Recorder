# Third-party notices

Simple Screen Recorder uses:

- [PySide6 / Qt for Python](https://doc.qt.io/qtforpython-6/) — LGPLv3/GPLv3 or commercial licensing.
- [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg) — BSD-2-Clause wrapper; supplies an FFmpeg executable.
- [FFmpeg](https://ffmpeg.org/) — this binary includes GPL components including libx264. FFmpeg is invoked as a separate process. Build configuration and license details can be inspected with `ffmpeg -L` and `ffmpeg -buildconf`. Source and release archives are available at [FFmpeg downloads](https://ffmpeg.org/download.html); Windows build sources and build recipes at [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg) and [Gyan.dev](https://www.gyan.dev/ffmpeg/builds/).
- [PyAudioWPatch](https://github.com/s0d3s/PyAudioWPatch) — MIT; based on PyAudio and PortAudio with their respective notices.
- PyInstaller — GPL with a bootloader exception.

These dependencies retain their own licenses. The MIT license in this repository covers application code, not third-party libraries. The source release does not contain compiled third-party binaries. The optional local portable build bundles the installed Qt libraries and FFmpeg executable; consult their licenses before redistributing a compiled build.
