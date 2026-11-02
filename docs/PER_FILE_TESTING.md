# Single-file and per-file quality tests

Test one file automatically chooses the longest supported video among the selected Media Pool files. Longer recordings offer more sampling locations but are not guaranteed to represent a batch. Explicit preferences take precedence while the file remains selected. Current Auto eligibility is 8-bit SDR YUV 4:2:0, known positive duration/frame rate and even dimensions.

The scope warning explains that only the chosen file is tested and that different scenes, textures and motion in other files may need different encoder settings.

Test each selected file independently tests every selected Media Pool file and places successful results in the Encoding queue. Output settings and the existing queue auto-start preference are captured at dispatch. Test jobs remain sequential; two short motion probes can run concurrently within each test. Output destination, naming and overwrite confirmations are validated before adding the batch. Batch sequence numbers are retained when files finish independently. If a source or settings change, or an output conflicts before handoff, its completed test remains available with a queue error; failed/cancelled tests do not enqueue an encode.

Each encoding job stores its own source-bound profile and fingerprint, in addition to displaying the chosen encoder and quantizer. A cache eviction does not force reanalysis. Source/tool/settings fingerprint checks and final sampled output verification remain active. Single-file results are not silently bound to other files. Encoding follows existing queue controls; there is no additional concurrent full encode or search.

As of 0.3-preview.46, test footage comes only from the selected Media Pool files. The scanned Media Pool root is the default parent for all test folders, including when footage lives in nested subfolders. Change test folder location provides an optional existing destination folder; Default clears the override. The location is captured when tests are queued and applies to both scopes. Separate test-source folder scanning is no longer exposed in the UI.
