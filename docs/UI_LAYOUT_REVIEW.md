# Workspace layout review — 0.3-preview.48

Reviewed Media Pool, Quality Test, Encoding queue, and the FFmpeg settings dialog at 360, 420, 768, 1024, 1440, and 1920 pixel widths. Tested Auto, Quick estimate, Manual, and ProRes modes with preserve, destination-directory, and replacement form states (72 combinations); ProRes replacement remains disabled in normal use. Checked dark and light themes, popup/grid selection, keyboard navigation, output section visibility and containment.

Common file-format/audio and naming controls are visible sections instead of disclosures. Save-mode-dependent fields remain conditional. Quality Test groups footage on the left and output/storage on the right on wide screens, then stacks them on smaller screens. Queue controls are grouped into running, display and cleanup actions. Only optional import filters, test storage overrides, detailed measurements, and diagnostic scan logs remain expandable; primary settings do not introduce nested disclosures.

Responsive changes prevent header/logo crowding, make import controls compact, arrange mobile statistics in two columns, stack narrow form rows, wrap job headers and queue controls, and keep overflow inside data tables or the file list rather than across the page. Preview/picker colors follow the active theme; terminal text keeps its dark presentation.

Browser checks exercise visual/layout states without starting user encodes, changing files, submitting tool configuration, or deleting queue jobs. Validation does not claim to test operating-system native folder dialogs on every platform.


## Full-height output column — 0.3-preview.58
On desktop viewports at least 1100 CSS pixels wide, Output settings is a fixed right-hand column spanning 100dvh. Its heading and queue footer remain visible while only the middle controls scroll. The Media Pool workspace, including its header, reserves the column width. Switching to Quality Test or Encoding queue removes that reservation and hides the column. Narrower screens stack a viewport-bounded settings panel with the same independent control scrolling.

Verified Auto, Manual and ProRes at 1280×720, 1440×900, 1920×1080, 2560×1440, 3840×2160, 420×900 and 360×800, checking panel boundaries, queue-button visibility, page overflow, surrounding content clearance and restored full-width other panes.

## Notification and spacing review — 0.3-preview.115

Reviewed Media Pool, Test Queue and Encoding Queue in both themes at 3840×2160, 2560×1440, 1920×1080, 1440×900, 1280×720, 1024×768, 850×900, 420×900 and 360×800. Checked Automated Test, Automated Estimate, Manual, ProRes profiles and Proxy controls. Reviewed FFmpeg settings/About dialogs, preset save/manage dialog, preset/exclusion/filter/history flyouts in both themes at five sizes. Native OS folder-picker internals were outside this browser-layout review.

Findings: desktop heading/content spacing and independent viewer scrolling were retained. Narrow headers used multiple loosely wrapped tool rows; they now use a consistent title row and accessible icon buttons for tools, about, notifications and theme. Queue run/cleanup actions use balanced columns on narrow screens. Waiting and terminal jobs no longer display stale ETA/speed. No document-level horizontal overflow or overlapping header regions remained in the repeated matrix. Tables, long filenames, errors and history entries remain contained and wrap appropriately.

Ordinary toasts and import progress share a bounded left-hand stack. Notification history opens from the header, fits both themes and small screens, supports Escape/outside click, marks entries read and links to queue records. Popup dismissal is independent of history retention; clearing history removes visible message toasts. Keyboard focus and pointer hover pause expiry. Both app and queue notifications are escaped before rendering.

Validation: 203 Python regressions, JavaScript rendering/filter/timeline/notification checks, browser matrix and overlay checks. A real local H.264 encode and invalid-source job produced one success and one failure notification through the queue scheduler. Timing checks verified expiry and focus pause/resume. No user queue or source files were used for layout fixtures.
