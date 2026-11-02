# ProRes editing output

Select ProRes 422 HQ from the main codec list. This is the only editing/intermediate codec currently supported. FFV1, source-copy mode, and the other expanded codec choices have been removed from this flow.

ProRes uses software prores_ks profile 3, 10-bit 4:2:2 video and 24-bit PCM audio in MOV. This is a lossy editing intermediate, not a lossless archival copy. Supported inputs are SDR 8/10-bit 4:2:0 or 4:2:2. HDR, alpha, RGB, and 4:4:4 sources should be kept unchanged by this preview.

Originals are retained. Output dimensions/duration and decoding are checked before publication. It bypasses quality searching; files can be much larger. Other streams are mapped, and unsupported MOV streams cause a failure rather than silent removal.
