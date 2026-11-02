# Test timeline markers

Version 112 applies the approved rounded-marker design. SVG connectors start at the bottom center of each preview card and terminate at the actual sample midpoint on the filmstrip. Cards retain their existing collision-avoiding rows; connectors bend when a card shifts away from its source position. No dots are drawn above the timeline.

The filmstrip retains true-position sample highlights. Separate rounded locators below it have start/end ticks and a minimum width of 24 CSS pixels so eight-second clips remain legible on multi-hour recordings. These minimum-width locators are not always to scale. Tooltips explicitly explain enlargement and provide exact start/end times and duration; the card displays duration and its timestamp range. Locators are bounded to the viewer and placed on separate rows when they would collide. The time axis moves below the final locator row.

The active card, connector, filmstrip highlight and lower locator use the shared green accent; inactive elements use theme colors. Existing playback eligibility is unchanged: only an active visible sample can animate. Skeleton previews remain in place while footage is being selected and loaded. Locators appear after actual windows are selected, rather than suggesting invented ranges during loading.

Verification covers template rendering, preservation of skeletons and exact metadata, connector/card center alignment, no upper dots, bounded locators and collision avoidance for three and twelve samples across both themes at 360, 420, 850, 1440, 1920 and 3840 pixels.
