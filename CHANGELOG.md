# 0.3.0-rc.18 — Release candidate

- Combined Video Tools, About, Updates, and Feedback into one accessible Settings dialog. The dialog stays anchored near the top while panels expand downward and long content scrolls internally.
- Added user-invoked GitHub update checks with stable/RC channel selection, checksum verification, and automatic Windows installation.
- Updates replace the installed app in its existing folder after shutdown while preserving settings, presets, queues, cache locations, external dependencies, and user files. A separate helper verifies the installed runtime and restores previous application files if replacement or verification fails. Recovery backups and a transaction report are retained.
- Updates require an idle queue and paused watch folders.

# 0.3.0-rc.14 — Release candidate

- Fixed Encoding Queue viewport rebound during progress refreshes, including near the bottom of terminal view. Terminal scrollback and follow-output remain independent.
- Distinguished unreadable video metadata from unsupported color formats, rejected incomplete video indexes before encoding, and re-inspected incomplete cached metadata.
- Preserved the original rounded, tightly spaced wordmark while correcting the low v and final r. Updated matching wordmarks and the multi-size Windows icon; the green arrow remains unchanged.

# 0.3.0-rc.10 — Release candidate

- Fixed idle downward scrolling in Encoding Queue terminal view caused by browser scroll anchoring during progress refreshes. Terminal scrollback and follow-output behavior remain independent of the queue viewport.

# 0.3.0-rc.9 — Local candidate

- Added an optional replacement working folder. Encodes and verification run there; a verified backup frees source-disk space before transferring the verified encode back. Failed/interrupted transfers retain recovery files. Storage guards and saved presets support the working folder; portable presets omit machine-specific paths.

# 0.3.0-rc.8 — Release candidate

- Made the source-folder field expand into available import-row space as the window grows, retaining compact controls and responsive wrapping.

# 0.3.0-rc.7 — Local candidate

- Reduced the source-folder field width and compacted import controls so metadata mode and import options share one row where space permits.

# 0.3.0-rc.6 — Local candidate

- Integrated output settings directly into each encoding queue card as compact wrapping label/value rows, removing the nested panel.

# 0.3.0-rc.5 — Local candidate

- Added an always-visible output settings summary to each encoding queue entry, using its saved configuration and resolved encoder parameters.

# 0.3.0-rc.4 — Local candidate

- Added Import cache settings with a persistent user-selected directory, entry count, storage usage and safe copy to a new empty location. Repeat imports reuse unchanged metadata without FFprobe.

# 0.3.0-rc.3 — Local candidate

- Added Files only import, which lists video files and sizes without probing metadata or generating previews. Analyze selected files later while retaining selection and file identity.

# 0.3.0-rc.2 — Local candidate

- Added Match source container for per-file MP4, MOV, MKV and WebM output, including mixed-container replacement batches. Container and codec compatibility checks remain active.

# 0.3.0-rc.1

First public release candidate for Archiver 0.3.

- Redesigned Media Pool, Test Queue and Encoding Queue with light/dark themes.
- Automated XPSNR quality searches using ab-av1, motion-aware sampling, independent validation and selectable test depth.
- Original-codec split comparisons, per-sample target results and final recommendations without proxy re-encoding.
- H.264, H.265, AV1, configurable ProRes profiles, and half/quarter-resolution proxy workflows.
- Faster cached metadata import, multi-select pool filters and persistent subfolder exclusions.
- Recoverable queues, output verification, storage monitoring, encode reports, preservation controls and watch folders.
- User presets with startup defaults and portable import/export.
- Notification history, opt-in queue auto-start, readable test folders and a header Feedback link.
- Windowless Windows launcher, bundled ab-av1 and third-party notices; FFmpeg/FFprobe remain external with a setup helper.

Internal candidate notes follow.

# 0.3 Release Candidate 14

- Move Watch folders beside Browse in the Media Pool import toolbar.
- Remove the redundant Import progress button; keep the import toast and notification history.
- Use a native notification-popover invoker so the bell reliably toggles the panel with pointer and keyboard input.

# 0.3 Release Candidate 13

- Allow representative test-file selection from the entire loaded Media Pool when nothing is selected.
- Keep selected-file scoping when there is a pool selection, and preserve manual test-file choices without changing that selection.
- Clarify empty-pool and automatic file-selection guidance.

# 0.3 Release Candidate 12

- Order each test card as timeline and progress, comparison, results, then Test details.
- Move terminal output into Test details and preserve comparison playback and disclosure state during updates.

# 0.3 Release Candidate 11

- Give Results, Comparison and Test details permanent regions in every Test Queue item.
- Show skeleton placeholders and explicit queued/running/unavailable states until real data arrives.
- Keep Test details in one location from startup through completion and preserve its disclosure state.

# 0.3 Release Candidate 10

- Simplify comparison to an on-video draggable split with a compact play/pause, seek and time bar.
- Autoplay and loop measured clips when visible, preserving manual pause across refreshes and pausing offscreen/background playback.
- Remove extra view modes, split-position slider, frame-step button and explanatory clutter; retain sample and target/final result selection.

# 0.3 Release Candidate 9

- Remove comparison save controls.
- Try actual video playback instead of rejecting inconclusive codec hints, including shorthand AV1.
- Keep an explicit loading/error state inside the comparison until actual frames are ready, and preserve decoding errors across refreshes.
- Serve the original comparison source with its actual container MIME type.

# 0.3 Release Candidate 8

- Preserve Test details and other test disclosure states during active refreshes and completion.
- Simplify test timing: Test progress and elapsed time on the left; ETA on the right. Keep predicted full-video encode times in the detailed measurements.

# 0.3 Release Candidate 7

- Name new test folders with the local test start date and time, such as Archiver-test-2026-11-02_10-45-30.
- Add a sequence suffix for same-second collisions without overwriting existing test data. Existing folders and exclusion behavior remain compatible.

# 0.3 Release Candidate 6

- Show synchronized original-codec comparisons once a sample evaluation finishes.
- Retain each sample's checked attempts and select its first target-meeting result for comparison.
- Automatically switch to the final recommended setting on completion, with a selector to revisit each sample's target result.
- Preserve comparison playback during progress refreshes. Use the original source and stream-copy output remuxing only; never re-encode comparison video or substitute proxies.

# 0.3 Release Candidate 5

- Measure motion for independent and adaptive validation clips during lossless reference preparation.
- Match preview motion scores by clip timestamps instead of list position.
- Show Pending, Unavailable or Not measured when a motion score is not available; retain all measured clip scores in results.

# 0.3 Release Candidate 4

- Test Queue starts only on request unless Start tests when files are queued is enabled.
- Match Encoding Queue behavior: explicit pauses and recovered queues stay paused; active queues continue normally.
- Watch-folder tests honor each rule's explicit automatic-start choice.

# 0.3 Release Candidate 3

- Fix stale selected dropdown labels after codec and mode changes.
- Synchronize styled selected labels with the actual option while preserving disabled-option explanations and open menus.

# 0.3 Release Candidate 2

- Add Fast, Balanced (default), and Extensive test coverage levels without changing the XPSNR target.
- Explain representative-file testing versus testing each file, expected runtime and sample limitations in the Test Queue.
- Keep independent validation at every depth, with level-specific scouting, clip counts and expansion budgets.

# 0.3 Release Candidate 1

- Direct difficult-clip CRF searches replace repeated expanded-average searches after validation failures.
- Check known weak clips first; preserve strict per-clip targets and independent validation.
- Bound variability-only expansion to one extra coverage pass with cached checks and no repeated search.
- Report estimates from all validated clips rather than extrapolating only the difficult clip.
- Shared themed terminal windows and safe semantic log coloring across both queues.

## 0.3-preview.128

- Stabilize sample preview playback with explicit native seek loops, frame-progress/low-frame-rate detection, proxy-stall recovery and source-generation guards for pending play requests.
- Warm required fallback clips one at a time before assessment without playing inactive previews or blocking analysis. Allow idle hardware for fallback generation during selected-preview preparation.
- Release inactive full-resolution native decoders, preserve poster thumbnails and add regression coverage for switching, stale playback, recovery and bounded warm-up.

## 0.3-preview.127

- Fix quality tests failing with WinError 6 after CRF search: all media/validation subprocesses explicitly detach standard input from the windowless launcher.
- Apply the same launch safeguard to process cleanup and NVIDIA telemetry.
- Add invalid-handle regression coverage and a packaged runtime check for media subprocess launch after terminal capture.

## 0.3-preview.126

- Move Test Queue and Encoding Queue setup/actions into independent right-hand controls panels. Keep job previews, results and progress in the center, with persistent primary actions in the sidebar footer.

- Show actual motion-probe locations and live planned/active/completed states during scouting, including parallel probes, instead of placeholder test samples.
- Reuse loaded timeline thumbnails while probe progress updates, then switch to selected sample previews once selection finishes.

## 0.3-preview.125

- Place Quality mode first in every output workflow, followed by codec and encoding method.
- Keep dropdown controls in place and avoid rewriting unchanged option labels during polling, so open menus remain open.
- Compact the parallel import selector and menu to fit its short labels.

## 0.3-preview.124

- Make timeline sample highlights translucent over filmstrip thumbnails.
- Compact Video Tools to one line with a red/green readiness dot; keep Exclusions visible but disabled until subfolders are enabled; shorten the adaptive import option to Auto.
- Put quality mode first in the dedicated proxy panel. Offer H.264, H.265, AV1 and ProRes, with safe subfolder/next-to/custom destinations, concise descriptions and portable preset support.
- Remove the optional queue sample-quality check and ignore legacy saved flags. Automated (Test) retains its existing final validation. Verify expanded proxy commands with software and NVIDIA encoders.

## 0.3-preview.123

- Address all 24 findings from the preview.122 systems audit: startup/recovery validation, durable queue changes, independent test handoff, storage pause handling, preset initialization/portability, comparison request/playback lifetime, contrast, watch-folder browsing/state, and verification edge cases.
- Show pixel-format conversions and verify declared output precision. Preserve native XPSNR precision for matching formats; report infinite static-content scores explicitly as Identical.
- Add regression checks and repeat generated-media, browser, crash/restart and packaged application checks. Preview build only; no release published.

## 0.3-preview.122 — 2026-11-01

- Integrate output verification, recoverable queues, storage checks and per-encode reports into Encoding Queue.
- Verify intended duration, dimensions, frame rate, track counts and reported color properties before publishing. Full decode scans default on; independent sampled XPSNR checks are optional for manual jobs and remain mandatory for tested encodes.
- Journal queues atomically, offer paused recovery after restart, restart interrupted files, and use completion receipts to keep completed outputs untouched. Recovery journals are isolated by application build for rollback.
- Aggregate storage planning by volume, show estimates versus source-size budgets, monitor low space/disconnections and hold interrupted jobs for retry. Staging files remain on the output volume.
- Save escaped HTML and JSON reports beside outputs, with source identity, settings, exact command, tool versions, actual size reduction and verification results. Report-writing errors do not discard completed media.
- Add on-demand synchronized source/output and amplified-difference previews inside completed Test Queue results, using their exact validation pairs. Cache browser proxies in the existing test folder; offer native dimensions and prepare only while media work is idle.
- Add explicit audio/subtitle selection and metadata/date/chapter/color controls in Output settings. Block incompatible track copies before queueing; require explicit text subtitle conversion. Preserve supported stream flags and reject automatic HDR-to-SDR changes.
- Add restart-safe watch folders beside Media Pool import controls: stable-file delay, current saved presets, per-file automated tests where selected, relative folder structure, output/proxy/test exclusions, individual errors and retry. Watch-folder actions always retain originals.
- Add portable preset import/export to the existing Presets panel. Strip machine-specific paths and measured test bindings, validate available encoders, and reset imported output actions to Keep originals.

## 0.3-preview.121 — 2026-11-01

- Add Install missing tools to Video tools, using the existing setup helper in the background with download/verification status and completion notifications.
- Reuse working installations, download compatible FFmpeg/FFprobe when needed, and restore missing or incompatible ab-av1 using the official release asset and published SHA-256 digest.
- Automatically verify and save executable paths for future launches; pause queued work and prevent concurrent setup/path changes. Allow retry after download or verification failures.

## 0.3-preview.120 — 2026-11-01

- Replace separate FFmpeg/ab-av1 header entries with a single Video tools button and shared Ready / Setup required indicator.
- Combine executable setup, dependency diagnostics and ab-av1 installation details in one panel.
- Require verified FFmpeg/FFprobe, supported output encoding, FFV1 references, XPSNR/motion filters and an ab-av1 build supporting XPSNR search/JSON results before media work can start.
- Disable import/test/encode entry points and enforce the same checks on work-start APIs and schedulers. Keep setup, diagnostics and non-media management available.
- Apply FFmpeg configuration atomically and pause waiting work when tools change so queued jobs can be resumed deliberately.

## 0.3-preview.119 — 2026-11-01

- Combine FFmpeg status and its settings access into one header entry.
- Add an ab-av1 header entry showing detected version/readiness, with installation status, bundled/PATH location, executable path, repository link and Check installation action.
- Cache ab-av1 version checks by binary identity so ordinary status refreshes do not repeatedly launch the tool. Report missing/invalid installations without breaking the interface.

## 0.3-preview.118 — 2026-11-01

- Present Test Queue as a visible child of Media Pool in the left navigation, with indentation and a connecting branch. Keep Encoding Queue separate at the top level.
- Preserve direct access, counters and keyboard tab navigation. Retain the parent-child cue in the compact icon rail.

## 0.3-preview.117 — 2026-11-01

- Align the source input, Browse, subfolder controls, parallel import selector and import buttons with a consistent 41px control height and centered checkbox labels.
- Keep alignment consistent when Exclusions is visible and when toolbar controls wrap. Match the custom exclusion input and Add button heights.

## 0.3-preview.116 — 2026-11-01

- Group nearby successful queue completions into updating toasts, separately for encodes and tests. Use a five-second rolling completion gap with a thirty-second maximum group span.
- Keep failures individual and prioritize their toast space. Preserve every completion as an individual notification-history entry under the existing 500-entry retention limit.
- Add combined Type and Source filters, matching counts, reset filters and a filtered-empty state. Sources include encodes, tests, both queues, imports and app actions.
- Link grouped success toasts to the corresponding filtered results. Keep filters and clear-all controls visible while the history list scrolls.

## 0.3-preview.115 — 2026-11-01

- Add success/failure notifications for Encoding Queue and Test Queue results, recorded by Archiver even when the browser is closed. Link notifications back to their queue item.
- Add a notification-history panel in the header with unread count, timestamps, clear history and persistent local storage for the latest 500 entries. Existing action toasts and completed import summaries are included.
- Stack dismissible toasts and import progress on the left without overlap. Toast expiry pauses while hovered or keyboard-focused. Historical entries are not replayed as toasts after reload.
- Review the three main pages, output modes, dialogs and flyouts across light/dark themes and nine viewport sizes. Compact narrow-screen toolbars and queue controls, retain consistent heading/content alignment and prevent horizontal overflow.
- Hide stale speed/ETA information for waiting and finished queue items. Avoid retransmitting unchanged history on each poll.

## 0.3-preview.114 — 2026-11-01

- Show the selected preset name on the output-settings header button, with Modified when current controls differ. Keep the full name and status available in the button tooltip and accessible label.
- Add an Archiver filename part. Keep originals defaults to {original}_{archiver}; the Archiver tag becomes removable when another filename part or custom suffix is present.
- Restore the Archiver tag if the final replacement part is removed. Recognize literal _archiver suffixes from older presets and support the token in preview and queued filename generation.

## 0.3-preview.113 — 2026-11-01

- Move saved output presets into a compact panel opened by Presets beside the Output settings heading.
- Add immutable Default settings that restore the built-in output configuration, including hidden controls and proxy defaults.
- Allow any saved preset to be used on startup, or return startup to built-in defaults. Preserve the startup choice through rename/update; deleting it falls back to built-in defaults.
- Migrate existing preset files without losing configurations. Opening the panel, applying a preset or loading a startup preset never starts encoding.

## 0.3-preview.112 — 2026-11-01

- Apply the approved test timeline design: rounded lower range bars with start/end ticks, stronger centered connectors, and no dots above the filmstrip.
- Keep true-position range highlights on the filmstrip and readable minimum-width range locators below it. Exact timestamps and durations remain visible and available in tooltips.
- Shift preview cards and stack close range markers to avoid overlap, including at timeline edges and narrow widths. Highlight only the sample currently being assessed.

## 0.3-preview.111 — 2026-11-01

- Add named user output presets with Save as, apply, update settings, rename and delete controls. Presets persist across restarts and versioned builds in the user's Archiver configuration folder.
- Save codec, encoder method, quality controls, resolution/frame rate, audio, container, filename template and output destination, including Proxy and ProRes workflows.
- Show modified output settings without overwriting a saved preset. Applying a preset fills controls for review and never starts encoding.
- Exclude source metadata, file selections, quality-test IDs and destructive confirmations. Automated Test presets require a matching test for the selected footage.

## 0.3-preview.110 — 2026-11-01

- Remove the separate Output preset menu. Proxy is now a Quality mode in the existing codec / method / quality flow.
- Select Half or Quarter resolution with buttons inside Proxy controls. Use the primary codec selector for H.264 or ProRes 422 Proxy; unsupported codecs explain their disabled state.
- Preserve transcode and proxy control values independently while switching modes. Keep existing proxy encoding, audio, filename and Proxies subfolder rules.

## 0.3-preview.109 — 2026-11-01

- Style native scrollbars to match the light and dark themes across viewers, output settings, dropdowns and logs. Use solid-color rounded thumbs with hover and active states, and preserve system scrollbars in high-contrast mode.

## 0.3-preview.108 — 2026-11-01

- Scout 12–48 stratified two-second motion probes based on recording duration; select 6–8 eight-second search clips where duration permits, preserving the highest-motion candidate.
- Validate the suggested setting on each search clip and additional nonoverlapping held-out clips. Keep one holdout outside all search rounds and report every clip’s XPSNR.
- Expand footage when a clip misses the target, clip scores differ by more than 3 dB, clip bitrates differ by more than 2×, or successive size estimates differ by more than 10%. Reuse matching clip checks and lossless references.
- Allow up to four adaptive search rounds without an elapsed-time cutoff. Never offer a recommendation that fails a checked clip. Flag remaining variability in output-size estimates.
- Key sample proxy caches by timestamp and duration so expanded sample sets cannot play stale clips. Keep larger preview sets readable in multiple rows.
- Centered pins and range brackets are provided as a separate design mockup; the app keeps the existing timeline markers pending review.

## 0.3-preview.107 — 2026-11-01

- Replace sample-preview and timeline-thumbnail loading wheels with full-frame skeleton placeholders using a gentle solid-color pulse. Respect reduced-motion preferences and keep existing loaded/error transitions.

## 0.3-preview.106 — 2026-11-01

- Move subfolder exclusions into a compact flyout attached to Include subfolders, with concise explanatory text.
- Combine proxy exclusions into one Proxy folders checkbox covering Proxy, Proxies, Proxy Media and Final Cut Proxy Media. A tooltip explains editor layouts and custom locations.
- Migrate saved proxy choices and preserve custom exclusions. Keep original-media folders eligible for import.

## 0.3-preview.105 — 2026-11-01

- Remove the matching-parent-filename import exclusion; old saved preferences and client flags no longer hide same-named source videos.
- Automatically number conflicting output filenames across a batch, queued jobs and existing files. Naming previews use the same allocator.
- Resolve collisions that appear during encoding when publishing the completed output, without re-encoding or overwriting another file. Explicit Replace originals behavior is unchanged.

## 0.3-preview.104 — 2026-11-01

- Remove legacy ProRes codec descriptions and the ProRes-only qualifier on MOV.
- Use exact ProRes profile names in the profile dropdown and keep current workflow and compatibility explanations.

## 0.3-preview.103 — 2026-11-01

- Expose Copy original audio in output settings, retaining all mapped audio tracks without re-encoding.
- Show Same as source for copied-audio bitrate and restore the encoding bitrate when switching back.
- Allow compatible Opus/Vorbis stream copy in WebM and explain incompatible source audio without silently transcoding it.

## 0.3-preview.102 — 2026-11-01

- Keep desktop workspace scrolling inside the active viewer, placing the Media Pool scrollbar beside the pool instead of at the window edge.
- Preserve independent output-settings scrolling, per-tab viewer positions and logo-to-top behavior; keep normal document scrolling on narrow layouts.

## 0.3-preview.101 — 2026-11-01

- Fix Automated (Estimate) incorrectly using quality-test source restrictions; accept full-range 8-bit SDR footage and convert its pixel range explicitly when encoding.
- Return specific estimate failure reasons instead of interpreting any mention of a test as a test requirement.
- Show clearly labeled partial output-size estimates for mixed selections, with affected filenames and reasons in the details tooltip.

## 0.3-preview.100 — 2026-11-01

- Allow multiple selections in every Media Pool filter using checkbox pickers. Match any selected value within one filter and combine different filters.
- Preserve choices while pool options update, keep menus open for multiple selections, and support keyboard navigation and per-filter/global reset.

## 0.3-preview.99 — 2026-11-01

- Cache imported metadata locally in SQLite across restarts, invalidating changed files, tools and parser versions. Keep quality analysis and output verification uncached.
- Try bounded metadata inspection for indexed containers, with normal inspection fallback and a shared timeout budget.
- Add Auto import concurrency with throughput-based admission and stall/timeout backoff; retain fixed 4/8/16 options.
- Show cached, inspected and slow reads in a compact import toast. Bound Media Pool thumbnail generation to avoid unbounded competing reads.

## 0.3-preview.98 — 2026-10-31

- Add H.264 as a compact proxy codec at half and quarter resolution, with software and hardware encoding choices.
- Use 8-bit 4:2:0, a short GOP and no B-frames to reduce decoding and seeking work. Scale the target bitrate with dimensions and frame rate.
- Keep source timecode and separate PCM audio tracks in MOV; store H.264 variants beside ProRes proxies in a separate H264 subfolder.
- Include hardware proxy jobs in adaptive queue admission and clarify the dependence of editor playback on hardware decoding.

## 0.3-preview.97 — 2026-10-31

- Add half- and quarter-resolution editing proxy presets using ProRes 422 Proxy in MOV with profile-controlled VBR and source frame rate.
- Retain source filenames, timecode and audio channel counts; write to separate Proxies/Half or Proxies/Quarter folders and keep originals.
- Estimate proxy sizes from Apple profile data rates, dimensions, frame rate and PCM audio. Verify format, timing, orientation and audio layout before publishing.

## 0.3-preview.96 — 2026-10-31

- Apply the language audit across import, output settings, test results, queues, dialogs and errors. Keep standard encoding terminology and explain actions before they run.
- Add read-only per-file encoding details with exact encoder, preset, rate control and metadata provenance. Clarify bitrate estimates and binary size units.
- Align Intel ICQ bounds with the encoder and retain raw errors and commands in technical details.

## 0.3-preview.95 — 2026-10-31

- Tighten native sample playback boundaries and withhold frames until the selected sample is ready.
- Continue checking NVIDIA session availability after adaptive backoff or when parallel encoding is disabled.

## 0.3-preview.94 — 2026-10-31

- Play active test sample ranges directly from source media when supported by the browser; create H.264 proxies only on fallback. Preserve active-only, visible-only looping and bounded recovery.
- Show current source-frame snapshots in Encoding Queue thumbnails, generated from the encode process without a second decoder.
- Add adaptive hardware queue parallelism with resource/session admission, aggregate-throughput feedback, per-job cancellation and serial fallback. Software work and quality searches remain exclusive.

## 0.3-preview.93 — 2026-10-31

- Introduce neutral light and charcoal dark themes with shared solid green accents.
- Add custom path-based humanist wordmark, a matching A-r app icon, and consistent rounded interface icons.
- Polish typography, compact spacing, focus/disabled states, tables, dialogs and progress across all panels. Remove gradients, shadows, blur and shimmer effects.

## 0.3-preview.92 — 2026-10-31

- Remove the centered main-content width cap and align each panel with its header title to use available horizontal space.
- Reduce horizontal padding in import, output settings, test setup and queue panels; allow custom exclusion controls to use the available width.

## 0.3-preview.91 — 2026-10-31

- Add custom folder exclusions as reusable checkbox entries, with Add/Enter and individual removal.
- Save custom names and all exclusion checkbox states in per-user preferences across restarts and builds.

## 0.3-preview.90 — 2026-10-31

- Group Recommended exclusions inside the import panel with an indented branch connector to show it is a child of Include subfolders.
- Expand exclusions whenever Include subfolders is enabled, while retaining optional manual collapse.

## 0.3-preview.89 — 2026-10-31



- Preserve the dependency setup result when the batch launcher pauses, so success/failure exit codes remain accurate.



## 0.3-preview.88 — 2026-10-31



- Include Setup video tools.cmd to download, checksum-verify and configure external FFmpeg/FFprobe beside the application without administrator access or PATH changes.

- Preserve portable relative paths and a shared per-user fallback for later builds; retain the upstream package documentation and licenses.

- Validate required encoders and XPSNR/motion filters and apply settings to an idle running instance when possible.



## 0.3-preview.87 — 2026-10-31



- Add a live selected-files estimated output total and reduction/increase percentage to Media Pool statistics.

- Include audio, use adjusted bitrate budgets or matching per-file test results, and show unavailable when current settings cannot support a size estimate.



## 0.3-preview.86 — 2026-10-31



- Treat the primary output codec as authoritative across quality workflow changes; synchronize hidden codec fields instead of restoring their stale defaults.

- Use Automated (Estimate) consistently in the description and label its percentage control Estimated bitrate budget.



## 0.3-preview.85 — 2026-10-31



- Match Quick Estimate and filename dimensions to FFmpeg’s rounding for portrait and unusual aspect ratios; verified 1080×1920 → 608×1080.



## 0.3-preview.84 — 2026-10-31



- Rename quality workflows to Automated (Test), Automated (Estimate), and Manual.

- Quick Estimate adjusts the per-file bitrate budget for codec efficiency, actual scaled pixel count, and output/source FPS; expose resolution and frame-rate controls for estimates.

- Label percentages as adjusted bitrate budgets instead of retained quality.



## 0.3-preview.83 — 2026-10-31



- Track FFmpeg encode/reference timestamps to highlight only the individual clip being processed in joined-sample searches.

- Preserve sample video elements through progress and stage changes; pause inactive previews and retry transient playback errors.



## 0.3-preview.82 — 2026-10-31



- Remove the motion-probe sentence from the test setup settings summary.



## 0.3-preview.81 — 2026-10-31



- Fix Test Queue cards failing to render after an Encoding queue thumbnail change accidentally referenced an undefined variable in the test template.

- Distinguish display errors from actual connection failures during state refresh.



## 0.3-preview.80 — 2026-10-31



- Restore source metadata reuse in manual controls: compatible recorded CRF/CQP values take priority, with reported average video bitrate as fallback.

- Label the choice Reuse reported bitrate / quality metadata and explain that values come from each source file rather than being inferred.



## 0.3-preview.79 — 2026-10-31



- Use FFmpeg rate-control terminology and mode-specific explanations, with a link to official codec documentation.

- Replace the metadata reuse choice with Reuse reported average bitrate; it uses reported video bitrate without reusing CRF/CQP or forcing source CBR behavior.



## 0.3-preview.78 — 2026-10-31



- Rename the Media Pool quality-test button to Add to test queue.



## 0.3-preview.77 — 2026-10-31



- Navigate home through the logo without reloading the application or replaying import notifications.

- Do not automatically display an already-completed import on initial page load; Import progress still opens the report, and new imports show progress normally.



## 0.3-preview.76 — 2026-10-31



- Remove fixed Mbps choices from manual video bitrate controls; use Custom bitrate for target rates.

- Add individual file thumbnails to Encoding queue cards, backed by queued source metadata so they survive Media Pool rescans.



## 0.3-preview.75 — 2026-10-31



- Skip Windows Recycle Bin and System Volume Information directories during recursive imports. Deleted test folders are renamed by Windows and previously escaped the Archiver-test prefix exclusion when scanning a drive root.

- Add regression coverage for renamed deleted test samples, system storage, and the optional live test-folder exclusion.



## 0.3-preview.74 — 2026-10-31



- Remove the redundant Files are never deleted sentence from the parent-folder filename filter explanation.



## 0.3-preview.73 — 2026-10-31



- Add combinable codec, resolution, frame-rate and file-format filters populated from loaded Media Pool files, with a Clear filters action.

- Rename Select visible to Select all; selection follows the active filters and the count shows matching versus total files.



## 0.3-preview.72 — 2026-10-31



- Align all workspace header titles to the Media Pool inset.

- Add a total test count beside the Test Queue header, matching the Encoding queue count.



## 0.3-preview.71 — 2026-10-31



- Move Media Pool, Test Queue and Encoding queue titles into the workspace header.

- Reduce vertical padding and gaps throughout the workspace and full-height output settings column, preserving text size and independent scrolling.



## 0.3-preview.70 — 2026-10-31



- Explain disabled audio codecs, quality modes, and Replace Originals choices directly in their dropdown labels, identifying the setting or test required to enable them.

- Add disabled audio bitrate explanations while retaining the visible audio guidance and locked filename explanation.



## 0.3-preview.69 — 2026-10-31



- Remove the Custom text filename button; custom text remains editable directly in the template.

- Compact filename buttons without reducing text size, and grey out locked Original name.



## 0.3-preview.68 — 2026-10-31



- Build output filenames with ordered part buttons and an editable template with live previews.

- Lock Original name when Preserve Originals is selected, including server-side validation.



## 0.3-preview.67 — 2026-10-31



- Remove the Remove audio option from output settings.



## 0.3-preview.66 — 2026-10-31



- Place import progress at the lower-left of the window and fade it away four seconds after completion. Import progress can still reopen it.



## 0.3-preview.65 — 2026-10-31



- Rename the test navigation tab and page heading to Test Queue.



## 0.3-preview.64 — 2026-10-31



- Remove the redundant Encoder dropdown from Manual controls. Codec and encoding method determine the encoder; unavailable combinations show a clear message.



## 0.3-preview.63 — 2026-10-31



- Move Media Pool import progress and scan activity into a dismissible, non-modal toast. Imports continue after dismissal; Import progress reopens it.



## 0.3-preview.62 — 2026-10-31



- Persist folder history separately for Media Pool, encoding destination and test-output Browse dialogs across restarts/builds.

- Prefer valid explicit field paths, then saved context history, then source-folder/global/home fallbacks; cancellation never replaces history.



## 0.3-preview.61 — 2026-10-31



- Rename the navigation tab to Quality Test Queue.



## 0.3-preview.60 — 2026-10-31



- Slightly indent dependent output controls beneath numbered primary settings, with a subtle guide line and compact mobile spacing.



## 0.3-preview.59 — 2026-10-31



- Replace the quick-estimate per-file bitrate readout with a short explanation of source bitrate, codec efficiency, and quality-level adjustments.



## 0.3-preview.58 — 2026-10-31



- Give Output settings a dedicated full-browser-height right column on desktop, with independently scrolling controls and a persistent Add to queue footer.

- Resize Media Pool/header space around the column; restore full width in Quality Test and Encoding queue.

- Keep a bounded, independently scrolling settings panel on narrower screens.



## 0.3-preview.57 — 2026-10-31



- Hide and disable Original filename under Preserve Originals, switching an existing selection to the custom-suffix naming option.



## 0.3-preview.56 — 2026-10-31



- Explain automatic PATH detection in About and FFmpeg settings.

- Remove VMAF credits, capability checks, legacy optimizer/scoring paths, and metric UI fallbacks. Auto search and final quality verification use XPSNR only; vmafmotion remains the independent motion estimator.



## 0.3-preview.55 — 2026-10-31



- Use a consistent same-bitrate comparison in delivery codec descriptions, qualified as typical encoder/content-dependent behavior.



## 0.3-preview.54 — 2026-10-31



- Add per-file Automatic and explicit ProRes profiles with a higher-fidelity preference, source explanations and planning size estimates.

- Support SDR 4:4:4/RGB/alpha sources with appropriate profiles; reject unsupported HDR/12-bit conversion and alpha-losing profile selections.



## 0.3-preview.53 — 2026-10-31



- Remove editing from the ProRes codec description.



## 0.3-preview.52 — 2026-10-31



- Clarify the delivery codec efficiency/quality-per-byte progression and distinguish ProRes as a high-fidelity editing format.



## 0.3-preview.51 — 2026-10-31



- Add a top-right About dialog with Archiver version/repository and linked third-party acknowledgements.

- Keep FFmpeg/FFprobe external with download/setup guidance and an explicit packaging exclusion check.

- Include offline bundled-component license notices and a versioned dependency-notice inventory.



## 0.3-preview.50 — 2026-10-31



- Replace script launchers in user builds with a windowless Archiver.exe and bundled Python runtime.

- Reduce the distribution root to Archiver.exe, _internal, and README.txt; keep source/tests/developer docs out of releases.

- Preserve legacy launchers under scripts/legacy, organize packaging files, and update the project README.

- Support folder picking from the frozen executable and keep logs in LocalAppData.



## 0.3-preview.49 — 2026-10-31



- Rename Subfolder filters to Recommended exclusions.



## 0.3-preview.48 — 2026-10-31



- Audit Media Pool, Quality Test, Encoding queue, settings dialog, and output modes across desktop/tablet/mobile widths.

- Show file format/audio and output naming as visible sections; organize test setup into footage and settings/storage groups without new nested menus.

- Group queue controls by action, display, and cleanup; improve header, import controls, statistics, forms, and small-screen spacing.



## 0.3-preview.47 — 2026-10-31



- Display test-file choices in a compact responsive thumbnail grid with scrollable rows, two-line filenames, full-name tooltips, and grid-aware keyboard navigation.



## 0.3-preview.46 — 2026-10-31



- Select test footage only from selected Media Pool files; remove the separate test-folder scan controls.

- Default test storage to the imported Media Pool root, with a clear location summary and optional Browse/Default override for both single-file and per-file tests.



## 0.3-preview.45 — 2026-10-31



- Show Archiver test folders as a checked-by-default subfolder exclusion.

- Match the Archiver-test- prefix case-insensitively, including renamed/older test folders; count these exclusions with other skipped folders.



## 0.3-preview.44 — 2026-10-31



- Exclude Proxy and Proxies subfolders by default during recursive Media Pool imports, with custom folder-name exclusions.

- Add an optional same-stem parent-folder filter to skip likely proxy copies while retaining sibling and same-folder variants.

- Report excluded folders and parent-name matches separately from scan errors.



## 0.3-preview.43 — 2026-10-31



- Enable parallel Media Pool imports by default with up to 16 concurrent metadata reads.

- Offer 4, 8, or 16 files at a time, retaining a serial-import toggle.

- Benchmark 64 existing NAS videos at 4/8/16/32 workers: median metadata times 2.475/1.399/0.698/0.679 seconds; choose 16 as the default at the point of diminishing returns.



## 0.3-preview.42 — 2026-10-31



- Automatically choose the longest supported selected video while preserving explicit preferences.

- Explain that a single-file test may not represent files with different scenes or motion.

- Add Test each selected file: snapshot output preferences, validate destinations before testing, and queue each successful file with its own bound recommendation.

- Retain individual results with encoding jobs to avoid repeat testing after cache eviction; preserve batch numbering and expose queue-handoff errors.



## 0.3-preview.41 — 2026-10-31



- Remove the eyebrow and subtitle around the Quality test queue heading.



## 0.3-preview.40 — 2026-10-31



- Rename Media library to Media Pool and Quality tests to Quality Test.

- Order navigation as Media Pool, Quality Test, Encoding queue, including keyboard navigation.



## 0.3-preview.39 — 2026-10-31



- Remove the suggested-range, quality-band explanation, and Auto status helper blocks.

- Automatically select a test file from selected library files; offer a source-thumbnail dropdown for choosing a preferred file.

- Move separate-folder loading into an optional disclosure and support thumbnails for independently loaded test videos.



## 0.3-preview.38 — 2026-10-31



- Use a thin NLE-style quality playhead with a downward arrow on the colored XPSNR slider.

- Remove the drag instruction and restore a compact scale layout.



## 0.3-preview.37 — 2026-10-31



- Link the XPSNR quality target heading to official FFmpeg documentation and remove the expandable guidance/sources section.

- Combine the colored scale and slider into one accessible control with a draggable white marker.



## 0.3-preview.36 — 2026-10-31



- Place the completed result summary and Use tested settings above the timeline and terminal, with the action before expandable details.



## 0.3-preview.35 — 2026-10-31



- Remove the technical XPSNR calibration disclaimer from Test details.



## 0.3-preview.34 — 2026-10-31



- Organize Test details into Selected settings, Motion Test results, CRF Samples, and About this test.

- Sort motion samples by source time with time ranges; sort CRF samples numerically and mark the chosen setting and target outcomes.

- Add consistent section spacing and readable explanation widths.



## 0.3-preview.33 — 2026-10-31



- Animate previews only during measured sample assessment; pause during preview/reference preparation, candidate encoding, between attempts and after completion. Joined clips are explicitly shown as scored together.

- Bound motion probing to two independent workers and reuse selected-clip motion measurements collected during lossless reference preparation, avoiding a second source decode.

- Keep CRF attempts sequential and prioritize preview creation before quality analysis.



## 0.3-preview.32 — 2026-10-31



- Generate timeline stills first with two bounded workers; generate selected loop previews before preparing the quality reference and starting the search.

- Prefer hardware H.264 preview encoding (NVENC, Quick Sync, AMF), automatically falling back to software when unavailable.

- Populate the timeline while motion selection is running.



## 0.3-preview.31 — 2026-10-31



- Show measured XPSNR and estimated video size in the completed summary.

- Group Motion Test results and CRF Samples under Test details, with plain-language explanations; remove Analysis details.

- Describe current typical/higher-motion selection accurately rather than promising a low/average/high selection.



## 0.3-preview.30 — 2026-10-31



- Label the quality-target reset button Default.

- Shift neighboring sample cards apart, keeping connectors and sample markers aligned to the actual footage positions.

- Remove the repeated progress/ETA estimate disclaimer.



## 0.3-preview.29 — 2026-10-31



- Reserve the sample-card and timeline layout immediately with skeleton loading placeholders.

- Clear each placeholder as its image or video loads, including cached media; show unavailable states for failed images and honor reduced-motion preferences.



## 0.3-preview.28 — 2026-10-31



- Use tested settings fills editable manual controls while preserving tested CRF/CQ/ICQ tuning and source timing.

- Give encoder launches explicit standard input so the hidden Windows launcher does not inherit an invalid console handle.



## 0.3-preview.27 — 2026-10-31



- Select typical and higher-motion footage from nine random, distributed two-second probes, then search exactly those windows through a lossless reference.

- Keep source-relative size estimates, native adaptive CRF search and adjustable XPSNR targets.

- Simplify result summaries, highlight Use tested settings, retain the tested target when applying, and describe the four output codecs.



# Changelog



## 0.3-preview.26 — 2026-10-30 (local testing build)



- Separated active loop preview generation from timeline still thumbnails. Up to two thumbnail jobs and one loop preview can run concurrently, so thumbnails no longer occupy the loop-generation lane.

- Deduplicates concurrent requests for the same cache artifact, serves cached files without waiting for workers, and retains atomic writes and source-side caches.

- Motion selection is unchanged: scores describe the three ab-av1 distributed windows; no random motion probing, average-based selection, or resampling is performed.

- Folder build on port 8898; earlier builds retained. Nothing published.

## 0.3-preview.25 — 2026-10-30 (local testing build)



- Added a 30–50 dB XPSNR slider and numeric entry, defaulting to 38 with a reset button. Highlights a 36–40 dB starting range and displays a lossy-to-placebo scale.

- Added expandable guidance with primary research and FFmpeg documentation. Clearly distinguishes practical application bands from study-validated thresholds; high targets are not lossless codec modes.

- Carries the selected target through test queue settings, native ab-av1 arguments, reports, cache matching, and final-output verification. Changing the target cannot apply a recommendation tested at another value.

- Preserves the removal of minimum savings requirements and the source timestamp fix.

- Folder build on port 8897; earlier builds retained. Nothing published.

## 0.3-preview.24 — 2026-10-30 (local testing build)



- Removed minimum savings gates from recommendations and final output publication. Quality-passing outputs may be larger than the source; estimated size changes remain informational.

- Keeps XPSNR 38 dB, duration/frame-alignment checks, source-change detection, and the selected original-file handling behavior.

- Invalidates earlier policy-bound recommendations. Added a real encoding regression proving a larger, quality-passing file is published.

- Folder build on port 8896; earlier builds retained. Nothing published.



## 0.3-preview.23 — 2026-10-30 (local testing build)



- Auto now uses ab-av1's built-in `crf-search --min-xpsnr 38`. FFmpeg performs encoding and XPSNR measurements; no separate application search algorithm is added.

- Final output verification uses the same mean XPSNR 38 dB policy, correct reference-first filter ordering, and validated frame alignment. Original-file and 10% savings protections remain.

- Updated capabilities, results, trial tables, and Auto wording for XPSNR/dB. Old VMAF recommendations are invalidated. Historical scores retain their metric labels.

- Preserves the source-time-base fix. No automatic fallback to the old VMAF engine for AMD; AMD users can use software Auto, Quick estimate, or Manual.

- Folder build on port 8895; earlier builds retained. Nothing published.



## 0.3-preview.22 — 2026-10-30 (local testing build)



- Auto sample encodes and final Auto output preserve the demuxer's timestamp precision, avoiding frame mismatches caused by rounding VFR timestamps to an average-frame-rate grid.

- Invalidates older measured recommendations through the sampling fingerprint version. Re-run Auto tests before applying settings in this build.

- Added a regression check for fractional-rate and variable-rate final output. Compared XPSNR and VMAF on the retained Battlefield 3 samples; see docs/XPSNR_COMPARISON.md.

- The default remains VMAF NEG at target 97; XPSNR is an experiment, not a new UI/default. No changes to sample selection or preview playback.

- Folder build on port 8894; earlier builds retained. Nothing published.



## 0.3-preview.21 — 2026-10-30 (local testing build)



- Test results describe estimated output as larger or smaller than the original, instead of displaying ambiguous negative savings. Older saved reports use the clarified wording too.

- ab-av1 NVIDIA results display CQ instead of CQP; Intel quality results display ICQ. Manual constant-QP controls retain their existing labels and behavior.

- Investigated the AV1 NVENC CQ 22–23 quality/size discontinuity with direct FFmpeg reproductions. Search, sampling, quality target, and encoder settings are unchanged. See docs/NVENC_CQ_INVESTIGATION.md.

- Folder build on port 8893; earlier builds retained. Nothing published.



## 0.3-preview.20 — 2026-10-30 (local testing build)



- Confirmed ab-av1 crf-search drives Auto's adaptive quality-setting search. Analysis now uses --max-encoded-percent 10000, allowing target-quality recommendations larger than the source without treating them as search failures.

- Retains intermediate CRF/VMAF/predicted-size/time measurements in the UI and crf-search-measurements.json, including when a search fails. Final Auto encoding still retains the original if worthwhile savings are unavailable.

- Added native-resolution, source-timed vmafmotion analysis for each requested sample window: mean, 95th percentile, peak, frame count, raw per-frame statistics, and within-test relative comparisons. Motion data is saved even if the subsequent quality search fails.

- Motion is informational and does not change quality thresholds or sample selection. Missing filter support reports unavailable motion without breaking quality analysis.

- Folder build on port 8892; earlier builds retained. Nothing published.



## 0.3-preview.19 — 2026-10-30 (local testing build)



- Active sample previews now use cached 320-pixel H.264 video at source timing instead of 3-FPS animated WebP. Fractional and variable frame timing is preserved; previews are silent and loop locally.

- Playback starts only for active visible samples, pauses on hidden panes/tabs or off-screen cards, and keeps its video element attached through progress refreshes.

- Preview generation is single-threaded, low priority, limited to ten seconds, source-side cached, and independent of the quality-test worker. HTTP byte ranges support video buffering/looping. Failed previews retain a still thumbnail.

- Added a practical VMAF score guide. Auto's quality target and source/output safeguards are unchanged.

- Folder build on port 8891; previous builds retained. Nothing published.



## 0.3-preview.18 — 2026-10-30 (local testing build)



- Auto runs one perceptually lossless ab-av1 search at --min-vmaf 97, with at least 10% estimated space savings, instead of testing multiple lossy quality levels.

- Removed the generated quality-level picker and multi-level progress wording. Successful tests provide one tested configuration; failures retain the original without applying unvalidated settings.

- Retains positioned sample previews, filmstrip, native terminal progress and final-output safeguards.

- Folder build on port 8890; previous versions retained. Nothing published.



## 0.3-preview.17 — 2026-10-30 (local testing build)



- Sample cards are positioned over their recording locations with connectors to a chronological thumbnail filmstrip. Removed the blue seekbar and extra scrub-preview image.

- Only the active sample animates at 3 FPS, using a cached low-resolution WebP preview. No FPS badge is shown. Refreshes retain the playing preview; completed/inactive samples return to still images.

- Progress bar and expanded terminal output are below the timeline. Windows hidden-terminal capture exposes ab-av1's actual CLI progress and current-search ETA; progress remains labeled estimated.

- Bundles pywinpty with its license for the current Windows/Python runtime. Other Python runtimes can install the matching dependency or use the pipe-output fallback. Preview generation falls back to stills if animated WebP is unavailable.

- Folder build on port 8889; earlier builds retained. Nothing published.



## 0.3-preview.16 — 2026-10-30 (local testing build)



- Removed Match original / near-source from Auto testing and quality choices.

- Auto now generates visually lossless/reduced-size and nominal 5%, 10%, and 20% loss recommendations.

- Folder build on port 8888. Previous builds retained; nothing published.



## 0.3-preview.15 — 2026-10-30 (local testing build)



- Output flow is now codec, software/hardware encoding method, then quality. Auto reveals the test action.

- One Auto test generates near-source (VMAF 99.5), visually lossless/reduced-size (97), and nominal 5/10/20% loss (95/90/80) recommendations for the selected codec and method.

- Completed tests reveal a quality-level selector. Unavailable targets remain explained in the report without discarding successful levels. Each level carries its own settings, validation policy, and source fingerprint.

- Percentage labels explicitly describe nominal score deficits, not measured perceptual-loss percentages. Exact preservation requires retaining the source.

- Folder build on port 8887 by default. Previous builds retained; nothing published.



## 0.3-preview.14 — 2026-10-30 (local testing build)



- Simplified output settings into codec, quality, encoding method, and save destination. Auto shows one target, a test action, and readiness status; internal engine selection and the redundant generated-preset selector are hidden.

- Collapsed file format/audio and naming options. ProRes uses its own short editing path without irrelevant testing controls.

- Only H.264, H.265/HEVC, AV1, and ProRes remain output choices. Removed extended-codec UI and rejected removed codecs through the queue API.

- Auto selects its testing engine internally; AMD uses the existing analyzer for the selected codec/target.

- Ready-to-launch folder build on port 8886. Earlier builds preserved; no publication.



## 0.3-preview.13 — 2026-10-30 (local testing build)



- Builds now create a ready-to-launch versioned folder by default, with the existing windowless launcher. No manual ZIP extraction needed.

- ZIP archives are optional with `python build_release.py --zip`. Existing runtime requirements and application behavior remain unchanged.

- Uses port 8885. No GitHub publication.



## 0.3-preview.12 — 2026-10-30 (local testing build)



- Added a primary recommended codec selector: H.264, H.265/HEVC, AV1, and ProRes 422 HQ. Selection routes to the appropriate testing, source-based, custom, or editing workflow.

- Added opt-in expanded choices: FFV1, exact source copy, MPEG-2, MPEG-4 Part 2, and Motion JPEG. VP9 remains excluded.

- Extended legacy codecs use manual bitrate controls and MKV, with unsupported CRF/CQP/container combinations rejected. Automatic searches and source estimates remain focused on recommended delivery codecs.

- Uses port 8884. Previous builds retained; no GitHub release.



## 0.3-preview.11 — 2026-10-30 (local testing build)



- Added Placebo / Archival / editing setup with lossless FFV1, ProRes 422 HQ editing intermediates, and exact source copies.

- Automatic format/container controls; originals retained, no quality search or minimum savings requirement. Strict FFV1 pixel format and full decoded-video checksum verification; ProRes duration/dimension and decode checks.

- Included full source metadata in queued jobs so ab-av1 final encoding can reproduce the tested keyframe interval.

- All ab-av1 features from preview.10 retained. Uses port 8883; earlier builds preserved. Nothing published to GitHub.



## 0.3-preview.10 — 2026-10-30 (local testing build)



- Bundled official ab-av1 0.11.7 Windows executable and MIT license. Auto can search a selected AV1, HEVC, or H.264 encoder for one mean quality target.

- Live stdout/stderr console messages, saved full logs, completed attempt metrics, and predicted full-encode time/size.

- Source sample-location thumbnails, active sample indication, marked timeline, and source thumbnail scrubbing. Requested positions are approximate due to keyframe copy boundaries.

- Matched test/final encoder controls, cancellable child-process trees, fingerprinted session recommendations, no test time limit, and existing final-file safeguards.

- Removed VP9 as an encoding output option. Inputs remain readable.

- Port 8882; previous builds retained. No GitHub release.



## 0.3-preview.9 — 2026-10-28 (local testing build)



- Windowless Windows launcher and native branded notification-area icon, with click-to-open and queue/test pause/resume and Quit controls.

- Desktop launches reuse the existing instance for the same port. Browser closure leaves work running; Quit confirms active cancellation and waits for cleanup.

- Startup errors appear in a dialog with a local diagnostic log. No third-party tray dependency added.

- Uses port 8881; earlier archives preserved. Not published to GitHub.



## 0.3-preview.8 — 2026-10-28 (local testing build)



- Removed elapsed-time cutoffs from quality analysis, test source inspection, and comparison-preview generation. Tests finish or can be cancelled regardless of elapsed time.

- Short sampling, shared trial caches, bounded searches, and early rejection remain in place. Regular directory-scan timeouts are unchanged.

- Uses port 8880; previous archives retained. Not published to GitHub.



## 0.3-preview.7 — 2026-10-28 (local testing build)



- Source presets now apply documentation-guided input/output codec-efficiency ratios before quality-tier bitrate budgets.

- Added output-codec selection, server-generated bitrate previews matching queued settings, versioned estimator metadata, and documented primary sources/limitations.

- Optimized selects the most efficient available codec and refuses a less efficient fallback. Auto remains the measured-quality workflow.

- Uses port 8879; previous archives retained. Not published to GitHub.



## 0.3-preview.6 — 2026-10-28 (local testing build)



- Removed the Performance tab, monitoring endpoint, background system/GPU telemetry, charts, and polling.

- Removed the psutil dependency. Archiver now needs only Python plus user-supplied FFmpeg/FFprobe.

- Uses port 8878. Previous builds preserved; not published to GitHub.



## 0.3-preview.5 — 2026-10-28 (local testing build)



- New setups: Auto with required tests and generated presets, immediate source-based codec/bitrate presets, and Custom controls.

- Auto tests generate up to three validated presets while sharing references and trial measurements. Unavailable targets are reported; changed sources/tools invalidate generated presets. Clearing test cards retains session presets.

- Metadata presets: source codec at 100/75/50% video bitrate, or AV1 at 100% source bitrate. Per-file settings for mixed batches; no quality-equivalence claims or silent encoder fallbacks.

- Uses port 8877. Earlier builds remain available; not published to GitHub.



## 0.3-preview.4 — 2026-10-28 (local testing build)



- Removed the ambiguous encoding-speed preset selector from automatic mode. Tests and final encodes use the same internally managed balanced preset and choose the smallest worthwhile output meeting the quality target.

- Removed duplicate quality, hardware, container, and test-tuning controls from the test page. It inherits Media library settings, displays a summary, and links back for editing.

- Test storage defaults to the selected video's own source folder, including all temporary samples, trial encodes, VMAF logs, previews, and saved reports. No output-folder selection required.

- Recursive media-library and test scans skip generated test folders.

- Uses port 8876; earlier builds retained. Not published to GitHub.



## 0.3-preview.3 — 2026-10-28 (local testing build)



- Speed-oriented sampling: one approximately 10-second assessed clip for quality-setting search; finalists use up to 30 assessed seconds across three clips, plus encoder warm-up.

- Stop failed validation settings at the first failing scene; reuse already measured samples. Sample footage does not grow with source duration.

- Queue explicitly distinguishes assessed footage and warm-up from total processing time. Existing 15-minute value is a wall-clock safety limit, not footage length.

- Documented Netflix's 10-second training clips and the limits of short-sample coverage. Sampling-version cache invalidation retains the existing VMAF model and quality policies.

- Uses port 8875; previous preview archives retained. Not published to GitHub.



## 0.3-preview.2 — 2026-10-28 (local testing build)



- Quality-first automatic settings with Software/CPU or Hardware/GPU selection; hardware tests use the chosen NVIDIA, Intel, or AMD backend. Device-compatibility presets removed.

- Dedicated Quality test queue with source-directory browsing independent of the media library, a required user-selected test output directory, and saved per-test reports/comparison clips.

- Live encoder, quality setting, sample, VMAF stage, operation progress, completed trial counts, elapsed time, and activity history.

- Multiple queued tests, pause/resume and cancellation, stable completed previews, and applying a tested policy to selected media-library files.

- Preview uses port 8874; previous preview.1 and 0.2 builds remain available for rollback. Not published to GitHub.



## 0.3-preview.1 — 2026-10-28 (local testing build)



- Simple quality targets: original 1:1 copy, no perceived loss, web publishing, smaller files, and custom settings.

- Local VMAF NEG trials across compatible software and hardware encoders, with quality-setting search, fixed presets, fresh-scene validation, and adaptive sample expansion.

- Measured recommendations, video-savings and encoding-time estimates, comparison previews, cancellation, session caching, and batch search starting points.

- Independent per-file analysis and final-file quality checks before publishing outputs; files without worthwhile savings retain their originals.

- Explicit SDR/pixel-format support checks and provisional quality targets.

- Separate preview port (8873) for side-by-side testing and rollback. Packaging refuses to overwrite an existing version archive. Not published to GitHub.



## 0.2 — 2026-10-20



- Live scan discovery, current-file details, recent activity, and cancellation.

- Optional four-file parallel metadata scanning and a large-directory notice.

- Queue pause, stop, resume, and clear-waiting controls.

- Completed encode size comparisons and output-directory shortcuts.

- Performance tab with CPU, RAM, storage/network throughput, NVIDIA GPU utilization, video encode/decode activity, and history graphs.

- DPI-aware native Windows directory picker.

- UI refinements and updated dependency documentation.



Performance monitoring uses psutil; GPU telemetry requires NVIDIA's installed nvidia-smi. Other GPUs show unavailable. Pause lets the active job finish; Stop cancels it and holds waiting jobs. No FFmpeg or FFprobe binaries are bundled.



## 0.1 — 2026-10-20



Initial release of Archiver, a local FFmpeg video library and transcoding queue.



- Directory scanning with FFprobe metadata and scrubbable thumbnails.

- Separate library and queue panes, light/dark themes, and native folder pickers.

- Software and hardware encoder selection, resolution and frame-rate controls.

- Source-based automatic bitrate, manual CRF/CQP, and custom bitrate controls.

- Multiple audio codecs and bitrates with all source audio tracks mapped.

- Output filename presets, custom suffixes, and numbered batch names.

- Manual or automatic queue starting and three progress display modes.

- Original-file preservation, replacement with Recycle Bin handling, and confirmed permanent deletion.



FFmpeg and FFprobe are supplied separately by users. See README.md for requirements and limitations.
