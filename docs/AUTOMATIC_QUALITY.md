# Automatic quality — 0.3-preview.11

Current Auto uses [XPSNR 38 dB](AUTO_XPSNR.md). VMAF-specific policy details below describe the legacy analyzer. No minimum savings gate applies to either path.

Auto now defaults to the bundled ab-av1 engine for one selected codec and quality target. See [ab-av1 behavior and progress](AB_AV1.md). The multi-codec comparison behavior below applies to the Archiver engine. VP9 output has been removed. [Archival / editing mode](ARCHIVAL.md) is separate and does not use quality testing.

## Encoding setups

**Auto** requires a completed matching Auto test. One test generates up to three measured presets: No perceived quality loss, High quality / Web publishing, and Smaller files. These are available only after their targets pass validation. The application shares lossless references and matching trial measurements across all three searches. Their coverage remains capped at approximately ten scored seconds during search and thirty scored seconds for each finalist. Generating a set can take longer than measuring one target, but does not repeat identical sample encodes.

Select a generated preset to enable Auto queuing. A report must match the current encoding method, GPU backend, container, source fingerprint, model, sampling policy, and tools. Changing the reference source invalidates it. The tested source reuses matching results; other files use the tested settings as starting points and receive per-file validation. Final output checks remain mandatory. Clearing finished test cards retains up to thirty generated reports for the session. Reports and preview clips remain saved beside the source, but are not automatically reloaded into a new session.

**Source-based presets** use video-stream bitrate and a versioned codec-efficiency estimate without VMAF. Choose the output codec, then a 100/75/50% estimated quality tier. The formula is `source bitrate × output codec cost / input codec cost × tier budget`. Initial relative costs are H.264 1.00, HEVC/VP9 0.65, and AV1 0.50; these are conservative engineering priors guided by primary documentation, not codec-standard guarantees. For 40 Mbps H.264 → AV1, 100% estimates 20 Mbps and the lower tiers estimate 15/10 Mbps. Same-codec 100% keeps the source video bitrate. Converting back to a less efficient codec increases the estimated bitrate.

Optimized chooses the most efficient available codec for the selected hardware/software method and container. It will not choose a codec less efficient than the source. Unknown codec pairs, missing source video bitrate, or an unavailable explicit output encoder produce an explanation rather than silent fallback. Output previews and queued jobs use the same server estimator; jobs record its version and factors. The percentages are estimated quality tiers implemented as bitrate budgets, not literal fractions of perceptual quality. Hardware implementations, speed presets, grain, motion, and existing source compression can change actual quality substantially. See [codec estimates, evidence, and limitations](CODEC_ESTIMATES.md).

**Custom controls** retain manual codec, encoder, bitrate/quality, resolution, frame rate, and audio settings. The earlier 1:1 copy label is not used for bitrate-matching presets; matching bitrate is a lossy transcode, not an exact copy.

The encoding setup determines how presets are obtained. Software mode compares available CPU H.264 (x264), HEVC (x265), and AV1 (SVT-AV1, or AOM when unavailable). Hardware mode compares H.264, HEVC, and AV1 only on the selected NVIDIA NVENC, Intel Quick Sync, or AMD AMF backend. It never silently switches to software. WebM limits candidates to AV1 because of its container requirements. Unusable hardware is reported with the results.

Automatic mode manages presets internally using a consistent balanced preset for each encoder: x264/x265 medium, SVT-AV1 8, AOM cpu-used 4, NVIDIA p5, Intel medium, or AMD balanced. The same preset is used in trials and final encoding. Among candidates that pass the quality policy, it selects the smallest measured video. Quality-setting search compensates for differences between encoders; presets are not user-facing quality targets.

A preset controls encoding effort, affecting speed and compression efficiency. At fixed bitrate it may affect quality; with fixed CRF/CQP, bitrate and quality can both change. Holding measured quality to a target mainly turns this into an encoding-time/file-size tradeoff. An extra ambiguous speed/quality selector is therefore removed from automatic mode. [FFmpeg encoder documentation](https://ffmpeg.org/ffmpeg-codecs.html) describes the encoder-specific preset controls.

## Test queue and directories

Open **Quality tests** from the sidebar or **Test encoding options** in Output settings. Browse to a source directory and load videos; this separate scan preserves the media library and also allows videos already selected in the library. Choose a test video. The Auto setup, software/hardware method, GPU backend, and container come directly from Media library output settings. The test page displays a read-only summary and an Edit output settings shortcut; it does not duplicate these controls. Source-based and Custom users switch to Auto before generating measured presets.

Add one or more tests. Each snapshots the current Media library output settings and runs serially with other tests and full encodes. The queue displays waiting/running/completed/failed/cancelled status, active codec and encoder, quality value, sample number, completed encoder and sample counts, elapsed time, current operation progress when FFmpeg reports it, and an activity log. Overall progress counts completed encoders and reserves the final part for preview generation; it is not a time estimate. Short operations may finish before reporting intermediate progress.

Pause finishes the active test and holds remaining tests. Adding tests preserves a paused queue. Resume continues it; Cancel stops a queued, waiting, or active test. Finished entries retain recommendations and independent preview pairs without resetting playback on refresh. Clearing finished entries removes them from the session queue but retains their saved files.

Each test defaults to creating `Archiver-test-<id>` beside the selected source video, including when that video is in a subfolder of the scanned directory. All references, trial encodes, VMAF logs, previews, and reports for that test use this location. An unwritable source folder reports an error instead of silently using another drive. The API still accepts an explicit directory override for existing integrations, but the normal UI needs no directory selection. FFV1 references, trial encodes, and VMAF logs use a temporary subfolder there, removed on completion, failure, or cancellation. Successful tests retain `results.json` and any generated comparison clips in the per-test folder. Source scans skip generated test folders. Queue state is session-only; reports and previews remain on disk after exit. Full encodes use validated session results when the source/preferences match, and results for other sources serve only as starting points for individual validation.

## Analysis

Analysis is entirely local, serial with encoding, and cancellable. There is no wall-clock deadline for a quality test, its source inspection, sample processing, VMAF scoring, or comparison-preview generation. It continues until it finishes, fails, or you cancel it. Short samples, cached measurements, bounded search iterations, and early rejection of failed settings control the amount of work; elapsed time does not stop it. The regular directory scanner retains its separate per-file metadata timeout.

The speed-oriented sample plan is independent of source length. For sources at least 33 seconds long, one central clip supplies 10 assessed seconds per search setting, with one additional second for encoder warm-up. Each encoder's finalist is checked against two fresh clips near the beginning/end, giving at most 30 assessed seconds across three clips and 33 encoded seconds including warm-up. References and matching per-setting sample results are cached within the search; validation does not re-encode an already tested clip. A failed validation scene stops that setting early before trying a more conservative setting. No automatic expansion beyond this footage budget occurs. Multiple settings/codecs still require repeated processing of these short clips, so total elapsed time can exceed 30 seconds.

For sources between 12 and 33 seconds, three shorter, non-overlapping clips use the same search/holdout split. Sources shorter than 12 seconds are sampled in full and explicitly have no independent holdout. FFV1 references preserve resolution and consecutive frames; VMAF scores every assessed frame. Final-file verification also uses at most three short scored regions, excluding their warm-up portions.

Netflix's [model documentation](https://github.com/Netflix/vmaf/blob/master/resource/doc/models_v0.md) describes 10-second clips in the subjective data used to train the model. It does not prescribe a universal minimum duration or guarantee that 30 seconds represents an arbitrary long video. Using one search clip and two validation clips is Archiver's engineering tradeoff for speed, not an official Netflix recommendation. These distributed samples can miss difficult scenes. Sampling version 2 invalidates cached recommendations from earlier sampling plans without changing the VMAF model or quality thresholds.

Each encoder receives a bounded search of its native CRF/CQP values. Previously analyzed batch settings seed the search; they never bypass per-file validation. Trial results are reused within a search. Finalists that fail fresh-scene checks are retried at more conservative settings. Recommendations can be reused within the application session only when source path, size, modification time, tool identities, policy, and preferences match. This is a metadata fingerprint rather than a full content hash.

Every sample verifies decoded frame counts, dimensions, and timestamp alignment before VMAF evaluates all scored frames. Scores use `vmaf_v0.6.1neg`, policy version 1. The preview engineering defaults are:

| Target | Minimum mean per sample | Minimum frame 5th percentile per sample | Minimum one-second block mean |
|---|---:|---:|---:|
| No perceived quality loss | 97 | 93 | 90 |
| Web publishing | 93 | 86 | 80 |
| Smaller files | 88 | 78 | 70 |

These thresholds require subjective calibration across real footage, including grain, animation, motion, dark scenes, and small text. They are not claims of universal perceptual equivalence. VMAF model validity depends on viewing conditions, and applying this fixed model at native resolutions is a preview limitation. Do not interpret scores from different resolutions as directly interchangeable. The comparison measures additional degradation relative to the existing compressed source, not its original master.

Estimated savings concern video only. Source video bitrate comes from stream metadata when available, otherwise sampled compressed packet sizes and durations. Content variability, audio, and container overhead affect final size. There is no minimum savings requirement. Size estimates are informational and quality-passing outputs may be larger than the source.

Before a measured output is published or replaces an original, Archiver verifies duration and checks distributed regions of the final encode against the same quality policy. Failure retains the source and removes temporary output. Existing replacement/Recycle Bin safeguards still apply. Use Preserve Originals while evaluating this preview.

Comparison previews are silent eight-second clips. The source preview is encoded as lossless H.264; the candidate uses the recommended encoder. Playback depends on browser support, including support for lossless H.264, AV1, and HEVC. Preview generation failure does not invalidate measured results. Each successful test retains its own preview pair in its source-side test directory. Large high-resolution samples require substantial temporary disk space; the analyzer checks available space before extraction.

## Rollback

Keep the previous release extracted separately. Version 0.3-preview.9 uses port 8881, leaving all previous versions on their existing ports. Stop the preview and launch 0.2 to roll back. Both releases are source distributions using your installed Python/FFmpeg; no media tools are bundled. Existing build archives are never overwritten. This preview has not been published to GitHub.

## Reference documentation

- [FFmpeg libvmaf integration](https://ffmpeg.org/ffmpeg-filters.html#libvmaf)
- [Netflix VMAF models and NEG guidance](https://github.com/Netflix/vmaf/blob/master/resource/doc/models_v0.md)
