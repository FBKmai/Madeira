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

## What this fixes, and what it does not

Fixed by building against the iOS 27 SDK:

- the whole interface is drawn at the display's real size, at native pixels;
- SwiftUI lays the library out again when the device is folded or unfolded,
  since the window really changes size;
- a session's virtual monitor is chosen from the screen's own shape
  (`ResolutionChoices`), so a game fills it in Fit;
- touch input maps to what is on screen, as on any other iPhone.

Not included, on purpose:

- the fold-aware session layout of [PR #506](https://github.com/willfaust/Madeira/pull/506)
  — the game in the upper half and a control deck on the flat half;
- any change to the touch-control layouts. The built-in layout is laid out
  from the actual canvas, so it stays inside the screen on a foldable; it is
  simply spread out, since it is a two-thumb layout for a wide window.

## Checking a build

`CURRENT_PROJECT_VERSION` is 6 here, so the developer interface's light grey
build label and the log's first `[build] v0.2.0 (6)` line tell this build from
the release IPA's `v0.2.0 (5)`. Nothing else claims to be either.
