#!/usr/bin/env python3
"""Exercise the production touch-control layout store without an iOS SDK.

Part A compiles the Foundation-only blocks (ControlAction/TouchControl from
ContentView.swift, the pure touch state from TouchGamepad.swift and the pure
preset state from TouchControlPresets.swift) on the host: the built-in
controller layout on phone and tablet screens, built-ins read-only, "Custom
Layout N" naming, encode/decode and what loading a layout puts on screen.
Where SwiftUI is available, it also checks the production canvas hit shape.

The preset is checked as data: its name, id and its 18 bindings, each an XInput
mapping that produces a non-neutral pad sample; and the key sticks' glyphs.

Part B checks the UI wiring in the same files: kill switches, the write-back
on the end of an edit, the default for new users only, and the session slot.
Set SWIFTC if Swift is not on PATH.
"""
from pathlib import Path
import argparse
import os
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--wiring-only', action='store_true',
                    help='check source wiring only; explicitly skip Swift compilation/runtime tests')
args = parser.parse_args()

root = Path(__file__).resolve().parents[2]
app = root / 'app/Madeira'
content = (app / 'ContentView.swift').read_text(encoding='utf-8')
touch = (app / 'TouchGamepad.swift').read_text(encoding='utf-8')
presets = (app / 'TouchControlPresets.swift').read_text(encoding='utf-8')

# ---------------------------------------------------------------- Part A
actions = content[content.index('enum ControlAction: Codable'):content.index('final class TouchControlsModel')]
pure_touch = touch.split('// MARK: - Pure touch state', 1)[1].split('// MARK: - UIKit touch lifetime', 1)[0]
pure_touch = pure_touch[pure_touch.index('struct GamepadSample'):]
pure = presets.split('// MARK: - Pure preset state', 1)[1].split('// MARK: - Persistence', 1)[0]
pure = pure[pure.index('struct ControlPreset'):]
for block in (actions, pure):
    assert 'SwiftUI' not in block and 'UIKit' not in block, 'the layout core stays Foundation-only'

tests = r'''
var failures = 0
func require(_ condition: @autoclosure () -> Bool, _ label: String) {
    if condition() { print("PASS: " + label) } else { print("FAIL: " + label); failures += 1 }
}

let screens: [(String, ControlPresetScreen)] = [
    ("6.3in phone", ControlPresetScreen(width: 874, height: 402, left: 59, right: 59, top: 0, bottom: 21)),
    ("6.1in phone", ControlPresetScreen(width: 844, height: 390, left: 47, right: 47, top: 0, bottom: 21)),
    ("6.9in phone", ControlPresetScreen(width: 956, height: 440, left: 62, right: 62, top: 0, bottom: 21)),
    ("4.7in phone", ControlPresetScreen(width: 667, height: 375)),
    ("insets unreported", ControlPresetScreen(width: 874, height: 402)),
    ("11in tablet", ControlPresetScreen(width: 1194, height: 834, top: 24, bottom: 20)),
    ("13in tablet", ControlPresetScreen(width: 1366, height: 1024, top: 24, bottom: 20)),
    ("mini tablet", ControlPresetScreen(width: 1133, height: 744, top: 24, bottom: 20)),
    ("phone, portrait", ControlPresetScreen(width: 402, height: 874, left: 0, right: 0, top: 62, bottom: 34)),
]
let expected = ["LS", "RS", "D↑", "D↓", "D←", "D→", "A", "B", "X", "Y",
                "LB", "RB", "LT", "RT", "View", "Menu", "L3", "R3"]
func find(_ cs: [TouchControl], _ name: String) -> TouchControl { cs.first { $0.action == .pad(name) }! }

// --- Built-in controller layout: complete, mapped, on screen, non-overlapping.
for (label, screen) in screens {
    let s = screen.landscape
    let cs = ControlPresetLayout.xbox(for: screen)
    let names = cs.compactMap { $0.action.padName }
    require(cs.count == expected.count && expected.allSatisfy { n in names.filter { $0 == n }.count == 1 },
            "\(label): sticks, D-pad, ABXY, bumpers, triggers, View/Menu, L3/R3 once each")
    require(names.allSatisfy(TouchPadAction.supported), "\(label): every control is a supported XInput mapping")
    require(cs.allSatisfy { $0.scale >= 0.5 && $0.scale <= 3.0 }, "\(label): scales inside the pinch clamp")
    require(cs.allSatisfy { $0.nx >= 0.03 && $0.nx <= 0.97 && $0.ny >= 0.03 && $0.ny <= 0.97 },
            "\(label): positions inside the editor's drag clamp")
    let m = ControlPresetLayout.margins(s)
    let safe = CGRect(x: m.left, y: m.top, width: s.width - m.left - m.right, height: s.height - m.top - m.bottom)
    let boxes = cs.map { ControlPresetLayout.box($0, screen: s) }
    require(boxes.allSatisfy { safe.contains($0) }, "\(label): every control inside the safe area")
    var overlaps: [String] = []
    for i in cs.indices { for j in cs.indices where j > i {
        let a = boxes[i], b = boxes[j]
        // Round controls (a square box) are compared as circles, so the face
        // diamond's diagonal neighbours may share box corners; anything else
        // (wide shoulders, Start/Select pills) as its drawn box. 2 pt gap.
        let dx = a.midX - b.midX, dy = a.midY - b.midY
        let round = abs(a.width - a.height) < 1e-9 && abs(b.width - b.height) < 1e-9
        if round ? (dx * dx + dy * dy).squareRoot() < a.width / 2 + b.width / 2 + 2
                 : a.insetBy(dx: -1, dy: -1).intersects(b) {
            overlaps.append("\(cs[i].action.label)/\(cs[j].action.label)")
        }
    } }
    require(overlaps.isEmpty, "\(label): no two controls overlap \(overlaps)")
    let bar = ControlPresetLayout.topBarRect(s)
    require(!boxes.contains { $0.intersects(bar) }, "\(label): the overlay's top buttons stay free")
    let l = find(cs, "LS"), r = find(cs, "RS"), up = find(cs, "D↑"), down = find(cs, "D↓")
    let left = find(cs, "D←"), right = find(cs, "D→")
    let a = find(cs, "A"), b = find(cs, "B"), x = find(cs, "X"), y = find(cs, "Y")
    let lt = find(cs, "LT"), lb = find(cs, "LB"), rt = find(cs, "RT"), rb = find(cs, "RB")
    let view = find(cs, "View"), menu = find(cs, "Menu")
    require(l.nx < 0.3 && l.ny > 0.6 && r.nx > 0.7 && r.ny > 0.6, "\(label): sticks in the bottom corners")
    require(down.ny < l.ny && up.ny < down.ny && left.nx < up.nx && up.nx < right.nx && abs(up.nx - down.nx) < 1e-9,
            "\(label): D-pad cross above the left stick")
    require(y.ny < x.ny && x.ny == b.ny && b.ny < a.ny && x.nx < y.nx && y.nx < b.nx && abs(y.nx - a.nx) < 1e-9
            && a.ny < r.ny && a.nx > 0.5, "\(label): Y top, X left, B right, A bottom, above the right stick")
    require(lt.ny < 0.2 && abs(lt.nx - lb.nx) < 1e-9 && lt.ny < lb.ny && lb.nx < 0.5
            && abs(rt.nx - rb.nx) < 1e-9 && rt.ny < rb.ny && rb.nx > 0.5,
            "\(label): shoulder columns in the top corners, triggers above bumpers")
    require(view.nx < 0.5 && menu.nx > 0.5 && abs(view.ny - menu.ny) < 1e-9, "\(label): View left of Menu, centre")
}
let ids = Set(ControlPresetLayout.xbox(for: .referencePhone).map { $0.id })
require(ids.count == expected.count, "built-in controls have distinct ids")

// --- The short-edge grip keeps the centre clear and works with real canvas shapes.
let shortScreens: [(String, ControlPresetScreen)] = screens + [
    ("unfolded wide", ControlPresetScreen(width: 1800, height: 700, left: 84, right: 52, bottom: 21)),
    ("folded landscape", ControlPresetScreen(width: 874, height: 402, left: 59, right: 59, bottom: 21)),
    ("compact landscape", ControlPresetScreen(width: 600, height: 390, left: 16, right: 20, bottom: 12)),
    ("small landscape", ControlPresetScreen(width: 568, height: 320)),
    ("short landscape", ControlPresetScreen(width: 600, height: 360)),
    ("narrow portrait", ControlPresetScreen(width: 320, height: 568)),
    ("near-square unfolded", ControlPresetScreen(width: 720, height: 700, left: 32, right: 48, top: 44, bottom: 34)),
    ("square unfolded", ControlPresetScreen(width: 720, height: 720, top: 44, bottom: 34)),
    ("portrait session", ControlPresetScreen(width: 402, height: 874, top: 62, bottom: 34)),
    ("asymmetric safe area", ControlPresetScreen(width: 1366, height: 720, left: 84, right: 52, bottom: 21)),
]
let shortExpected = expected
for (label, screen) in shortScreens {
    let cs = ControlPresetLayout.shortEdge(for: screen)
    let names = cs.compactMap { $0.action.padName }
    require(cs.count == shortExpected.count && shortExpected.allSatisfy { n in names.filter { $0 == n }.count == 1 },
            "\(label): short-edge grip binds all controller inputs once")
    require(names.allSatisfy(TouchPadAction.supported), "\(label): short-edge mappings are XInput")
    let left = max(ControlPresetLayout.margins(screen).left, screen.width * 0.03)
    let right = max(ControlPresetLayout.margins(screen).right, screen.width * 0.03)
    let top = max(ControlPresetLayout.margins(screen).top, screen.height * 0.03)
    let bottom = max(ControlPresetLayout.margins(screen).bottom, screen.height * 0.03)
    let safe = CGRect(x: left, y: top, width: screen.width - left - right,
                      height: screen.height - top - bottom)
    let boxes = cs.map { ControlPresetLayout.box($0, screen: screen) }
    require(boxes.allSatisfy { safe.contains($0) }, "\(label): controls stay inside safe and drag bounds")
    var overlaps: [String] = []
    for i in cs.indices { for j in cs.indices where j > i {
        let a = boxes[i], b = boxes[j]
        let dx = a.midX - b.midX, dy = a.midY - b.midY
        let round = abs(a.width - a.height) < 1e-9 && abs(b.width - b.height) < 1e-9
        if round ? (dx * dx + dy * dy).squareRoot() < a.width / 2 + b.width / 2 + 2
                 : a.insetBy(dx: -1, dy: -1).intersects(b) {
            overlaps.append("\(cs[i].action.label)/\(cs[j].action.label)")
        }
    } }
    require(overlaps.isEmpty, "\(label): short-edge controls do not overlap \(overlaps)")
    require(!boxes.contains { $0.intersects(ControlPresetLayout.topBarRect(screen)) },
            "\(label): short-edge grip leaves the top menu band free")
    let ls = find(cs, "LS"), rs = find(cs, "RS")
    require(ls.nx < 0.35 && rs.nx > 0.65 && abs(ls.ny - rs.ny) < 1e-9,
            "\(label): thumb sticks stay near the two short edges")
}
require(ControlPresetLayout.shortEdge(for: .referencePhone).map { $0.action } ==
        ControlPresetLayout.shortEdge(for: ControlPresetScreen(width: 874, height: 402, left: 59, right: 59, bottom: 21)).map { $0.action },
        "short-edge mapping order is stable across safe-area snapshots")

// The session-wide size multiplier is applied by the actual drawing and hit
// testing AFTER per-control fitting. Check those physical sizes, not only the
// normal-size layout, including requests that must be capped on a small canvas.
func placementIssues(_ cs: [TouchControl], screen s: ControlPresetScreen, sizeScale: Double) -> [String] {
    let m = ControlPresetLayout.margins(s)
    let safe = CGRect(x: m.left, y: m.top, width: s.width - m.left - m.right,
                      height: s.height - m.top - m.bottom)
    let boxes = cs.map { ControlPresetLayout.box($0, screen: s, sizeScale: sizeScale) }
    var issues: [String] = []
    if !boxes.allSatisfy({ safe.contains($0) }) { issues.append("safe area") }
    if boxes.contains(where: { $0.intersects(ControlPresetLayout.topBarRect(s)) }) { issues.append("menu") }
    for i in boxes.indices { for j in boxes.indices where j > i {
        let a = boxes[i], b = boxes[j]
        let round = abs(a.width - a.height) < 0.001 && abs(b.width - b.height) < 0.001
        let dx = a.midX - b.midX, dy = a.midY - b.midY
        if round ? (dx * dx + dy * dy).squareRoot() < a.width / 2 + b.width / 2 + 2 - 1e-7
                 : a.insetBy(dx: -1, dy: -1).intersects(b) {
            issues.append("\(cs[i].action.label)/\(cs[j].action.label)")
        }
    } }
    return issues
}
for (label, s) in shortScreens {
    let limit = ControlPresetLayout.sizeLimit(for: ControlPresetLayout.shortEdgeID, screen: s)
    require(limit >= 1 && limit <= 2, "\(label): short-edge size limit is usable")
    for requested in [0.5, 0.75, 1, 1.2, 1.5, 2] {
        let q = min(requested, limit)
        let cs = ControlPresetStore.layout(of: ControlPresetStore.builtIns[1], screen: s, sizeScale: q)
        let issues = placementIssues(cs, screen: s, sizeScale: q)
        require(cs.count == 18 && issues.isEmpty,
                "\(label): size \(requested) (effective \(q)) fits \(issues)")
        require(cs.allSatisfy { $0.scale >= 0.5 && $0.scale <= 3 && $0.nx >= 0.03 && $0.nx <= 0.97
                               && $0.ny >= 0.03 && $0.ny <= 0.97 },
                "\(label): sized controls survive the editor clamps unchanged")
        require(ControlPresetStore.reflow(id: ControlPresetLayout.shortEdgeID, controls: cs,
                                         screen: s, editing: false, sizeScale: q) == nil,
                "\(label): reflow at size \(q) is idempotent")
    }
}
for (label, screen) in screens {
    let s = screen.landscape
    let cs = ControlPresetLayout.xbox(for: s)
    let limit = ControlPresetLayout.sizeLimit(for: ControlPresetLayout.xboxID, screen: screen)
    require(limit >= 0.5 && limit <= 2 && placementIssues(cs, screen: s, sizeScale: limit).isEmpty,
            "\(label): Xbox's overall size also cannot grow into its neighbours")
}

// --- The built-in controller presets as data: what a user is offered and what each button does.
let builtIn = ControlPresetStore.builtIns
require(builtIn.count == 2 && builtIn[0].id == ControlPresetLayout.xboxID
        && builtIn[1].id == ControlPresetLayout.shortEdgeID
        && builtIn[0].name == "Xbox controller" && builtIn[1].name == "Short-edge grip",
        "Xbox controller and Short-edge grip are listed as built-ins")
require(builtIn.allSatisfy { $0.controls.count == 18 && Set($0.controls.compactMap { $0.action.padName }) == Set(expected) },
        "each built-in binds the 18 controller inputs, none twice")
require(builtIn.flatMap(\.controls).allSatisfy { c in
            guard let n = c.action.padName else { return false }
            return TouchPadAction.sample(n, x: 1, y: 1) != GamepadSample()
        }, "every built-in binding produces a non-neutral XInput sample when pressed or deflected")
require(ControlPresetStore().preset(ControlPresetLayout.xboxID)?.name == "Xbox controller"
        && ControlPresetStore().preset(ControlPresetLayout.shortEdgeID)?.name == "Short-edge grip"
        && ControlPresetStore(user: []).all.first?.id == ControlPresetLayout.xboxID,
        "a store with no user layouts offers both built-ins first")
let one = ControlPresetStore(user: [ControlPreset(id: "u", name: "Mine", controls: [])])
require(one.resolvedID(ControlPresetLayout.xboxID) == ControlPresetLayout.xboxID && one.resolvedID("u") == "u",
        "a game's remembered built-in or custom layout resolves")
require(one.resolvedID("gone") == nil && one.resolvedID(nil) == nil, "a deleted or absent layout resolves to none")
require(ControlPresetStore.restoredID(ControlPresetLayout.xboxID, adaptive: nil) == nil
        && ControlPresetStore.restoredID(ControlPresetLayout.shortEdgeID, adaptive: false) == nil,
        "legacy or untrusted built-in IDs preserve their controls as unsaved, not auto-reflowed")
require(ControlPresetStore.restoredID(ControlPresetLayout.shortEdgeID, adaptive: true) == ControlPresetLayout.shortEdgeID
        && ControlPresetStore.restoredID("u", adaptive: nil) == "u"
        && ControlPresetStore.restoredID(nil, adaptive: true) == nil,
        "tracked built-ins reflow, custom and absent IDs keep their original meaning")

// --- The key sticks carry a glyph that tells them apart; nothing else does.
require(ControlAction.joystickWASD.stickGlyph == "keyboard", "the WASD stick's glyph is the keyboard")
require(ControlAction.joystickArrows.stickGlyph == "arrow.up.and.down.and.arrow.left.and.right",
        "the arrow-key stick's glyph is the arrows")
require(ControlAction.joystickWASD.stickGlyph != ControlAction.joystickArrows.stickGlyph, "WASD and Arrows differ")
let plain: [ControlAction] = [.none, .mouseLeft, .mouseRight, .keyboardToggle, .key(0x20), .pad("LS"), .pad("RS"), .pad("A")]
require(plain.allSatisfy { $0.stickGlyph == nil }, "no other control (nor the controller sticks) has a stick glyph")
require(ControlAction.joystickWASD.stickKeys == [0x57, 0x44, 0x53, 0x41]
        && ControlAction.joystickArrows.stickKeys == [0x26, 0x27, 0x28, 0x25], "the glyph does not change the keys a stick posts")

// --- Encode / decode round trip.
var store = ControlPresetStore()
var custom = TouchControl()
custom.nx = 0.2; custom.ny = 0.7; custom.scale = 1.4; custom.action = .key(0x20)
var stick = TouchControl(); stick.action = .pad("LS")
let layout = [custom, stick] + ControlPresetLayout.xbox(for: .referencePhone)
var n = 0
let fixedID: () -> String = { n += 1; return "user-\(n)" }
require(store.save(name: "  Racing  ", controls: layout, newID: fixedID) == .created("user-1"), "save creates")
require(store.save(name: "Shooter", controls: [custom], newID: fixedID) == .created("user-2"), "second layout")
require(store.preset("user-1")?.name == "Racing", "names are trimmed")
let data = try! store.encoded()
let back = try! ControlPresetStore.decoded(data)
require(back == store && back.user.count == 2, "user layouts round-trip through JSON")
require(back.preset("user-1")?.controls == layout, "keyboard and controller actions survive")
let text = String(decoding: data, as: UTF8.self)
require(!text.contains(ControlPresetLayout.xboxID), "built-ins are never written to the file")
let future = #"{"version":2,"presets":[]}"#
require((try? ControlPresetStore.decoded(Data(future.utf8))) == nil, "a newer file version is refused, not misread")
let smuggled = try! ControlPresetStore.decoded(Data(#"{"version":1,"presets":[{"id":"builtin.xbox","name":"X","controls":[]}]}"#.utf8))
require(smuggled.user.isEmpty && smuggled.preset(ControlPresetLayout.xboxID)?.controls.count == expected.count,
        "a file entry cannot shadow a built-in")
let saved = #"{"version":1,"presets":[{"id":"p","name":"Old","controls":[{"id":"6F1B5E2A-1C1D-4B7E-9C84-0A0B0C0D0E0F","nx":0.5,"ny":0.5,"scale":1,"action":{"pad":{"_0":"A"}}}]}]}"#
require((try? ControlPresetStore.decoded(Data(saved.utf8)))?.preset("p")?.controls.first?.action == .pad("A"),
        "a stored controller mapping decodes by name")

// --- Built-ins are read-only; naming.
let xbox = ControlPresetLayout.xboxID
require(ControlPresetStore.isBuiltIn(xbox) && store.all.first?.id == xbox, "the controller layout is built in and listed first")
require(!store.delete(id: xbox) && !store.overwrite(id: xbox, controls: []), "built-in not deletable or writable")
require(store.save(name: "xbox CONTROLLER ", controls: [], newID: fixedID) == .refusedBuiltIn, "a built-in's name is refused")
require(store.save(name: "   ", controls: [], newID: fixedID) == .refusedEmpty, "an empty name is refused")
require(store.save(name: "racing", controls: [custom], newID: fixedID) == .replaced("user-1")
        && store.preset("user-1")?.controls == [custom], "saving under a user layout's name replaces it")
require(store.overwrite(id: "user-2", controls: layout) && store.preset("user-2")?.controls == layout, "overwrite a user layout")
require(store.nextCustomName() == "Custom Layout 1", "first custom name")
_ = store.save(name: "Custom Layout 1", controls: [], newID: fixedID)
_ = store.save(name: "custom layout 3", controls: [], newID: fixedID)
require(store.nextCustomName() == "Custom Layout 2", "the lowest free number, case-insensitive")
_ = store.save(name: "Custom Layout 2", controls: [], newID: fixedID)
require(store.nextCustomName() == "Custom Layout 4", "numbers already taken are skipped")
require(store.delete(id: "user-2") && store.preset("user-2") == nil && !store.delete(id: "user-2"), "delete once")
require(ControlPresetStore.clean(String(repeating: "x", count: 99)).count == ControlPresetStore.maxNameLength, "names are capped")

// --- What loading puts on screen.
var wild = TouchControl(); wild.nx = -1; wild.ny = 5; wild.scale = 9; wild.action = .pad("A")
let loaded = ControlPresetStore.layout(of: ControlPreset(id: "w", name: "W", controls: [wild, wild]), screen: nil)
require(loaded.count == 2 && loaded[0].id != loaded[1].id && loaded[0].id != wild.id, "fresh ids on every load")
require(loaded[0].nx == 0.03 && loaded[0].ny == 0.97 && loaded[0].scale == 3.0, "positions and scale clamped")
let tablet = ControlPresetScreen(width: 1194, height: 834, top: 24, bottom: 20)
let fitted = ControlPresetStore.layout(of: ControlPresetStore.builtIns[0], screen: tablet)
require(fitted.map { $0.action } == ControlPresetLayout.xbox(for: tablet).map { $0.action }
        && fitted.map { $0.scale } == ControlPresetLayout.xbox(for: tablet).map { $0.scale },
        "the Xbox built-in is laid out again for the screen it is loaded on")
let fittedShort = ControlPresetStore.layout(of: ControlPresetStore.builtIns[1], screen: tablet)
require(fittedShort.map { $0.action } == ControlPresetLayout.shortEdge(for: tablet).map { $0.action }
        && fittedShort.map { $0.scale } == ControlPresetLayout.shortEdge(for: tablet).map { $0.scale },
        "the short-edge built-in is laid out again for the screen it is loaded on")
let gripID = ControlPresetLayout.shortEdgeID
let oldGrip = ControlPresetStore.builtIns[1].controls
let reflowed = ControlPresetStore.reflow(id: gripID, controls: oldGrip, screen: tablet, editing: false)!
require(reflowed.map { $0.action } == fittedShort.map { $0.action }
        && reflowed.map { $0.nx } == fittedShort.map { $0.nx },
        "a saved built-in copy reflows for this canvas even when its layout ID is unchanged")
require(Set(reflowed.map(\.id)).isDisjoint(with: Set(oldGrip.map(\.id))),
        "a reflow invalidates every old control ID")
require(ControlPresetStore.reflow(id: gripID, controls: reflowed, screen: tablet, editing: false) == nil,
        "the same geometry is a no-op, preventing observation loops and disk rewrites")
let smallCanvas = ControlPresetScreen(width: 250, height: 180)
require(ControlPresetLayout.shortEdge(for: smallCanvas).isEmpty
        && ControlPresetStore.layout(of: ControlPresetStore.builtIns[1], screen: smallCanvas).isEmpty,
        "an undersized canvas does not silently fall back to a reference-phone layout")
require(ControlPresetStore.reflow(id: gripID, controls: reflowed, screen: smallCanvas, editing: false) == nil,
        "an undersized reflow retains IDs; the UI blocks input instead of disconnecting the controller")
require(!ControlPresetLayout.fits(ControlPresetLayout.xbox(for: smallCanvas), screen: smallCanvas, sizeScale: 0.5)
        && ControlPresetStore.layout(of: ControlPresetStore.builtIns[0], screen: smallCanvas, sizeScale: 0.5).isEmpty,
        "the minimum slider size does not claim that a tiny window can fit the Xbox layout")
require(ControlPresetStore.reflow(id: ControlPresetLayout.xboxID, controls: fitted,
                                 screen: smallCanvas, editing: false, sizeScale: 0.5) == nil,
        "a tiny Xbox reflow also preserves the current IDs instead of generating overlapping controls")
let enlarged = ControlPresetStore.reflow(id: gripID, controls: oldGrip, screen: tablet, editing: false,
                                        sizeScale: min(1.5, ControlPresetLayout.sizeLimit(for: gripID, screen: tablet)))!
require(enlarged.map { $0.nx } != reflowed.map { $0.nx },
        "changing overall size repositions both thumb clusters, not only their drawing size")
require(ControlPresetStore.reflow(id: nil, controls: oldGrip, screen: tablet, editing: false) == nil
        && ControlPresetStore.reflow(id: "user", controls: oldGrip, screen: tablet, editing: false) == nil
        && ControlPresetStore.reflow(id: gripID, controls: oldGrip, screen: tablet, editing: true) == nil,
        "unsaved, custom and in-progress layouts never reflow")
var insetOnly = tablet; insetOnly.left = 80; insetOnly.right = 48
require(ControlPresetStore.reflow(id: gripID, controls: reflowed, screen: insetOnly, editing: false) != nil,
        "a safe-area-only change reflows the built-in")
for invalid in [ControlPresetScreen(width: 0, height: 0),
                ControlPresetScreen(width: .nan, height: 400),
                ControlPresetScreen(width: 800, height: 400, left: .infinity),
                ControlPresetScreen(width: 400, height: 100, top: 100)] {
    require(ControlPresetStore.reflow(id: gripID, controls: oldGrip, screen: invalid, editing: false) == nil,
            "transient or invalid geometry does not replace a layout")
}
let portraitGrip = ControlPresetScreen(width: 402, height: 874, top: 62, bottom: 34)
require(ControlPresetStore.reflow(id: gripID, controls: oldGrip, screen: portraitGrip, editing: false) != nil,
        "short-edge grip follows the actual portrait session canvas")
require(ControlPresetStore.reflow(id: ControlPresetLayout.xboxID, controls: fitted,
                                 screen: portraitGrip, editing: false) == nil,
        "portrait does not silently reinterpret the legacy landscape Xbox layout")
var held = TouchGamepadState()
held.configure(Set(oldGrip.map(\.id)))
let oldA = find(oldGrip, "A"), newA = find(reflowed, "A"), finger = UUID()
held.update(owner: finger, control: oldA.id, value: TouchPadAction.sample("A", x: 0, y: 0))
require(held.connected && held.sample.buttons != 0, "pre-resize button is held")
held.configure(Set(reflowed.map(\.id)))
require(held.connected && held.sample == GamepadSample(),
        "reflow releases held input without disconnecting the controller")
held.update(owner: finger, control: oldA.id, value: TouchPadAction.sample("A", x: 0, y: 0))
require(held.sample == GamepadSample(), "a delayed pre-resize finger cannot revive the old press")
held.update(owner: UUID(), control: newA.id, value: TouchPadAction.sample("A", x: 0, y: 0))
require(held.sample.buttons != 0, "a fresh post-resize press still works")

// --- Gesture zones ride with a layout and survive the file.
var zs = ControlPresetStore()
var zone = GestureZone(); zone.kind = .swipe; zone.x = 0.9; zone.w = 0.5
guard case .created(let zid) = zs.save(name: "Zoned", controls: [], zones: [zone]) else { fatalError() }
let reread = try! ControlPresetStore.decoded(try! zs.encoded())
let loadedZones = ControlPresetStore.zones(of: reread.preset(zid)!)
require(loadedZones.count == 1 && loadedZones[0].kind == .swipe, "a layout's zones survive saving and loading")
require(loadedZones[0].id != zone.id, "loaded zones get fresh ids")
require(loadedZones[0].x + loadedZones[0].w <= 1, "a loaded zone stays on screen")
let old = try! JSONDecoder().decode(ControlPreset.self, from: Data(#"{"id":"a","name":"Old","controls":[]}"#.utf8))
require(old.zones == nil && ControlPresetStore.zones(of: old).isEmpty, "layouts saved before zones still load")

__EDITOR_SIZE_TESTS__

if failures > 0 { print("\(failures) FAILED"); exit(1) }
print("PASS: built-in controller layout, layout store, naming and loading")
'''

# Compile the production editor callbacks against small state fixtures.
def function(source, start):
    i = source.index(start); b = source.index('{', i); depth = 1; k = b + 1
    while depth:
        depth += (source[k] == '{') - (source[k] == '}'); k += 1
    return source[i:k]


panel = content[content.index('struct MappingPanel: View {'):]
setter = panel.split('set: { value in', 1)[1].split('}), in:', 1)[0]
backdrop = content.split('Color.clear.contentShape(editorCanvas(geo.size))', 1)[1]
dismiss = function(backdrop, '.onTapGesture {').split('{', 1)[1][:-1]
sizes = '\n'.join(function(content, signature) for signature in ('static func diameter(', 'static func size('))
lifecycle = '\n'.join(function(content, signature) for signature in (
    'func preserveEditedBuiltIn(', 'func setControlsForGeometry(', 'func hitsInteractive('))
saved = function(content, 'private struct Saved: Codable').replace('private struct', 'struct', 1)
canvas = function(content, 'private func editorCanvas(')
controls_property = function(content, '@Published var controls: [TouchControl] = []').replace('@Published ', '', 1)
reflow_callback = function(presets, 'func reflowBuiltIn(screen: ControlPresetScreen)')
editor_tests = r'''
final class EditorControls {
    static let shared = EditorControls()
    static let baseDiameter: CGFloat = 64
    var sizeScale = 1.0
    var selected: UUID? = UUID()
    var editing = true
    var loading = false
    var visible = true
    var fitsCanvas = true
    var hapticsEnabled = true
    var layoutID: String?
    var editBaseline: [TouchControl] = []
    var editZoneBaseline: [GestureZone] = []
    var saves = 0
    var savedLayouts: [String?] = []
    func save() {
        if !loading { saves += 1; savedLayouts.append(layoutID) }
    }
    func index(of id: UUID?) -> Int? { controls.firstIndex { $0.id == id } }
''' + '\n'.join((controls_property, sizes, lifecycle, saved)) + r'''
}
final class EditorZones {
    static let shared = EditorZones()
    static var enabled = true
    var selected: UUID? = UUID()
    var zones: [GestureZone] = []
    func contains(_ p: CGPoint, in bounds: CGRect) -> Bool {
        Self.enabled && zones.contains { $0.contains(p, in: bounds.size) }
    }
}
enum TouchControlsOverlay {
    static func showsLayoutMenu(_ m: EditorControls) -> Bool { !m.editing && m.visible }
}
typealias TouchControlsModel = EditorControls
typealias GestureZonesModel = EditorZones
func setSize(_ control: TouchControl, _ value: Double, _ m: EditorControls) {
''' + setter + r'''
}
func dismissPanel(_ m: EditorControls, _ zones: EditorZones) {
''' + dismiss + r'''
}
let editor = EditorControls()
var first = TouchControl(), second = TouchControl()
editor.controls = [first, second]
editor.layoutID = ControlPresetLayout.xboxID
editor.editBaseline = editor.controls
editor.savedLayouts.removeAll()
// The editor writes positions on every touch, including a zero-distance tap.
editor.controls[0].nx = editor.controls[0].nx
require(editor.layoutID == ControlPresetLayout.xboxID,
        "a tap that writes equal positions keeps a built-in source")
editor.savedLayouts.removeAll()
editor.controls[0].nx = 0.44
require(editor.layoutID == nil && !editor.savedLayouts.isEmpty && editor.savedLayouts.allSatisfy { $0 == nil },
        "the first control edit clears a built-in source before saving")
editor.layoutID = ControlPresetLayout.xboxID
editor.editBaseline = editor.controls
EditorZones.shared.zones = []
editor.editZoneBaseline = []
editor.preserveEditedBuiltIn()
require(editor.layoutID == ControlPresetLayout.xboxID, "zone bookkeeping without an edit keeps a built-in source")
EditorZones.shared.zones.append(GestureZone())
editor.preserveEditedBuiltIn()
require(editor.layoutID == nil, "an actual gesture-zone edit clears a built-in source")
EditorZones.shared.zones = []
editor.layoutID = ControlPresetLayout.xboxID
let savedCount = editor.savedLayouts.count
editor.setControlsForGeometry([first, second])
require(editor.layoutID == ControlPresetLayout.xboxID && editor.savedLayouts.count == savedCount,
        "geometry-derived controls do not clear provenance or write a save")
setSize(first, 3.0, editor)
require(editor.controls[0].scale == 3 && editor.controls[1].scale == 1, "size slider changes only its selected control")
editor.controls[0].locked = true
setSize(first, 0.5, editor)
require(editor.controls[0].scale == 3, "size slider honours the current lock even with an older view value")
setSize(TouchControl(), 0.5, editor)
require(editor.controls.count == 2 && editor.controls[0].scale == 3, "a removed slider target is ignored")
editor.controls[0].locked = nil
setSize(first, 0.5, editor)
let resized = try! JSONDecoder().decode([TouchControl].self, from: JSONEncoder().encode(editor.controls))
require(resized[0].scale == 0.5 && resized[1].scale == 1, "slider sizes survive the controls file format")
let editorZones = EditorZones(), beforeDismiss = editor.controls
dismissPanel(editor, editorZones)
require(editor.selected == nil && editorZones.selected == nil && editor.editing,
        "an outside tap dismisses either panel and keeps edit mode")
require(editor.controls == beforeDismiss, "dismissing the panel preserves control edits")
#if canImport(SwiftUI)
let m = editor, zones = editorZones
''' + canvas + r'''
let canvasScreen = CGSize(width: 800, height: 400)
var canvasControl = TouchControl()
editor.controls = [canvasControl]
var canvasZone = GestureZone(); canvasZone.x = 0.4; canvasZone.w = 0.4
editorZones.zones = [canvasZone]
let area = editorCanvas(canvasScreen)
require(!area.contains(CGPoint(x: 400, y: 200)), "a control overlapping a zone is excluded from canvas taps")
require(!area.contains(CGPoint(x: 600, y: 300)), "zone taps stay with the zone editor")
require(area.contains(CGPoint(x: 720, y: 380)), "empty space takes dismissal taps")
EditorZones.enabled = false
require(editorCanvas(canvasScreen).contains(CGPoint(x: 600, y: 300)), "disabled zones do not block dismissal")
EditorZones.enabled = true; editorZones.zones = []
require(editorCanvas(canvasScreen).contains(CGPoint(x: 490, y: 200)), "canvas starts beyond a normal-size control")
editor.controls[0].scale = 3
require(!editorCanvas(canvasScreen).contains(CGPoint(x: 490, y: 200)), "the tap exclusion follows a resized control")
editor.controls[0].action = .pad("RT"); editor.controls[0].scale = 1
require(!editorCanvas(canvasScreen).contains(CGPoint(x: 445, y: 200)), "wide shoulder controls keep their full touch region")
#endif
'''
adaptive_tests = r'''
// Compile the actual model reflow callback, including size caps and tiny-window
// suspension, against the same minimal controls state used above.
final class AdaptivePresets {
    static var enabled = true
''' + reflow_callback + r'''
}
let adaptive = AdaptivePresets(), live = EditorControls.shared
live.editing = false
live.controls = oldGrip
live.layoutID = gripID
live.sizeScale = 2
live.saves = 0
adaptive.reflowBuiltIn(screen: tablet)
require(live.fitsCanvas && live.sizeScale <= ControlPresetLayout.sizeLimit(for: gripID, screen: tablet)
        && placementIssues(live.controls, screen: tablet, sizeScale: live.sizeScale).isEmpty,
        "model reflow caps enlarged controls before placing them on the new canvas")
require(live.saves == 0 && live.layoutID == gripID,
        "the model reflows without disk writes or losing the built-in source")
let fittedIDs = live.controls.map(\.id)
adaptive.reflowBuiltIn(screen: smallCanvas)
require(!live.fitsCanvas && live.controls.map(\.id) == fittedIDs,
        "tiny-window suspension keeps every controller ID instead of unplugging the pad")
adaptive.reflowBuiltIn(screen: tablet)
require(live.fitsCanvas && live.controls.map(\.id) == fittedIDs,
        "returning to the previous canvas resumes the same fitted controls")
live.editing = true
adaptive.reflowBuiltIn(screen: smallCanvas)
require(live.fitsCanvas && live.controls.map(\.id) == fittedIDs,
        "the editor keeps the existing layout accessible even on a tiny canvas")
live.layoutID = "custom"
live.preserveEditedBuiltIn()
require(live.layoutID == "custom", "editing never drops a custom layout's write-back target")
live.layoutID = gripID
live.loading = true
live.setControlsForGeometry(oldGrip)
require(live.loading && live.layoutID == gripID,
        "geometry updates preserve an outer loading transaction")
live.loading = false

let legacyWorkingCopy = try! JSONDecoder().decode(EditorControls.Saved.self,
    from: Data(#"{"controls":[],"visible":true,"layout":"builtin.xbox"}"#.utf8))
require(legacyWorkingCopy.adaptiveLayout == nil && legacyWorkingCopy.haptics == nil
        && ControlPresetStore.restoredID(legacyWorkingCopy.layout, adaptive: legacyWorkingCopy.adaptiveLayout) == nil,
        "the actual working-copy schema decodes old files without trusting a built-in ID")
let trackedWorkingCopy = EditorControls.Saved(controls: oldGrip, visible: true, layout: gripID,
                                            haptics: true, adaptiveLayout: true)
let trackedRoundTrip = try! JSONDecoder().decode(EditorControls.Saved.self,
    from: JSONEncoder().encode(trackedWorkingCopy))
require(trackedRoundTrip.controls == oldGrip
        && ControlPresetStore.restoredID(trackedRoundTrip.layout, adaptive: trackedRoundTrip.adaptiveLayout) == gripID,
        "tracked working copies retain both their controls and adaptive provenance")

// The actual window hit test, not just the editor's exclusion Path: the full
// shoulder width is interactive, whereas the corners of a round button are not.
live.editing = false; live.layoutID = nil; live.visible = true; live.fitsCanvas = true; live.sizeScale = 1
EditorZones.shared.zones = []
let hitBounds = CGRect(x: 0, y: 0, width: 800, height: 400)
var shoulder = TouchControl(); shoulder.action = .pad("RT")
live.controls = [shoulder]
require(live.hitsInteractive(CGPoint(x: 448, y: 200), in: hitBounds, topBar: false),
        "the drawn outer shoulder edge does not pass a press through to the game")
require(!live.hitsInteractive(CGPoint(x: 400, y: 226), in: hitBounds, topBar: false),
        "space below the actual shoulder rectangle stays click-through")
live.sizeScale = 1.5
require(live.hitsInteractive(CGPoint(x: 470, y: 200), in: hitBounds, topBar: false),
        "the shoulder touch region follows the session-wide size multiplier")
live.sizeScale = 1; live.controls[0].action = .pad("A")
require(!live.hitsInteractive(CGPoint(x: 428, y: 228), in: hitBounds, topBar: false),
        "a round button does not steal touches from its bounding-box corners")
var hitZone = GestureZone(); hitZone.x = 0.7; hitZone.y = 0.5; hitZone.w = 0.2; hitZone.h = 0.2
EditorZones.shared.zones = [hitZone]
require(live.hitsInteractive(CGPoint(x: 640, y: 240), in: hitBounds, topBar: false),
        "gesture zones still participate in the window hit test")
live.fitsCanvas = false
require(!live.hitsInteractive(CGPoint(x: 400, y: 200), in: hitBounds, topBar: false)
        && !live.hitsInteractive(CGPoint(x: 640, y: 240), in: hitBounds, topBar: false),
        "suspended layouts pass both control and zone touches through")
require(live.hitsInteractive(CGPoint(x: 400, y: 30), in: hitBounds),
        "the top menu remains accessible while gameplay controls are suspended")
'''
tests = tests.replace('__EDITOR_SIZE_TESTS__', editor_tests + adaptive_tests)

if args.wiring_only:
    print('SKIP: Swift compilation/runtime layout tests (--wiring-only); only source wiring is checked')
else:
    with tempfile.TemporaryDirectory(prefix='madeira-presets-') as tmp:
        src, exe = Path(tmp) / 'main.swift', Path(tmp) / 'check'
        # CoreGraphics where it exists: on macOS, Foundation alone no longer gives CGRect
        # its members (midX, width, ...); Linux's Foundation still does.
        header = 'import Foundation\n#if canImport(CoreGraphics)\nimport CoreGraphics\n#endif\n#if canImport(SwiftUI)\nimport SwiftUI\n#endif\n'
        src.write_text(header + actions + pure_touch + pure + tests, encoding='utf-8')
        subprocess.run([os.environ.get('SWIFTC', 'swiftc'), str(src), '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True)

# ---------------------------------------------------------------- Part B
gamepad = (app / 'GamepadInput.swift').read_text(encoding='utf-8')
model = content[content.index('final class TouchControlsModel'):content.index('/// Click-through EXCEPT')]
zones_ui = (app / 'GestureZones.swift').read_text(encoding='utf-8')
touch_view = function(touch, 'final class TouchPadView: UIView {')
zone_view = function(zones_ui, 'final class GestureZoneView: UIView {')
assert 'name: TouchControlsHost.geometryChanged' in function(touch_view, 'init() {'), \
    'UIKit pad surfaces subscribe to geometry changes'
assert 'releaseAll(); changed?(.zero, false)' in touch_view, \
    'UIKit pad surfaces publish a neutral state when geometry changes'
assert 'name: TouchControlsHost.geometryChanged' in zone_view and 'carryX = 0; carryY = 0' in zone_view, \
    'gesture zones cancel fingers and fractional mouse motion on a geometry change'
assert 'onReceive(NotificationCenter.default.publisher(for: TouchControlsHost.geometryChanged))' in content, \
    'SwiftUI controls cancel drag input on a geometry change'
assert 'c.scale = scale * fit.scale' in function(presets, 'static func shortEdge(for'), \
    'short-edge fitting does not multiply the global size twice'
assert 'guard let fitting = ControlPresetLayout.controls(for: id, screen: screen' in presets \
    and 'm.fitsCanvas = false' in function(presets, 'func reflowBuiltIn(screen: ControlPresetScreen)'), \
    'built-in fitting suspends input rather than unplugging the pad on tiny windows'
assert 'let sizeScale = min(m.sizeScale, ControlPresetLayout.sizeLimit(for: id, screen: screen))' in presets, \
    'built-in reflow caps the session-wide size before drawing'
assert 'else if CGRect(x: cx - size.width / 2' in model and 'size = Self.size(c)' in model, \
    'window hit tests use the complete drawn rectangle for wide controls'

for flag, where in (('MADEIRA_CONTROL_PRESETS', presets), ('MADEIRA_CONTROLS_EDITOR_DONE', content)):
    assert f'.flag("{flag}")' in where, flag + ' is a kill switch'
# Defaults an existing user would notice are opt-in: the built-in is never applied
# automatically and player 1 is not reserved unless the switch is set to 1.
for flag, where in (('MADEIRA_CONTROLS_XBOX_DEFAULT', presets), ('MADEIRA_PAD_EARLY_SLOT', gamepad)):
    assert f'.optIn("{flag}")' in where and f'.flag("{flag}")' not in where, flag + ' is opt-in'
assert '!= "0"' in function(gamepad, 'static func flag('), 'only "0" disables'
assert '== "1"' in function(gamepad, 'static func optIn('), 'only "1" enables'
assert 'Self.xboxDefault' in function(presets, 'var defaultPending: Bool {'), 'the automatic built-in needs the opt-in'

model = content[content.index('final class TouchControlsModel'):content.index('/// Click-through EXCEPT')]
assert 'ControlPresetsModel.shared.editingEnded(baseline: editBaseline, zoneBaseline: editZoneBaseline)' in model
assert 'needsDefaultLayout = !FileManager.default.fileExists(atPath: Self.url.path)' in model, 'default only without a file'
assert 'var layout: String?' in model, 'older controls files still decode'
ended = function(presets, 'func editingEnded(baseline: [TouchControl], zoneBaseline: [GestureZone]) {')
assert ended.index('guard Self.enabled else { return }') < ended.index('s.overwrite(id: id'), 'write-back is switchable'
default = function(presets, 'func applyDefaultIfNeeded(screen: ControlPresetScreen) {')
assert 'm.controls.isEmpty' in default and 'm.needsDefaultLayout = false' in default, 'applied once, never over controls'
assert default.index('if load(ControlPresetLayout.xboxID') < default.index('m.needsDefaultLayout = false', default.index('if load(')), \
    'a failed default load keeps the one-time default pending'
deleting = function(presets, 'func delete(_ id: String) -> Bool {')
assert 'let restored = Self.touchPad' in deleting and 'if !restored { m.layoutID = nil }' in deleting, \
    'a deleted active layout never stays as the on-screen copy source'
assert 'Self.touchPad' in function(presets, 'var defaultPending: Bool {'), 'no controller default without touch XInput'
overlay = function(content, 'struct TouchControlsOverlay: View {')
assert overlay.index('Color.clear.contentShape(editorCanvas(geo.size))') < overlay.index('GestureZonesLayer('), 'dismissal stays behind editable controls'
assert panel.index('.onTapGesture { }') < panel.index('.position(layout.center)'), 'only the panel consumes its background taps'
assert 'ControlPresetsModel.enabled && m.visible && !m.editing' in overlay, 'menu only while touch controls are shown'
assert 'if m.editing && Self.editorDone {' in overlay and 'Text("Done")' in overlay
assert 'TouchControlsOverlay.showsLayoutMenu(self) ? 3 : 2' in model, 'the menu button is hit-testable'
window = function(content, 'final class ControlsWindow: UIWindow {')
assert window.index('if m.editing {') < window.index('!hit.isDescendant(of: root)') \
    < window.index('guard m.hitsInteractive('), 'menu and dialog presentations take their touches in play mode'
reserve = function(gamepad, '@MainActor func reserveSessionSlot(touchControls: Bool) {')
assert reserve.index('guard Self.enabled, Self.optIn("MADEIRA_PAD_EARLY_SLOT")') < reserve.index('touchState.reserved = true')
run = function(content, 'private func runWineFullSequence(profile: LibraryEntry? = nil) {')
assert run.index('GamepadInput.shared.reserveSessionSlot(') < run.index('DispatchQueue.global'), 'reserved before Wine starts'

# The built-in reaches a library session: LibraryHUD replaces the overlay's top bar there, so the
# Session menu carries the same menu, and a game remembers the layout it was loaded from.
lib = (app / 'Library.swift').read_text(encoding='utf-8')
hud = function(lib, 'struct LibraryHUD: View {')
menu = function(hud, 'private var menu: some View {')
row = menu.index('ControlLayoutMenu(style: .row)')
assert 'if session && !m.editing { LibraryHUD() } else { topBar }' in overlay, 'a session shows the HUD instead of the top bar'
assert menu.index('Toggle("Touch controls"') < row < menu.index('LabeledContent("Opacity")'), \
    'the Session menu offers the layout menu with the touch-control settings'
assert 'controls.visible && ControlPresetsModel.enabled' in menu[row - 80:row], \
    'only while touch controls are on and MADEIRA_CONTROL_PRESETS is not 0'
assert 'model.saveCurrentProfile()' in menu[row:menu.index('LabeledContent("Opacity")')], 'a chosen layout is saved to the game'
layout_menu = function(presets, 'struct ControlLayoutMenu: View {')
assert 'enum Style { case glass, row }' in layout_menu and 'LabeledContent("Controller layout")' in layout_menu
assert 'ControlLayoutMenu()' in overlay, 'the overlay keeps its top-bar button, unchanged'
entry = function(lib, 'struct LibraryEntry: Codable, Identifiable {')
assert 'var controlLayout: String?' in entry, 'optional, so older library files decode'
model_lib = function(lib, 'final class LibraryModel: ObservableObject {')
begin = function(model_lib, 'func begin(_ entry: LibraryEntry')
assert 'store.resolvedID(' in begin and 'savedLayout = controls.layoutID' in begin
assert 'ControlPresetStore.restoredID(entry.controlLayout, adaptive: entry.adaptiveControlLayout)' in begin, \
    'legacy per-game built-ins must pass the provenance check before auto-reflow'
assert 'var adaptiveControlLayout: Bool?' in entry, 'older library profiles decode without an adaptive marker'
assert begin.index('if let profile = entry.controls') < begin.index('resolvedID'), "the layout follows the game's own controls only"
profile_save = function(model_lib, 'func saveCurrentProfile()')
assert 'entry.controlLayout = controls.layoutID' in profile_save and 'entry.adaptiveControlLayout = true' in profile_save
fin = function(model_lib, 'private func finish()')
assert fin.index('controls.editing = false') < fin.index('saveCurrentProfile()') \
    < fin.index('controls.layoutID = savedLayout'), 'finish ends editing, saves the game, then restores the shared layout'

# The WASD stick's centre glyph: drawn by the stick face, fed by the action.
face = function(content, 'struct JoystickFace: View {')
assert 'var glyph: String?' in face and 'Image(systemName: g)' in face, 'the stick face draws a glyph'
assert 'glyph: control.action.stickGlyph' in function(content, 'struct TouchControlButton: View {'), 'the overlay stick passes its glyph'
assert 'JoystickFace(held: s.held, dir: s.dir)' in content and 'JoystickFace(held: false, dir: -1)' in content, 'the portrait pad passes none, drawn as before'
assert '.opacity(glyph == nil || expanded ? 1 : 0)' in face, 'no glyph: the knob is always drawn'
print('PASS: switches (opt-in built-in default and session slot), edit write-back, layout menu, session-menu layout choice and stick glyph wiring')
