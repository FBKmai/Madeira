# Building for a foldable iPhone

A foldable iPhone runs an IPA that was linked against an older iOS SDK in a
**compatibility canvas**: iOS gives the app a fixed, narrower screen of its own,
scales that up onto the real display and puts a zoom button beside it. The
picture is soft, the bars are wide, and no amount of in-app layout work moves
either, because the app never sees the real screen.

The release IPA for v0.2.0 is such a build:

```
$ python3 - <<'PY' Payload/Madeira.app/Madeira      # or: vtool -show-build
...
LC_BUILD_VERSION platform=2 minos=18.0.0 sdk=26.5.0
```

A build of the same tree on today's `xcode-27` runner reports
`sdk=27.1.0`, and on the device it fills the screen at native resolution.

The runner label is not a version check: v0.2.0 was released from a runner
carrying that label with Xcode 26.5 installed, which is why the tag and the
release IPA disagree in this one respect. `build.yml` therefore fails in `plan`
when the SDK is older than 27.0, before anything is compiled, rather than
shipping another scaled build after a five-hour run.

## What the SDK fixes

- the whole interface is drawn at the display's real size, at native pixels;
- SwiftUI lays the library out again when the device is folded or unfolded,
  since the window really changes size;
- a session's virtual monitor is chosen from the screen's own shape
  (`ResolutionChoices`), so a game fills it in Fit;
- touch input maps to what is on screen, as on any other iPhone.

## Bar buttons on the trailing edge

At native size one more thing shows up: iOS draws its own status bar and deck
widgets along the **trailing edge** of a folded Duo. Taps on the library's own
cards still work there, but the two `topBarTrailing` items (Library options,
Add executable) and the floating tab bar's two icons sit under that system UI
and stop responding. Forcing the app into the left half of a split screen makes
them work again, which confirms it is the edge, not the controls.

`LibraryView` measures the **window** (not the screen), and when its narrow
side is at least 500 pt — true for a Duo in either orientation, false for a
phone — it moves the two toolbar groups to `.topBarLeading` and adds a small
Library / Settings switcher there. The system tab bar and its glass pill are
left untouched for every other device. Nothing about the game session, the
touch-control layouts or the translations changes.

If a folded cover screen is narrower than that, no rebuild is needed: put
`env.MADEIRA_LEADING_BAR = 1` in `madeira.cfg` to force the leading controls
on (or `= 0` to turn them off).

## Not included, on purpose

- the fold-aware session layout of [PR #506](https://github.com/willfaust/Madeira/pull/506)
  — the game in the upper half and a control deck on the flat half;
- any change to the touch-control layouts. The built-in layout is laid out
  from the actual canvas, so it stays inside the screen on a foldable; it is
  simply spread out, since it is a two-thumb layout for a wide window.

## Checking a build

`CURRENT_PROJECT_VERSION` is 7 here, so the developer interface's light grey
build label and the log's first `[build] v0.2.0 (7)` line tell this build from
the earlier native build's `(6)` and the release IPA's `v0.2.0 (5)`.
