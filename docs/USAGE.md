# Usage guide

## Start

Open a current Windows build folder and double-click **Archiver.exe**. Keep `_internal` beside it. Python is bundled; no script launcher or Python installation is needed. The interface opens in your browser and the tray icon controls the local application.

FFmpeg and FFprobe are supplied separately. Installations on PATH are detected; otherwise open Video tools and choose Install missing tools to download, verify and save their paths automatically on Windows. You can also enter existing executable paths manually. Setup runs in the background if you close the panel. Hardware encoders still need compatible hardware and drivers.

## Workflow

1. In Media Pool, select a source folder. Parallel import defaults to Auto, adapting up to 16 metadata reads; fixed limits are also available. Include subfolders exposes recommended exclusions for proxy and Archiver test folders, and custom folder names.
2. Select footage, then choose the quality mode, output codec, and software/hardware method. H.264, HEVC, AV1 and ProRes are the supported outputs. ProRes is a large intraframe format, not mathematically lossless.
3. Automated (Test) uses ab-av1 CRF search against an adjustable XPSNR target, default 38 dB. The right-hand Test controls panel in Test Queue automatically chooses the longest supported selected file, or you can choose another from the thumbnail grid. A single-file result may not represent very different footage.
4. Test one file to review its results and apply the measured settings to Manual controls, or choose Test each selected file to queue successful files with their own bound recommendations. The default test storage is the imported Media Pool root; an optional override applies to both scopes.
5. Review save behavior, format/audio, and output naming. Keep originals and Save to another folder retain sources. Replace Originals follows the chosen recycle/delete handling and applicable quality verification. Confirm permanent deletion when selected.
6. Use Encoding Queue to start, pause, cancel or inspect progress. Per-file test handoffs respect existing queue controls and the captured auto-start preference.
7. Reopen the browser through the tray icon; choose Quit to stop Archiver. Closing the browser tab alone does not quit it.

Logs are in `%LOCALAPPDATA%\Archiver\logs\archiver.log`. Quit the running version before switching to a retained rollback build. Builds are folders by default; keep all support files together.

## Development

Run `python app.py --tray` on Windows, or `python app.py` for a console-managed source session. `--port` changes the local port and `--no-browser` suppresses automatic browser opening. The packaged executable accepts these flags too. It listens only on 127.0.0.1. See the project README for dependency/build commands; old script launchers are preserved under `scripts/legacy` and are not shipped.

## Verification, recovery and reports

In Encoding Queue, use the right-hand **Queue controls** panel. New jobs inherit the selected options: technical output checks, a full decode scan, HTML/JSON reports and queue recovery default on. Manual encodes do not run sampled XPSNR checks. Encodes made through Automated (Test) retain their final quality check. Each measured verification clip must meet the target; an average cannot hide a failed clip.

Checks run before publication or replacement. A failed check retains the original and does not publish the staging file. Open **Verification details** for the job. Completed entries provide **View report**, **Open full report** and **Export JSON**. Sidecar filenames end in `.archiver-report.html` / `.archiver-report.json`. Source identity uses path, size and modification time, not a full-content checksum.

After a restart, **Restore paused** restores saved encoding and test queues. Interrupted files restart from the beginning; completion receipts prevent repeating completed outputs. Old interrupted test folders remain available and restarted tests use a new folder. Journals are stored in `%LOCALAPPDATA%\Archiver\workflows`, separately for each build so rollback versions do not overwrite one another's queue. Quit other versions before using a rollback build. A corrupt journal is preserved when its recovery prompt is dismissed.

**Storage details** combines output folders on the same detected volume. Encode staging files use the output folder. Unknown CRF/CQ sizes use a source-size planning budget; this is not a size prediction. Queues pause when a location becomes unavailable or has less than 64 MiB free. Reconnect/free space, recheck, then resume; an interrupted encode restarts. Reports, source backups and test-folder files still occupy disk space after jobs finish.

## Comparing test clips

For a newly completed quality test, select **Compare previews**. Choose a search or independent-validation clip, split/side-by-side/amplified difference, and synchronized playback or single-frame stepping. Browser proxies are cached under the existing test folder's `comparison` directory. They use high-bitrate 8-bit H.264, up to 1080p by default; native-resolution proxies take longer. Color and fine detail can differ from the exact files, especially for HDR. Quality scores are measured on the original validation pair. Preparation waits for active media work so it does not compete with a running queue. Earlier tests without retained exact clip references need to be rerun for this feature.

## Audio, metadata and portable presets

In Output settings, open **Audio tracks & metadata**. Track choices use their order and apply across selected files; missing selected tracks or incompatible copied formats stop queueing. Subtitles remain excluded until selected explicitly. Use MKV for styled subtitle copies, or explicitly convert text subtitles for MP4 (styling may be lost). Reported color information is preserved where supported; HDR-to-SDR conversion is not automatic. File modification dates, metadata and chapters can be preserved independently.

The existing header **Presets** panel now offers **Import** and **Export**. Portable files contain output settings only: source/output folders and executable paths are excluded. Imported presets use Keep originals and require a compatible encoder. Measured CQ/CRF bindings require a new test. Local startup-default selection remains available.

## Watch folders

Use **Watch folders** beside Media Pool import controls. Save an output preset first, then choose a source and a separate output folder outside it. Existing files are baselined when the rule is created; new recordings must stop changing for at least 30 seconds and pass inspection. The rule uses the current saved preset, retains originals, preserves relative source subfolders and excludes proxy/test folders. Automated (Test) tests each new file before handing its measured settings to Encoding Queue. Automatically starting queued work is opt-in and respects a paused queue. Individual failures remain visible with **Retry failed files**. Rules and seen-file stamps are saved across restarts.
