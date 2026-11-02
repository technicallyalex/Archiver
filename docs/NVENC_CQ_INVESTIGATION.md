# AV1 NVENC CQ 22–23 investigation

Investigated 2026-10-30 using the Battlefield 3 test `Archiver-test-3a34e1715b5b580d2a7e`. The source and existing report were read only. Diagnostic media and logs were written under `.test-temp/cliff-probe` locally, not into the source folder. No full-video transcode was performed.

## Presentation fixes in preview.21

Negative savings are now described as a larger estimated output, e.g. **49% larger than the original**. Positive savings are described as smaller. These are sample-based estimates. Older saved reports get the clarified wording when displayed. That build required at least 10% predicted reduction. Preview.24 removed the savings requirement; this document records the earlier investigation.

NVIDIA ab-av1 results now say **CQ**, matching the actual `-cq` option. Intel ab-av1 results say ICQ. The internal `cqp` compatibility value remains unchanged so applying reports and existing settings continues to work. Manual NVIDIA CQP actually uses `-rc constqp -qp` and retains its CQP label.

## Reproduction

Environment: NVIDIA GeForce RTX 5080, driver 621.01; FFmpeg 9.0.1 Gyan full build; ab-av1 0.11.7. Source: H.264, 2560×1440, variable frame timing, approximately 47.41 Mbps video.

The original three-window search returned CQ 21, VMAF 97.576, predicted output 148.684% of source. A separate thorough search of the same three windows returned CQ 22, VMAF 97.433, predicted output 134.878%. CQ 23 returned VMAF 93.164 and 60.384% of source. The original keep-original decision is supported for these tested configurations.

For isolation, ab-av1's copied reference sample at 113 seconds was retained. The same reference was encoded directly with FFmpeg, bypassing Archiver and ab-av1. Baseline output options were:

```
-c:v av1_nvenc -g 598 -fps_mode passthrough -cq VALUE -pix_fmt yuv420p -preset p5 -an
```

VMAF used ab-av1's exact format/timestamp alignment and `libvmaf=shortest=true:ts_sync_mode=nearest:n_threads=8:model=version=vmaf_v0.6.1neg`, without scaling or an input frame-rate override.

| Experiment on the same sample | CQ | Output bytes | VMAF |
|---|---:|---:|---:|
| Baseline | 22 | 71,756,103 | 97.248725 |
| Baseline | 22.5 | 68,906,666 | 97.168012 |
| Baseline | 23 | 32,776,698 | 92.293080 |
| Explicit `-rc vbr -b:v 0` | 22 | 71,756,103 | 97.248725 |
| Explicit `-rc vbr -b:v 0` | 23 | 32,776,698 | 92.293080 |
| Explicit VBR plus `-multipass fullres` | 22 | 72,688,236 | 97.279328 |
| Explicit VBR plus `-multipass fullres` | 23 | 33,131,760 | 92.189375 |

The direct CQ 23 file is byte-for-byte the same size as ab-av1's CQ 23 sample. FFmpeg confirms different CQ values were received: CQ(5632) and CQ(5888), its 8.8 fixed-point representations of 22 and 23. Output bitrate limits are zero; explicitly selecting VBR and zero target bitrate produces identical results. The large size reduction exists in the actual encoded files, independently of VMAF or prediction arithmetic.

## Separate timing finding

FFmpeg reports non-monotonic DTS corrections on this VFR sample. As a diagnostic only, both decoded streams were instead aligned by frame index (`settb=AVTB,setpts=N/60/TB`), retaining every decoded frame. This removes original playback timing from the comparison and must not be substituted blindly into production scoring.

| Experiment | VMAF with frame-index alignment |
|---|---:|
| Baseline CQ 22 | 98.978289 |
| Baseline CQ 23 | 93.985895 |
| p5 CQ 23 with 32-frame lookahead | 93.980094 |
| p7 CQ 23 | 94.048818 |

The approximately five-point CQ discontinuity remains with frame-index alignment. The roughly 1.7-point change in absolute scores demonstrates an additional timing sensitivity that deserves a separate investigation. Timestamp mapping and frame identity need validation before changing VMAF synchronization or encoder time bases.

## Conclusion and limits

The cliff is reproducible in the local FFmpeg/NVENC encoding path. It is not caused by Archiver's reported savings, JSON parsing, adaptive search, cache reuse, different sample locations, or a hidden target bitrate. Neither explicit VBR, multipass, added lookahead, nor p7 removed the discontinuity in these bounded experiments.

This identifies the affected layer, not the proprietary driver's internal cause. It does not establish that all NVIDIA hardware/drivers behave this way. A driver/build comparison on the same retained sample would be needed to isolate a driver regression from FFmpeg integration or content-dependent rate control. No driver updates, encoder changes, new sampling strategy, or search-tolerance changes were made.

Diagnostic files: `.test-temp/audit-bf3/direct-results.json`, `.test-temp/cliff-probe/matrix.json`, `.test-temp/cliff-probe/followup.json`, and their adjacent FFmpeg logs/media. Initial `direct-cq*-vmaf.log` experiments used a different synchronization setup and are not the production-equivalent measurements; use `baseline*-vmaf.log` and the matrix above.

## References

Follow-up in preview.22: the timestamp issue has been corrected by preserving the demuxer time base in Auto sample and final encodes. Identical decoded pixels were verified before/after the fix. The CQ cliff remains. See [the aligned XPSNR/VMAF comparison](XPSNR_COMPARISON.md) for corrected scores and search results; the earlier scores above document the pre-fix investigation.

- [Pinned ab-av1 encoder options and NVENC CQ mapping](https://github.com/alexheretic/ab-av1/blob/v0.11.7/src/ffmpeg.rs)
- [Pinned ab-av1 VMAF timestamp alignment](https://github.com/alexheretic/ab-av1/blob/v0.11.7/src/command/args/vmaf.rs)
- [FFmpeg NVENC rate control and CQ handling](https://github.com/FFmpeg/FFmpeg/blob/master/libavcodec/nvenc.c)
