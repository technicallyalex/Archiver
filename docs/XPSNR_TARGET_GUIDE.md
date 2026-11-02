# Choosing an XPSNR target

Auto defaults to **38 dB**. Its slider and numeric entry allow **30–50 dB**, in 0.1 dB steps. Reset to 38 restores the default. These are application control limits, not the mathematical limits of the XPSNR metric.

The slider runs from visually lossy/more compression to placebo/very high fidelity. The labels describe a practical trade-off, not a certified appearance grade.

| Target band | Archiver guidance | Expected trade-off |
|---|---|---|
| 30–36 dB | More compression | Inspect fine detail, edges, and motion for visible loss. |
| 36–40 dB | Suggested starting range | Start at the default 38; compare the result on your footage. |
| 40–44 dB | Higher fidelity | A stricter error target, often requiring more data. |
| 44–50 dB | Placebo / very high fidelity | Diminishing visible returns; larger outputs or an unreachable search target are possible. |

Band boundaries are shared for display convenience; the live descriptions switch at 36, 40, and 44. The highlighted starting band is 36–40, and its marker identifies the default 38. These numerical bands are **Archiver starting points**, not thresholds established by the sources below. No published universal XPSNR-to-losslessness scale was found in the research reviewed for this change.

Higher scores mean lower perceptually weighted signal error for the same comparison. They do not represent a percentage of quality retained. A finite high target does not guarantee mathematical or visual losslessness. The Placebo label does not select ProRes or any other archival codec; Auto continues to search the codec/method selected by the user.

The reference is the selected input file. Raising the target reduces additional encoding loss; it cannot restore detail already missing from that input.

## Evidence and its limits

[Helmrich et al., ITU Journal (2020), A Study of the Extended Perceptually Weighted Peak Signal-to-Noise Ratio for Video Compression with Different Resolutions and Bit Depths](https://www.itu.int/dms_pub/itu-s/opb/journal/S-JOURNAL-ICTF.VOL3-2020-1-P08-PDF-E.pdf) evaluates association with human opinion scores on multiple video datasets, including UHD and 10-bit content. It supports XPSNR as a quality estimator rather than defining universal 38/40/42 dB transparency boundaries. Its reported experiments use luma measurements; Archiver follows ab-av1's minimum across color-plane averages, so those measurements are not interchangeable.

[FFmpeg's XPSNR documentation](https://ffmpeg.org/ffmpeg-filters.html#xpsnr) describes the measurement and its decibel output, including average and minimum color-plane summaries. It does not assign universal visually lossless targets. Ordinary PSNR quality tables should not be treated as validated XPSNR target tables.

Content, source quality, encoder, preset, bit depth, frame alignment, and viewing conditions affect interpretation. A high overall sample mean can also hide a difficult scene. Visually compare representative output before committing important footage to a new target.

## Local example

The earlier [Battlefield 3 comparison](XPSNR_COMPARISON.md) measured these results on one 1440p recording with AV1 NVENC p5:

- Target 40 dB selected CQ 26, achieved 40.007 dB and VMAF 94.968, with predicted output around 60% of the source size.
- Target 42 dB selected CQ 22, achieved 43.595 dB and VMAF 99.260, with predicted output around 135% of the source size.

This demonstrates that even a small target increase can have a large storage cost. It is one local experiment, not a general mapping from decibels to visibility or compression ratio. There is no minimum savings gate.

## Target binding

Each queued test stores its selected target. The native `--min-xpsnr` argument, result policy, final-output verification, and recommendation fingerprint all use that value. Different targets have separate cached recommendations. Moving the slider does not alter a running test or silently reuse a result from another target. Returning to a previously tested target can reuse a matching valid recommendation. A failed search does not lower the target automatically.
