# ab-av1 integration — 0.3-preview.23

In Media library, choose AV1, HEVC, or H.264, choose CPU/NVIDIA/Intel encoding, then choose **Auto · XPSNR 38 dB**. Run the quality test, then apply its generated configuration. ab-av1 is selected automatically. Auto uses one selected-codec adaptive search, not an additional custom comparison grid. VP9 is no longer an output option anywhere; VP9 sources remain readable.

The bundled upstream Windows executable is ab-av1 0.11.7, MIT licensed. Software encoding supports SVT-AV1, x265, and x264. NVIDIA/Intel use the corresponding FFmpeg encoders and require compatible hardware/drivers. AMD can use Quick estimate or Manual; Auto supports CPU, NVIDIA, and Intel and has no silent VMAF fallback. WebM output requires AV1.

Each test searches only the selected codec and quality target. Auto uses ab-av1’s built-in `crf-search --min-xpsnr 38` at native resolution and source timing, with the encoder time base preserved. FFmpeg provides the XPSNR measurement; no trained VMAF model is selected. These are provisional engineering targets, not universal perceptual or lossless guarantees. ab-av1 does not report our previous frame-percentile/one-second floors, so its results explicitly show those as unmeasured. The final output is checked against the mean target on distributed regions before publication. Old-engine presets are not reused as ab-av1 recommendations.

The adapter sets three ten-second sample windows, integer quality search steps, and a high --max-encoded-percent 10000 analysis ceiling. Larger target-quality results are retained, and output size is informational. Sources where this covers at least 85% of the duration use ab-av1's full-pass behavior. There is no wall-clock cutoff. A failed search reports its error and leaves the source unchanged. No minimum savings rule is applied to the final output.

The test display places sample cards above their positions on an 18-frame chronological source filmstrip. The active card uses a cached silent H.264 MP4 preview, up to ten seconds long and 320 pixels wide, preserving source frame timing including fractional and variable frame rates. Only an active visible sample plays, with no FPS label; inactive/completed samples are still thumbnails. There is no blue seekbar or separate scrub-preview image. Requested sample positions remain approximate because extraction may move to keyframes.

Loop previews have a separate single-worker lane; still thumbnails can use two workers concurrently. Preview jobs retain single-thread decode/filter/encode settings. Each source-side test folder caches its sample videos for reuse across search attempts. Short sources use their available length. Missing H.264 support or failed/cancelled preview generation falls back to still images. Previews are source context, not quality assessments or output comparisons. Proxy preparation uses a low-priority process and does not block the quality worker. Video requests support byte ranges; looping reuses the cached clip. Videos pause on hidden tabs/panes or off-screen cards, and retain their media element during refreshes to avoid playback resets.

A simple estimated progress bar and always-open terminal output sit below the filmstrip. Windows builds bundle pywinpty to capture a hidden pseudoconsole, preserving ab-av1's live CLI display without a visible CMD window. A small VT screen reader handles cursor redraws and wrapped JSON results. The latest 100 log messages and current CLI progress line appear in the UI; full output is saved as ab-av1.log. CLI ETA applies to the current quality search, not the entire suite or full encode. The bar follows the current estimated search progress; Auto runs one XPSNR 38 dB target. An unknown estimate stays unknown; final-encode time is identified separately.

The bundled native wheel matches the current build machine's Python runtime. On another Python version/architecture, install a compatible pywinpty package under .dependencies using requirements.txt. If unavailable, ordinary piped output still works, with a clear log message and no native CLI ETA. Native cancellation terminates the capture process tree, including active FFmpeg children.


Temporary ab-av1 sample files and configured tool aliases also use that folder. Upstream's global disk cache is disabled because it cannot be redirected by its CLI, and its metadata-based sample identity can collide across similarly named sources. Archiver retains its fingerprinted session recommendation cache. There are no additional lossless reference copies or automatic comparison-video encodes in this workflow.

Full encoding stays in Archiver's queue with its existing cancellation and source protection. The adapter matches tested quality controls, encoder preset, 8-bit pixel format, ten-second keyframe interval, and encoder-specific scene-change/lookahead settings. Cancellation terminates ab-av1's subprocess tree on Windows, including child FFmpeg processes. Hardware execution still needs testing on the user's device; software paths were exercised locally.

## Bundled executable provenance

- [Official release 0.11.7](https://github.com/alexheretic/ab-av1/releases/tag/v0.11.7)
- Download: `https://github.com/alexheretic/ab-av1/releases/download/v0.11.7/ab-av1.exe`
- SHA256: `a3a9534d2adecabc4861acf632d0f64741f56e2050d52032a5307bebb4fbdcc9`
- License: `tools/ab-av1/LICENSE`
- [Structured output contract](https://github.com/alexheretic/ab-av1/blob/v0.11.7/stdout-format-json.md)
- [Sampling implementation](https://github.com/alexheretic/ab-av1/blob/v0.11.7/src/command/sample_encode.rs)

Rollback: extract this preview separately. It uses port 8882. Previous ZIP builds remain intact. Nothing is published automatically.

## Archival option

Preview.11 adds a separate [archival/mezzanine mode](ARCHIVAL.md): lossy ProRes intermediates, lossless FFV1 video, and exact source copies. These remain outside quality-search workflows and file-size saving requirements.

Preview.19 preparation benchmark: a synthetic 640×360/24 FPS ten-second segment took a median 0.313 seconds over three runs for both the prior 3-FPS WebP and the H.264 proxy. Files were 112,846 and 462,236 bytes respectively. This measures preparation only; it is not a guarantee of unchanged test time on other footage or hardware. Fractional 59.94 FPS and VFR timing were verified separately.

See [CRF attempt retention and per-sample motion analysis](MOTION_ANALYSIS.md) for preview.20 behavior.

See [the current XPSNR workflow](AUTO_XPSNR.md) for target, verification, cache, and capability details.

## Header installation entry (version 119)

The header shows ab-av1's detected version and readiness beside the combined FFmpeg status/settings button. Its installation dialog exposes the version, bundled-versus-PATH origin, executable path and a Check installation action. ab-av1 remains included with Archiver and normally requires no separate setup. The configured FFmpeg still needs the XPSNR filter for automated quality tests; binary availability alone does not imply FFmpeg feature or hardware support.

Version checks use a five-second subprocess timeout and are cached by path, size and modification time. No executable is launched on unchanged status polls. Check installation invalidates that cache and revalidates the detected binary. Missing, invalid and unlaunchable binaries report unavailable status and explanatory details. The entry does not change the chosen executable or encoder settings.

## Unified Video tools readiness (version 120)

FFmpeg and ab-av1 share one Video tools header button and one readiness indicator. The combined setup dialog remains accessible when dependencies are missing. Core media actions are blocked until FFmpeg and FFprobe have been verified, at least one supported output encoder and FFV1 are available, FFmpeg provides XPSNR and vmafmotion, and ab-av1 reports its version plus XPSNR CRF-search and JSON-output options. Optional hardware encoder availability remains a per-configuration check.

The six work-start APIs (import, test-source scan, test admission, test resume, encode admission and encode resume) enforce readiness. The encode scheduler holds new jobs while dependencies are unavailable; a quality test checks readiness before starting. Existing work can finish safely rather than being forcibly interrupted. Media entry buttons reflect the same state. Presets, history, cancellation and setup stay accessible.

FFmpeg executable verification and capability discovery commit state together. Active media work prevents changing tools. Waiting jobs can remain in the queue while tools are configured; configuration pauses waiting encodes/tests for deliberate resumption. ab-av1 feature checks are cached by binary identity alongside its version and can be rechecked from the combined panel. Readiness does not install or download executables automatically.
