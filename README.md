# Archiver 0.1

A local video library and FFmpeg queue with a browser interface. No Python packages, cloud services, or bundled media binaries are required.

## Start

1. Install Python 3.10 or newer.
2. Obtain your own FFmpeg and FFprobe binaries from a source you trust. Put them on PATH or enter their full executable paths in **FFmpeg settings**. Both programs are required. Archiver does not redistribute them.
3. On Windows, double-click **Launch Archiver.bat**. On any supported platform, run `python app.py` from this folder.
4. Open the address printed in the terminal if the browser does not open automatically. Keep the terminal open; press Ctrl+C to stop the app.

Use `python app.py --port 8766` to choose another port, or `--no-browser` to skip opening the browser. The server listens only on 127.0.0.1. The UI and assets run locally without external libraries or font requests.

## Workflow

Click **Browse…** to choose a directory, or paste its path, optionally include subdirectories, and scan. FFprobe reads video and audio metadata. Select thumbnails or switch to the detailed list. Search, sort, resize thumbnails, or move the pointer over a thumbnail to scrub through extracted frames. Scrubbing uses still frames at approximately one-second intervals, including for formats the browser cannot play. Thumbnails are generated on demand and cached temporarily.

Choose a video codec and an encoder supported by your FFmpeg build. NVIDIA NVENC, Intel Quick Sync, and AMD AMF appear when included in that build. Their availability in this list does not guarantee compatible hardware or drivers; failed jobs show FFmpeg's error in the verbose view. Software encoding is available when the corresponding encoder is included in FFmpeg.

Resolution choices fit inside a 16:9 bounding box, preserve aspect ratio, and never upscale. Keep original rounds odd dimensions down to even pixels for encoder compatibility. Automatic uses each source video stream’s reported bitrate (not overall container bitrate). Output is 8-bit YUV 4:2:0; this version does not provide HDR tone mapping. For HDR or color-critical sources, review a test encode before replacing originals.

The first video stream and all audio streams are included. Subtitles, attachments, chapters, and additional video streams are not explicitly preserved. Audio codecs include AAC, MP3, Opus, and lossless FLAC, plus copy and remove options. AAC/MP3/Opus offer 64, 96, 128, 160, 192 (default), 256, and 320 kbps per audio stream. MP3 mixes multichannel audio to stereo. MP4 offers AAC/MP3/copy/remove; WebM offers Opus/remove with AV1/VP9 video; MKV offers all audio options. Copied audio must be compatible with the selected container. MP3 and Opus require libmp3lame and libopus in the user’s FFmpeg build. Container/codec combinations unsupported by your FFmpeg build fail with the terminal output available for diagnosis.

File actions:

- **Preserve Originals:** write a new file next to the source. Defaults to a custom `archiver` suffix, such as `Video_archiver.mp4`.
- **Replace originals:** encode to a temporary file, validate it with FFprobe, then replace the source. Requires matching source/output extensions. By default the original is sent to the Windows Recycle Bin. Select **Permanently Delete** in the original-file toggle to remove it permanently instead.
- **Transcode to New Directory:** write the chosen output filename in an existing destination folder.

Replacement keeps the original in a temporary backup folder until publishing succeeds. A publishing failure restores it; a recycling/deletion failure retains that backup and reports its path. Recycled files retain their original filename but Windows records the temporary backup folder as their restore location; restore and move them back manually if needed. Recycling requires Windows and a drive supporting the Recycle Bin. FFprobe validation checks readable video metadata and positive duration, not full decoding or visual quality.

Existing outputs are never intentionally overwritten outside Replace mode. Duplicate output names are rejected. Jobs wait until you click **Start queue**. Enable **Automatically start queued files** to start processing when adding files. Once started, the queue processes jobs one at a time until empty, including files added while it is running. The checkbox starts unchecked on page load. Cancel stops the active process and removes its temporary output. Progress can be displayed as a bar, compact speed/FPS/ETA text, or a rolling terminal log (last 1,500 lines). ETA is approximate and excludes final container flushing. Directory scans show unreadable-file errors without stopping other files.

## Distribution and limitations

Distribute this folder as a ZIP. Users install Python and supply FFmpeg/FFprobe independently. No FFmpeg binaries are included. Optional executable packaging can be added later with PyInstaller, but it is not required to run this version.

Library, tool configuration, and queue state live in memory and reset when the server stops. Theme preference is stored in the browser. Closing the browser does not stop encoding. The app does not automatically resume jobs after a restart. Keep source files unchanged while jobs run. The Browse button uses a native folder picker through Python’s tkinter module. If tkinter is unavailable, install your Python distribution’s Tk support or paste paths from your file manager.

## Verification

Run `python -m unittest discover -s tests -v`. Integration tests use FFmpeg/FFprobe on PATH and skip if unavailable. They generate tiny synthetic videos and exercise metadata, real transcoding, safe file handling, and HTTP authentication.


## Output filenames

Keep the original filename (with the selected output container extension), append a custom suffix, append resolution/frame-rate/quality-setting tags, or use a batch base name with a sequence such as `Vacation_001.mp4`. Suffixes appear before the extension. The preview shows up to three selected files; without a selection it uses a 1080p/30 fps example. Sequence numbers follow selection order and restart for each added batch. Resolution tags use fitted output dimensions (no upscaling); quality tags describe the chosen setting rather than measured visual quality. Replace-original mode keeps the original filename. Existing or duplicate output paths are rejected rather than overwritten.

The File action dropdown offers Preserve Originals, Replace Originals, and Transcode to New Directory. Preserve Originals defaults to Original Name + Custom Suffix with `archiver`, producing names such as `Video_archiver.mp4` alongside the source. Selecting this action again restores those defaults; other naming options remain available. Transcode to New Directory defaults to the original filename. Replace Originals retains the source filename.

## Manual video quality

Video quality / bitrate offers CRF for software encoders, CQP for hardware encoders, and custom target bitrate in Mbps (0.1–1000). Quality values are integers: 0–51 for H.264/HEVC and hardware, 0–63 for software AV1/VP9. Lower values generally retain more detail and increase size. Values are not equivalent across encoder families. Recommend from selected files uses a heuristic based on source codec and video-stream bits per pixel per frame; missing stream bitrate falls back to codec defaults. It applies the most conservative recommendation across the selection. It does not recover original encoder settings or perform a quality comparison. Rescan files to populate the new stream metadata. HDR/high-bit-depth sources show a warning because output remains 8-bit. The estimator does not model content complexity or resolution/frame-rate conversion losses.

## Automatic source settings

Automatic uses per-file FFprobe video-stream bitrate, including BPS stream tags when available. Reported bitrate is typically an average, not proof of the original configured target. Explicit rate-control tags can identify CBR/VBR or CRF/QP values. Compatible same-codec, whole-number CRF/CQP values are reused; otherwise bitrate is used. Unknown rate modes fall back to target-bitrate encoding, never inferred CBR. Missing usable bitrate/quality metadata prevents queuing Automatic and requests a manual setting. CFR is a frame-rate mode, not rate control. Encoder settings and quality scales are not universally portable, and matching source bitrate does not guarantee matching quality.

## Build a release

Run `python build_release.py` to create `dist/Archiver-0.1.zip` and its SHA-256 checksum. Only the listed source, web assets, tests, and documentation are packaged. Media, caches, credentials, and FFmpeg/FFprobe binaries are excluded.
