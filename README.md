# Archiver

Archiver is a simple browser-based tool that uses FFmpeg to select and transcode video files to reduce file size. Choose automated quality tests, bitrate estimates or manual controls, and manage originals and outputs with batch workflows. This Windows release supports H.264, H.265, AV1 and ProRes.

## 0.3 release candidate

[Download the release candidate](https://github.com/technicallyalex/Archiver/releases/tag/v0.3.0-rc.8). Extract the download, then open Archiver.exe in the application folder. This is a prerelease for testing, not a stable release.

Use **Feedback** in the app header to open a GitHub issue with the version and browser prefilled. You review and submit it yourself. See the [QA report](docs/QA_0_3_RC1.md) for tested workflows and known limits.

## Running a build

Open the versioned folder under `dist` and double-click **Archiver.exe**. Keep `_internal` beside it. Python is bundled; you do not need to install it. FFmpeg and FFprobe remain external tools, detected from PATH or selected through the app. Archiver opens your browser and provides a tray icon for reopening, queue controls and quitting.

Builds are folders by default, with no installer or ZIP required. Previous folders remain available for rollback. Quit a running version before switching versions. Logs are in `%LOCALAPPDATA%\Archiver\logs`.

## Development

- `app.py` and the supporting Python modules: processing service and queues.
- `web/`: shared browser interface.
- `tests/`: automated checks.
- `docs/`: feature documentation; older notes are historical.
- `packaging/`: executable entry point and build dependencies.
- `scripts/legacy/`: preserved old Python/script launchers, no longer shipped.
- `build/`: ignored executable build intermediates.
- `dist/`: ignored versioned user-facing builds.
- `.test-temp/` and `comparisons/`: retained local validation artifacts, not shipped.

Run from source with `python app.py --tray` on Windows. Install runtime requirements with `python -m pip install --target .dependencies -r requirements.txt`. Build on Windows with `python -m pip install -r packaging/requirements-build.txt`, then `python build_release.py`. ZIP packaging is available only with `--zip`.

The builder checks bundled web assets, ab-av1, the native terminal and Tk folder-picker runtime before creating the distribution. Native folder picking uses a separate executable helper process. Source code, tests, development scripts and scratch files are excluded from user builds.

See [per-file testing](docs/PER_FILE_TESTING.md), [import exclusions](docs/IMPORT_FILTERS.md), and [XPSNR testing](docs/AUTO_XPSNR.md). Earlier README content is preserved in `docs/history/README-preview49.md`.
