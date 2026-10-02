# QML Storybook

Storybook opens a separate Quickshell window and renders the production `ui/Dashboard.qml`, including `ContextView`, `ContextLane`, and `ContextCard`. Its events are fictional. It does not read `~/.codex`, lock the desktop, start PAM, or change Omarchy configuration. The gallery controls currently follow the Russian labels used by the installed interface.

From the repository root:

```bash
qs -p storybook.qml
```

The sidebar selects a scenario, an 820/1360/1680 px viewport, a light or dark test palette, and a screensaver or locked-screen preview. The password overlay is only a mockup; it has no input field. Playback controls provide play/pause, one event at a time, reset, page navigation, and three event rates. Pausing stops new events and drift. A single step applies one event with the real push animation, lets it drift briefly, then pauses again. Reusing an event ID updates its card instead of adding a duplicate.

Scenarios cover scanning, a confirmed empty set, 1/2/3/4/7 chats, a question awaiting a reply, an unknown source, loss of connection, a failed command, completion, and a burst of new cards. The light and dark palettes are synthetic test variants; the installed plugin uses the selected Omarchy theme.

## Reproducible checks

```bash
python3 check_storybook.py --out /tmp/endless-session-storybook-check
```

The command runs the gallery in an isolated temporary HOME and saves synthetic PNG frames plus `report.json`. It checks state and pagination; it does not replace a visual review of motion or a real lock/password test. For a single frame, the gallery accepts `OC_STORYBOOK_STORY`, `OC_STORYBOOK_THEME=light`, `OC_STORYBOOK_WIDTH=820|1360|1680`, `OC_STORYBOOK_MODE=locked`, `OC_STORYBOOK_STEPS`, `OC_STORYBOOK_PAGE`, `OC_STORYBOOK_PASSWORD=1`, and `OC_STORYBOOK_CAPTURE=<absolute-path.png>`.

## Rebuild the README animation

The animated promo uses the same `Dashboard` with a separate synthetic sequence. For GIF generation, the renderer copies the QML components into a temporary directory and translates display strings into English. It does not change the installed interface. Capture runs in an isolated HOME at 20 fps for 210 frames without reading Codex or locking the system:

```bash
python3 render_promo.py --out assets/endless-session-demo.gif
```

`ffmpeg` is required. The GIF's “Screen locked” state is a visual preview; no actual session lock or PAM authentication runs during capture.
