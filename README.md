# Archiver

Archiver helps save storage space by transcoding video footage at lower quality or with more efficient codecs. It provides a local browser interface powered by FFMPEG, so you can review a folder of footage, choose what to keep, and batch-encode smaller archive copies.

## Features

- Scan folders and review file sizes, codecs, resolution, and frame rate.
- Browse resizable thumbnails with hover previews or use a detailed file list.
- Choose software or hardware encoders, including NVIDIA NVENC, Intel Quick Sync, and AMD AMF when available.
- Adjust video quality, bitrate, resolution, frame rate, and audio settings.
- Keep originals, replace them, or save transcoded files to another directory.
- Add filename suffixes or batch names and monitor jobs in a separate queue.
- Use light or dark mode.

## Getting started

1. Install [Python 3.10 or newer](https://www.python.org/downloads/) and download [FFmpeg and FFprobe](https://ffmpeg.org/download.html) for your platform. They are not bundled with Archiver.
2. Download and extract the app from [Releases](https://github.com/technicallyalex/Archiver/releases).
3. On Windows, double-click **Launch Archiver.bat**, or run `python app.py` from the project folder.
4. Open **FFmpeg settings** if the tools are not detected automatically.
5. Scan a folder, select videos, choose output settings, and add them to the queue. Click **Start queue** to begin.

Reducing quality, resolution, or frame rate can save space at the cost of detail or motion smoothness. Results depend on the source and encoder settings. Current output is 8-bit and does not include HDR tone mapping, so review a sample before replacing important footage.

See the [usage guide](docs/USAGE.md) for naming options, original-file handling, encoding controls, and limitations. See the [changelog](CHANGELOG.md) for release history.

## Development

No third-party Python packages are required. Run `python -m unittest discover -s tests -v` to test and `python build_release.py` to package the app. Integration tests require FFmpeg and FFprobe; the Recycle Bin test is Windows-only. The release version is read from `VERSION`.
