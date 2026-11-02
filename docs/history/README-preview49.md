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
- Auto tests create measured quality presets; source-based presets offer immediate bitrate/codec suggestions; Custom retains manual encoding controls.

## Local 0.3 preview

Open the built `dist/Archiver-0.3-preview.26` folder and launch **Launch Archiver.vbs**. Builds now create a folder by default; use `python build_release.py --zip` only when an archive is wanted. This preview uses port 8898. Existing Python and FFmpeg requirements are unchanged. Previous versions remain available for rollback. Avoid processing the same source files in both versions simultaneously.

Auto now offers **ab-av1**: choose AV1, HEVC, or H.264 and one quality target, run a short-sample search, then apply the generated preset. The test queue shows verbose console output and a sequential source filmstrip with positioned sample cards and cached source-timed active-sample video. The bundled Windows tool requires no separate installation. See [ab-av1 usage and limitations](docs/AB_AV1.md). VP9 output has been removed. Auto searches the selected codec rather than a separate custom codec grid.

Choose H.264, H.265/HEVC, AV1, or ProRes. These are the only output codecs. Delivery codecs offer Auto XPSNR 38 dB testing, quick estimates, or manual controls. Choose the codec, then software/hardware, then quality. ProRes uses a dedicated editing path. File format/audio and naming options are collapsed until needed. See [the output flow](docs/CODEC_CHOICES.md).

Choose an **Encoding setup**:


- **Auto — Test-generated presets:** choose software or supported hardware, run one XPSNR 38 dB test, then apply the generated configuration. Auto cannot queue encodes until a matching test completes. Presets remain available for the session after clearing finished test entries. Other source files are validated individually when encoded.
- **Source-based presets — No test:** choose an output codec and an estimated quality tier. Target bitrate accounts for both input and output codec efficiency before applying the tier's budget. For a 40 Mbps H.264 source, AV1 estimates are 20/15/10 Mbps at 100/75/50%; keeping H.264 gives 40/30/20 Mbps. **Optimized** chooses the most efficient available codec. These are documentation-guided application estimates, not measured quality matches. See [codec estimate assumptions and sources](docs/CODEC_ESTIMATES.md).
- **Custom controls:** choose the codec, encoder, bitrate/CRF/CQP, resolution, frame rate, and audio settings yourself.

Tests inherit the media-library method and container settings and store all test data in their own folder beside the selected source video. Short samples and measured trial results are shared across generated presets to avoid duplicate work. The queue shows progress through the preset set, codecs, quality values, and samples. Only passing presets are offered; failed targets are reported. Reports and comparison clips remain on disk, while generated preset availability is session-only and invalidates when its reference source or tools change.

Measured and source-based presets currently support 8-bit SDR `yuv420p` sources with even dimensions, preserving resolution and frame rate. Auto needs FFmpeg with the `xpsnr` filter; metadata presets do not. Audio defaults to copying, subject to container compatibility. Keep unsupported/HDR sources unchanged or carefully review Custom settings. Auto targets XPSNR 38 dB; this is not a guarantee of visually lossless output. See [automatic quality details](docs/AUTOMATIC_QUALITY.md).

## Screenshots

Media library with thumbnail previews, file metadata, and encoding controls. Screenshots use generated sample videos.

![Media library in dark mode](docs/screenshots/media-library.png)

<details>
<summary>More views: light theme, file list, queue, and FFmpeg output</summary>

**Detailed file list and light theme**

![Detailed file list in light mode](docs/screenshots/list-view-light.png)

**Encoding queue**

![Completed encoding jobs with progress bars and speed](docs/screenshots/encoding-queue.png)

**Verbose FFmpeg output**

![Encoding queue showing detailed FFmpeg output](docs/screenshots/ffmpeg-output.png)

</details>

## Getting started

1. Install [Python 3.10 or newer](https://www.python.org/downloads/) and download [FFmpeg and FFprobe](https://ffmpeg.org/download.html) for your platform. They are not bundled with Archiver.
2. Download and extract the app from [Releases](https://github.com/technicallyalex/Archiver/releases).
3. On Windows, double-click **Launch Archiver.vbs** to run without a command window. If Windows Script Host is unavailable, open **Launch Archiver.pyw** with Python. For a diagnostic console session, run `python app.py` from the project folder.
4. Open **FFmpeg settings** if the tools are not detected automatically.
5. Scan a folder, select videos, choose output settings, and add them to the queue. Click **Start queue** to begin.

Reducing quality, resolution, or frame rate can save space at the cost of detail or motion smoothness. Results depend on the source and encoder settings. Current output is 8-bit and does not include HDR tone mapping, so review a sample before replacing important footage.

See the [usage guide](docs/USAGE.md) for naming options, original-file handling, encoding controls, and limitations. See the [changelog](CHANGELOG.md) for release history.

## Windows tray icon

The desktop launcher starts Archiver in the notification area near the clock and opens its local browser interface. Click the Archiver icon to reopen the app. Right-click for encoding-queue and quality-test pause/resume controls or **Quit Archiver**. Hover for the application's work status; no system performance monitoring is added. Windows may initially put the icon in its hidden-icons menu.

Closing the browser leaves Archiver and its queues running. Quit from the tray to stop the service. If work is active, Archiver asks before cancelling it and lets temporary-file cleanup finish. Launching the same version/port again opens the existing instance. Startup errors appear in a dialog and are logged to `archiver-desktop.log` in the application folder. `Launch Archiver.bat` forwards to the new launcher; use the VBS or PYW file directly to avoid even a brief command-window flash.

## Development

Local Windows builds bundle pywinpty for hidden native CLI progress capture. For a different Python runtime, install a matching wheel with `python -m pip install --target .dependencies -r requirements.txt`; pipe-output fallback remains available. Run `python -m unittest discover -s tests -v` to test and `python build_release.py` to package the app. Integration tests require FFmpeg and FFprobe; the Recycle Bin test is Windows-only. The release version is read from `VERSION`.

Auto uses ab-av1 crf-search with retained intermediate measurements and per-sample vmafmotion statistics. See [motion analysis and search behavior](docs/MOTION_ANALYSIS.md).

Preview.22 preserves source timestamp precision during Auto tests and final Auto encoding. Earlier measured presets require a new test. The default at that version was VMAF; see [the aligned XPSNR/VMAF experiment](docs/XPSNR_COMPARISON.md).

Preview.23 Auto uses ab-av1’s built-in `crf-search --min-xpsnr 38`. FFmpeg performs encoding and XPSNR measurement; ab-av1 performs the adaptive search. CPU, NVIDIA, and Intel are supported for Auto. AMD can use Quick estimate or Manual. Final output is validated using XPSNR too. Previous VMAF-based recommendations require a new test. See [the current Auto workflow](docs/AUTO_XPSNR.md).

Preview.24 removes minimum savings requirements from analysis and final encoding. Quality-passing outputs may be smaller, the same size, or larger. Estimated size changes remain visible. Quality, duration, source-change, and original-file handling checks remain.

Preview.25 adds an adjustable XPSNR slider and numeric target (30–50 dB), defaulting to 38. Expand Target guidance & sources for practical starting bands and the research limitations. Each test, cached recommendation, and final verification is bound to its chosen target. See [target guidance](docs/XPSNR_TARGET_GUIDE.md).

Preview.26 separates loop generation from still thumbnails and permits two thumbnail jobs plus one loop preview at once. Motion-aware sample selection is not implemented; scores remain informational. See [preview generation and motion status](docs/PREVIEW_GENERATION.md).
