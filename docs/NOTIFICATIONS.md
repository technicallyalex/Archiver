# Notifications

The header bell opens persistent history for the latest 500 notifications. The badge counts unread entries; opening history marks them read. Clear history removes saved entries and current message toasts. The history file is notifications.json beside tools.json (%LOCALAPPDATA%/Archiver on Windows; XDG_CONFIG_HOME/archiver or ~/.config/archiver elsewhere).

Queue schedulers record completed and failed encodes/tests without depending on a browser connection. Cancelled/skipped active work is informational; hardware-session retries do not announce a failure while still queued. A completed test that cannot enqueue its result reports that enqueue error. Repeated checks of the same job/status do not create duplicate history entries. If queue records have been removed, the notification remains and its action explains that the item is no longer available.

Application action toasts and finished import summaries also appear in history. Import progress retains its dedicated live card; ordinary toasts and that card share a left-hand stack. Up to three message toasts are visible at once; all recorded notifications remain available in history. Information/success messages expire after about seven seconds, failures after twelve; hover/focus pauses expiry. Dismissal does not delete history. Existing history is not replayed as popups when the page opens.

Reads/writes are serialized with atomic replacement, and the history is bounded. Revision polling avoids retransmitting unchanged entries. An unavailable history file cannot turn a successfully encoded output into a failed job; the history panel shows read errors, while ordinary action notifications can fall back to a transient local toast. ARCHIVER_NOTIFICATION_FILE is available for isolated test runs.

## Grouped success toasts and filters (version 116)

The first successful queue completion appears immediately. Further successes from the same queue update that visible toast when the actual completion-time gap is at most five seconds. A group spans at most thirty seconds, so a steady stream does not extend one toast indefinitely. Encodes and tests group separately; app actions, imports, failures, cancellations and skipped jobs are never included in a success group. A dismissed or expired toast is not revived. Grouped toasts restart their normal expiry on update, and View results opens history filtered to successes from that queue.

Grouping is presentation-only: the history file retains a separate record for every queue result, still bounded to the latest 500 entries. Failure toasts remain individual. When toast space is full, unprotected non-error cards are removed before errors; hover/focus controls are protected where space permits. At most three message cards are visible, with all recorded details available in history.

Type (all, errors, successes, information) and Source (all, both queues, encodes, tests, imports, app actions) filters combine with AND. Filtering changes neither stored records nor the unread total. Filters remain selected while the panel is closed/reopened; a page reload starts with all results. Reset filters restores the full list. A matching count and explicit no-match message distinguish filtering from empty history. Clear all history removes every saved notification, including hidden matches. The list scrolls independently so filters and footer controls remain accessible.

Validation includes time-gap/group-span boundaries, non-queue exclusion, separate encode/test groups, individual/prioritized failures, unchanged history row counts, reload behavior, combined filters, empty states, reset, clear-all under a filter, and a 100-completion burst. Both themes were checked at 1440, 850, 420 and 360 pixels.
