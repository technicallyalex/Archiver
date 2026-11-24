# Unreadable video metadata

A container can declare H.264, BT.709 and dimensions while its video index contains no usable samples. Unknown pixel format is not evidence of HDR, high bit depth or unsupported chroma sampling. Archiver now distinguishes unknown/unreadable video metadata from a confirmed unsupported automatic-test format.

Normal probing rejects a video track whose pixel format remains unknown. The bounded import attempt can still fall back to normal probing. Older cache entries with incomplete metadata are re-inspected. Pending manual encoding jobs also check imported metadata for this condition. Valid unsupported formats continue to receive the automatic-test format restriction; Manual remains available for supported manual conversion paths.

For the reported case, read-only inspection found zero video samples in stsz and zero entries in stts, stsc, stss and co64. Default and enlarged FFmpeg probing produced no decoded video frames. The file's large media-data area does not establish that its index is usable. A generated H.264 BT.709 1080p59.94 control was accepted for automated validation and successfully encoded manually to H.264 and AV1.

These diagnostics do not repair media. Another complete copy, a re-export from software that can open it, or specialized container/index recovery may be needed. Original media is never modified by metadata inspection.
