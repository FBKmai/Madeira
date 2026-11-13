import Foundation
import SwiftUI
import UIKit

// ============================================================================
// ml1530/ml1970 — NAMED TOUCH-CONTROL LAYOUTS.
//
// A layout is the landscape editor's `TouchControlsModel.controls`. The user's
// own layouts ("Custom Layout 1", "Custom Layout 2", ...) are kept app-wide in
// Documents/madeira-control-presets.json, beside madeira-controls.json, so a
// device backup carries them. Built-ins ship in code and can be loaded but
// never changed: "Xbox controller" and "Short-edge grip" both map full XInput.
//
// madeira-controls.json stays the working copy the overlay draws; it records
// which layout it was loaded from (`TouchControlsModel.layoutID`) so edits made
// in the editor are written back to that custom layout when editing ends.
//
// The layout menu is offered in two places: the landscape overlay's top bar
// (`ControlLayoutMenu`) and, in a library session, where LibraryHUD replaces
// that bar, as a "Controller layout" row of the in-game Session menu (the same
// view, `.row` style). A library game remembers its layout (`LibraryEntry.
// controlLayout`); other games and the overlay outside the library keep the
// one shared working copy.
//
// Switches (Documents/madeira.cfg `env.NAME = value`, or the environment):
//   MADEIRA_CONTROL_PRESETS=0        no layout menu, no write-back (default on)
//   MADEIRA_CONTROLS_XBOX_DEFAULT=1  a user with no controls file gets the
//                                    built-in once (default OFF: otherwise the
//                                    built-in is only applied from the menu)
// ============================================================================

// MARK: - Pure preset state (also compiled by the host regression test)

struct ControlPreset: Codable, Identifiable, Equatable {
    var id: String
    var name: String
    var controls: [TouchControl]
    /// Gesture zones (GestureZones.swift). Optional, so layouts saved before
    /// zones existed still decode; nil reads as none.
    var zones: [GestureZone]? = nil
}

enum GestureZoneKind: String, Codable, CaseIterable {
    case stick, swipe, look
    var title: String { switch self { case .stick: "Stick"; case .swipe: "Swipe"; case .look: "Look" } }
}

enum SwipeDirections: String, Codable, CaseIterable {
    case four, horizontal, vertical
    var title: String { switch self { case .four: "All"; case .horizontal: "Left/Right"; case .vertical: "Up/Down" } }
}

struct GestureZone: Codable, Identifiable, Equatable {
    static let directionNames = ["up", "down", "left", "right"]

    var id = UUID()
    /// Top-left corner and size, as fractions of the screen.
    var x = 0.04, y = 0.3, w = 0.36, h = 0.62
    var kind: GestureZoneKind = .stick
    /// Stick zones: .pad("LS"), .pad("RS"), .joystickWASD or .joystickArrows.
    var stick: ControlAction = .pad("LS")
    /// Swipe zones: what each direction presses.
    var swipe: [String: ControlAction] = ["up": .pad("D↑"), "down": .pad("D↓"),
                                          "left": .pad("D←"), "right": .pad("D→")]
    var directions: SwipeDirections = .four
    /// Swipe zones: a tap that did not become a swipe.
    var tap: ControlAction = .none
    /// Stick: full deflection distance is 70 pt / sensitivity. Swipe: the swipe
    /// length is 36 pt / sensitivity. Look: mouse counts per point.
    var sensitivity = 1.0
    func contains(_ p: CGPoint, in size: CGSize) -> Bool { rect(in: size).contains(p) }
    /// Locked in place: the editor selects it but will not move or resize it.
    var locked: Bool?

    func rect(in size: CGSize) -> CGRect {
        CGRect(x: x * size.width, y: y * size.height, width: w * size.width, height: h * size.height)
    }
    var feedsPad: Bool {
        switch kind {
        case .stick: return stick.isPad
        case .swipe: return tap.isPad || swipe.values.contains { $0.isPad }
        case .look: return false
        }
    }
}


/// The screen a built-in layout is placed on, in points, with its safe-area
/// insets. Built-ins are laid out in points from the edges and then normalised
/// to THIS screen, so one layout reads right on a phone and on a tablet.
struct ControlPresetScreen: Equatable {
    var width: Double
    var height: Double
    var left = 0.0, right = 0.0, top = 0.0, bottom = 0.0

    /// Ignore zero/transitional window geometry rather than replacing a layout.
    var isUsable: Bool {
        [width, height, left, right, top, bottom].allSatisfy { $0.isFinite }
            && left >= 0 && right >= 0 && top >= 0 && bottom >= 0
            && width > left + right && height > top + bottom
    }

    /// The legacy Xbox layout is landscape-only, so a portrait screen is laid out as the
    /// landscape one it rotates to: the top/bottom insets move to the sides.
    var landscape: ControlPresetScreen {
        guard height > width else { return self }
        let side = max(top, bottom)
        return ControlPresetScreen(width: height, height: width, left: side, right: side,
                                   top: 0, bottom: min(bottom, 21))
    }

    /// A 6.3-inch phone in landscape: what the stored copy of a built-in is
    /// laid out for. Loading lays it out again for the real screen.
    static let referencePhone = ControlPresetScreen(width: 874, height: 402,
                                                    left: 59, right: 59, top: 0, bottom: 21)
}

enum ControlPresetLayout {
    static let xboxID = "builtin.xbox"
    static let xboxName = "Xbox controller"
    static let shortEdgeID = "builtin.short-edge"
    static let shortEdgeName = "Short-edge grip"
    /// Mirrors `TouchControlsModel.baseDiameter`.
    static let baseDiameter = 64.0

    /// The margins a built-in keeps from each edge, whatever the reported insets.
    static func margins(_ s: ControlPresetScreen) -> (left: Double, right: Double, top: Double, bottom: Double) {
        (max(s.left, 16), max(s.right, 16), max(s.top, 8), max(s.bottom, 8))
    }

    /// The overlay's own buttons, centred at the top (TouchControlsModel.
    /// hitsInteractive claims this band). A built-in leaves it free.
    static func topBarRect(_ s: ControlPresetScreen) -> CGRect {
        // Four 44pt buttons, three 10pt gaps, plus the window's 10pt hit slop.
        CGRect(x: s.width / 2 - 113, y: 0, width: 226, height: 76)
    }

    /// The drawn bounding box, in points: `baseDiameter` × the control's scale
    /// for a round button, the pad button's own shape otherwise (a wide
    /// shoulder, a Start/Select pill), centred on its normalised position.
    /// `sizeScale` is the session-wide control-size slider; built-in layouts use
    /// this helper to cap that slider before enlarged controls can collide.
    static func box(_ c: TouchControl, screen s: ControlPresetScreen, sizeScale: Double = 1) -> CGRect {
        let d = baseDiameter * c.scale * (sizeScale.isFinite ? sizeScale : 1)
        let z = c.action.controlSize(diameter: CGFloat(d))
        return CGRect(x: c.nx * s.width - Double(z.width) / 2, y: c.ny * s.height - Double(z.height) / 2,
                      width: Double(z.width), height: Double(z.height))
    }

    /// Test the actual drawn sizes, not just the centres. The editor's minimum
    /// size is not proof that a layout fits a very small resized window.
    static func fits(_ controls: [TouchControl], screen s: ControlPresetScreen, sizeScale: Double) -> Bool {
        guard s.isUsable, !controls.isEmpty, sizeScale.isFinite, sizeScale >= 0.5 else { return false }
        let m = margins(s)
        let safe = CGRect(x: m.left, y: m.top, width: s.width - m.left - m.right,
                          height: s.height - m.top - m.bottom)
        let boxes = controls.map { box($0, screen: s, sizeScale: sizeScale) }
        guard boxes.allSatisfy({ safe.contains($0) }),
              !boxes.contains(where: { $0.intersects(topBarRect(s)) }) else { return false }
        for i in boxes.indices {
            for j in boxes.indices where j > i {
                let a = boxes[i], b = boxes[j]
                let round = abs(a.width - a.height) < 0.001 && abs(b.width - b.height) < 0.001
                if round {
                    let dx = a.midX - b.midX, dy = a.midY - b.midY
                    if (dx * dx + dy * dy).squareRoot() < a.width / 2 + b.width / 2 + 2 { return false }
                } else if a.insetBy(dx: -1, dy: -1).intersects(b) {
                    return false
                }
            }
        }
        return true
    }

    /// Largest session-wide size that keeps a pristine built-in inside the
    /// actual canvas, away from the overlay menu, and mutually separated. A
    /// game's Control size is a multiplier applied after a layout is loaded;
    /// without this cap a perfectly fitted foldable layout can overlap when a
    /// player chooses 150% or 200%.
    static func maximumSizeScale(for controls: [TouchControl], screen s: ControlPresetScreen) -> Double {
        guard s.isUsable, !controls.isEmpty else { return 2 }
        guard fits(controls, screen: s, sizeScale: 0.5) else { return 0.5 }
        var lo = 0.5, hi = 2.0
        for _ in 0..<24 {
            let mid = (lo + hi) / 2
            if fits(controls, screen: s, sizeScale: mid) { lo = mid } else { hi = mid }
        }
        return lo
    }

    /// The built-in controller layout, using the editor's controller mappings:
    ///
    ///   LT LB  (top left)                              (top right)  RB RT
    ///   D-pad  above the left stick        A/B/X/Y diamond above the right stick
    ///   LS (bottom left)  L3    View  Menu     R3  RS (bottom right)
    ///
    /// Placed in points from the safe-area edges, then normalised. `k` scales
    /// the whole thing up on a tall (tablet) screen, where a phone-sized stick
    /// would be lost; every scale stays inside the editor's 0.5–3.0 pinch clamp.
    static func xbox(for screen: ControlPresetScreen) -> [TouchControl] {
        let s = screen.landscape
        let W = s.width, H = s.height
        guard W > 0, H > 0 else { return [] }
        let k = min(max(H / 400, 1.0), 1.3)
        let (L, R, T, B) = margins(s)
        var out: [TouchControl] = []
        func add(_ name: String, _ scale: Double, _ x: Double, _ y: Double) {
            var c = TouchControl()
            c.action = .pad(name)
            c.scale = scale
            c.nx = x / W
            c.ny = y / H
            out.append(c)
        }
        func d(_ scale: Double) -> Double { baseDiameter * scale }
        let stickScale = 1.45 * k, faceScale = 0.78 * k, dpadScale = 0.7 * k
        let shoulderScale = 0.88 * k, systemScale = 0.75 * k, clickScale = 0.62 * k

        // Sticks: bottom corners, clear of the home indicator.
        let stick = d(stickScale)
        let stickY = H - B - 12 * k - stick / 2
        let lStickX = L + 76 * k, rStickX = W - R - 76 * k
        add("LS", stickScale, lStickX, stickY)
        add("RS", stickScale, rStickX, stickY)
        let stickTop = stickY - stick / 2

        // Shoulders: a column in each top corner, trigger above bumper as on
        // the controller. Drawn 1.6× as wide as they are tall and 0.74 d high
        // (ControlAction.controlSize), so the column is two of those plus a gap.
        let sh = d(shoulderScale), shW = sh * 1.6, shH = sh * 0.74
        let shoulderX = shW / 2 + 6 * k
        let triggerY = T + 6 * k + shH / 2
        let bumperY = triggerY + shH + 8 * k
        add("LT", shoulderScale, L + shoulderX, triggerY)
        add("LB", shoulderScale, L + shoulderX, bumperY)
        add("RB", shoulderScale, W - R - shoulderX, bumperY)
        add("RT", shoulderScale, W - R - shoulderX, triggerY)
        // The columns' bottom and inner edge, for placing the D-pad cross and
        // the face diamond below them (or, on a short screen, inboard of them).
        let rowBottom = bumperY + shH / 2
        let columnInner = shoulderX + shW / 2 + 10 * k

        // D-pad: a tight cross at the left edge, between the shoulder column
        // and the stick, so the middle of the screen stays clear. When the
        // screen is too short for that stack (a phone with a tall column), the
        // cross moves inboard of the column instead and rises beside it.
        let dp = d(dpadScale), arm = dp + 6 * k
        let stacked = rowBottom + 8 * k + 2 * arm + dp <= stickTop - 8 * k
        let dpadX = stacked ? L + 6 * k + arm + dp / 2 : L + columnInner + arm + dp / 2
        let dpadY = stacked ? rowBottom + 8 * k + arm + dp / 2
                            : max(stickTop - 22 * k - arm - dp / 2, T + 6 * k + arm + dp / 2)
        add("D↑", dpadScale, dpadX, dpadY - arm)
        add("D←", dpadScale, dpadX - arm, dpadY)
        add("D→", dpadScale, dpadX + arm, dpadY)
        add("D↓", dpadScale, dpadX, dpadY + arm)

        // A/B/X/Y: a tight diamond at the right edge, mirroring the D-pad.
        // Diagonal neighbours sit o·√2 apart, which clears one face button's
        // diameter.
        let face = d(faceScale)
        let o = face / 2 + 22 * k
        let cx = stacked ? W - R - 6 * k - o - face / 2 : W - R - columnInner - o - face / 2
        let cy = stacked ? rowBottom + 8 * k + o + face / 2
                         : max(stickTop - 22 * k - o - face / 2, T + 6 * k + o + face / 2)
        add("Y", faceScale, cx, cy - o)
        add("X", faceScale, cx - o, cy)
        add("B", faceScale, cx + o, cy)
        add("A", faceScale, cx, cy + o)

        // View / Menu: bottom centre, between the sticks.
        let sys = d(systemScale)
        let sysY = H - B - 20 * k - sys / 2
        add("View", systemScale, W / 2 - 46 * k, sysY)
        add("Menu", systemScale, W / 2 + 46 * k, sysY)

        // L3 / R3: small buttons on the inner side of each stick, level with
        // its bottom edge.
        let click = d(clickScale)
        let clickY = stickY + stick / 2 - click / 2
        add("L3", clickScale, lStickX + stick / 2 + 20 * k + click / 2, clickY)
        add("R3", clickScale, rStickX - stick / 2 - 20 * k - click / 2, clickY)
        return out
    }

    struct ShortEdgeFit {
        var left: Double, trailing: Double, top: Double, bottom: Double
        var scale: Double
        /// The requested overall control size, capped by the available canvas.
        /// Keep this separate from per-control scales so the editor's 0.5 clamp
        /// cannot enlarge a fitted button back into its neighbours.
        var sizeScale: Double
    }

    static func shortEdgeFit(for s: ControlPresetScreen, sizeScale: Double = 1) -> ShortEdgeFit? {
        guard s.isUsable else { return nil }
        let m = margins(s)
        let left = max(m.left, s.width * 0.03), trailing = max(m.right, s.width * 0.03)
        let bottom = max(m.bottom, s.height * 0.03), top = max(m.top, s.height * 0.03)
        let width = s.width - left - trailing
        guard width > 0 else { return nil }
        // Try both sides of the menu and below it. Pick the region with the
        // most room BEFORE capping the default size, so enlarging the controls
        // can use the same safe fit instead of growing into the menu.
        let clusterWidth = 199.8
        let widthScale = (width - 2) / (2 * clusterWidth)
        let bar = topBarRect(s).insetBy(dx: -10, dy: 0)
        let beside = min(widthScale, min((s.height - top - bottom) / 384,
                         min((Double(bar.minX) - left) / clusterWidth,
                             (s.width - trailing - Double(bar.maxX)) / clusterWidth)))
        let belowTop = max(top, Double(bar.maxY) + 8)
        let below = min(widthScale, (s.height - belowTop - bottom) / 384)
        let limit = max(beside, below)
        let scale = min(1.15, limit)
        guard scale >= 0.5 / 0.7 else { return nil }
        let requested = sizeScale.isFinite ? min(max(sizeScale, 0.5), 2) : 1
        return ShortEdgeFit(left: left, trailing: trailing,
                            top: beside >= below ? top : belowTop, bottom: bottom,
                            scale: scale, sizeScale: min(requested, limit / scale))
    }

    /// Two bounded thumb clusters, centred vertically instead of stretching
    /// from the top to the bottom of a tall unfolded display. Uses the ACTUAL
    /// canvas, including portrait sessions; no device or hinge assumptions.
    static func shortEdge(for s: ControlPresetScreen, sizeScale: Double = 1) -> [TouchControl] {
        guard let fit = shortEdgeFit(for: s, sizeScale: sizeScale) else { return [] }
        let k = fit.scale * fit.sizeScale
        let height = s.height - fit.top - fit.bottom
        let y0 = fit.top + (height - 384 * k) / 2
        var out: [TouchControl] = []
        func add(_ name: String, _ scale: Double, _ x: Double, _ y: Double, right: Bool = false) {
            var c = TouchControl()
            c.action = .pad(name)
            // `fit.sizeScale` is applied by TouchControlsModel's shared size
            // multiplier. Do not bake it into each control as well, or a 150%
            // request would become 225% and exceed the fit we just calculated.
            c.scale = scale * fit.scale
            c.nx = (right ? s.width - fit.trailing - x * k : fit.left + x * k) / s.width
            c.ny = (y0 + y * k) / s.height
            out.append(c)
        }
        add("LT", 0.88, 53, 30); add("LB", 0.88, 53, 80)
        add("RT", 0.88, 53, 30, right: true); add("RB", 0.88, 53, 80, right: true)
        add("View", 0.75, 171, 30); add("Menu", 0.75, 171, 30, right: true)
        let arm = 50.8
        add("D↑", 0.7, 78, 194 - arm); add("D↓", 0.7, 78, 194 + arm)
        add("D←", 0.7, 78 - arm, 194); add("D→", 0.7, 78 + arm, 194)
        let face = 46.96
        add("Y", 0.78, 78, 194 - face, right: true)
        add("A", 0.78, 78, 194 + face, right: true)
        add("X", 0.78, 78 + face, 194, right: true)
        add("B", 0.78, 78 - face, 194, right: true)
        add("LS", 1.45, 78, 327); add("RS", 1.45, 78, 327, right: true)
        add("L3", 0.7, 175, 350); add("R3", 0.7, 175, 350, right: true)
        return out
    }

    static func sizeLimit(for id: String?, screen: ControlPresetScreen) -> Double {
        guard screen.isUsable else { return 2 }
        switch id {
        case shortEdgeID:
            return shortEdgeFit(for: screen, sizeScale: 2)?.sizeScale ?? 1
        case xboxID:
            return maximumSizeScale(for: xbox(for: screen), screen: screen.landscape)
        default: return 2
        }
    }

    static func controls(for id: String, screen: ControlPresetScreen, sizeScale: Double = 1) -> [TouchControl]? {
        switch id {
        case xboxID:
            // This legacy layout is landscape-only. A small but otherwise valid
            // window can still be too tight even at the slider's minimum size.
            let controls = xbox(for: screen)
            return screen.width > screen.height && fits(controls, screen: screen, sizeScale: sizeScale)
                ? controls : []
        case shortEdgeID: return shortEdge(for: screen, sizeScale: sizeScale)
        default: return nil
        }
    }
}

/// The layout list: built-ins (read-only, in code), then the user's own
/// (persisted). Pure value type; `ControlPresetsModel` owns the file.
struct ControlPresetStore: Equatable {
    static let builtIns: [ControlPreset] = [
        ControlPreset(id: ControlPresetLayout.xboxID, name: ControlPresetLayout.xboxName,
                      controls: ControlPresetLayout.xbox(for: .referencePhone)),
        ControlPreset(id: ControlPresetLayout.shortEdgeID, name: ControlPresetLayout.shortEdgeName,
                      controls: ControlPresetLayout.shortEdge(for: .referencePhone)),
    ]
    static let maxNameLength = 40

    private(set) var user: [ControlPreset] = []

    init(user: [ControlPreset] = []) { self.user = user.filter { !Self.isBuiltIn($0.id) } }

    var all: [ControlPreset] { Self.builtIns + user }

    static func isBuiltIn(_ id: String) -> Bool { builtIns.contains { $0.id == id } }

    func preset(_ id: String) -> ControlPreset? { all.first { $0.id == id } }

    /// The id if a layout still has it, else nil: a game's remembered layout may
    /// have been deleted since, and controls that no layout holds are unsaved.
    func resolvedID(_ id: String?) -> String? { id.flatMap { preset($0)?.id } }

    /// Old files could save a modified built-in before the editor's Done
    /// cleared its ID. An ID alone therefore is NOT permission to regenerate
    /// those controls. Preserve ambiguous copies as unsaved, until the user
    /// explicitly selects a built-in again. Custom layout IDs stay unchanged.
    static func restoredID(_ id: String?, adaptive: Bool?) -> String? {
        guard let id else { return nil }
        return isBuiltIn(id) && adaptive != true ? nil : id
    }

    static func clean(_ name: String) -> String {
        String(name.trimmingCharacters(in: .whitespacesAndNewlines).prefix(maxNameLength))
    }

    /// Case-insensitive, whitespace-trimmed: "xbox controller " IS the built-in.
    func named(_ name: String) -> ControlPreset? {
        let n = Self.clean(name).lowercased()
        guard !n.isEmpty else { return nil }
        return all.first { $0.name.lowercased() == n }
    }

    /// "Custom Layout N", the lowest N not taken.
    func nextCustomName() -> String {
        var n = 1
        while named("Custom Layout \(n)") != nil { n += 1 }
        return "Custom Layout \(n)"
    }

    enum SaveResult: Equatable {
        case created(String)      // new user layout, its id
        case replaced(String)     // an existing user layout of that name, its id
        case refusedBuiltIn       // the name is a built-in's: pick another
        case refusedEmpty
    }

    /// Save a layout under a name. A built-in's name is refused (built-ins are
    /// never overwritten); a user layout's name replaces that layout in place.
    mutating func save(name: String, controls: [TouchControl], zones: [GestureZone] = [],
                       newID: () -> String = { UUID().uuidString }) -> SaveResult {
        let n = Self.clean(name)
        guard !n.isEmpty else { return .refusedEmpty }
        if let existing = named(n) {
            if Self.isBuiltIn(existing.id) { return .refusedBuiltIn }
            guard let i = user.firstIndex(where: { $0.id == existing.id }) else { return .refusedEmpty }
            user[i].controls = controls
            user[i].zones = zones.isEmpty ? nil : zones
            return .replaced(existing.id)
        }
        let id = newID()
        user.append(ControlPreset(id: id, name: n, controls: controls, zones: zones.isEmpty ? nil : zones))
        return .created(id)
    }

    /// Overwrite a user layout's controls. false for a built-in or a missing id.
    mutating func overwrite(id: String, controls: [TouchControl], zones: [GestureZone] = []) -> Bool {
        guard let i = user.firstIndex(where: { $0.id == id }) else { return false }
        user[i].controls = controls
        user[i].zones = zones.isEmpty ? nil : zones
        return true
    }

    /// false for a built-in or a missing id.
    mutating func delete(id: String) -> Bool {
        guard let i = user.firstIndex(where: { $0.id == id }) else { return false }
        user.remove(at: i)
        return true
    }

    private struct File: Codable { var version: Int; var presets: [ControlPreset] }

    /// Only the user's layouts are written; built-ins live in code.
    func encoded() throws -> Data {
        let e = JSONEncoder()
        e.outputFormatting = [.prettyPrinted, .sortedKeys]
        return try e.encode(File(version: 1, presets: user))
    }

    static func decoded(_ data: Data) throws -> ControlPresetStore {
        let f = try JSONDecoder().decode(File.self, from: data)
        guard f.version == 1 else {
            throw DecodingError.dataCorrupted(.init(codingPath: [], debugDescription: "preset file version \(f.version)"))
        }
        return ControlPresetStore(user: f.presets)
    }

    /// What loading a layout puts on screen: its controls with FRESH ids (a
    /// control's id keys its touch state, and two loads of one layout must not
    /// share them), positions inside the editor's drag clamp, and scales inside
    /// the pinch clamp. A built-in is laid out again for the screen it is
    /// loaded on.
    static func layout(of p: ControlPreset, screen: ControlPresetScreen?, sizeScale: Double = 1) -> [TouchControl] {
        var controls = p.controls
        if ControlPresetStore.isBuiltIn(p.id), let screen {
            guard screen.isUsable,
                  let fitted = ControlPresetLayout.controls(for: p.id, screen: screen, sizeScale: sizeScale),
                  !fitted.isEmpty else { return [] }
            controls = fitted
        }
        return controls.map { c in
            var c = c
            c.id = UUID()
            c.nx = min(max(c.nx, 0.03), 0.97)
            c.ny = min(max(c.ny, 0.03), 0.97)
            c.scale = min(max(c.scale, 0.5), 3.0)
            return c
        }
    }

    /// Only a pristine built-in follows the live canvas. Custom, unsaved and
    /// in-progress editor copies are never touched. Returning nil for unchanged
    /// geometry also prevents an observation -> controls -> observation loop.
    static func reflow(id: String?, controls: [TouchControl], screen: ControlPresetScreen,
                       editing: Bool, sizeScale: Double = 1) -> [TouchControl]? {
        guard !editing, screen.isUsable, let id, isBuiltIn(id),
              id != ControlPresetLayout.xboxID || screen.width > screen.height,
              let fitted = ControlPresetLayout.controls(for: id, screen: screen, sizeScale: sizeScale),
              !fitted.isEmpty else { return nil }
        // On a temporarily undersized canvas the overlay hides and blocks the
        // old controls, but keeps their IDs so player one's pad stays connected.
        // A later resize regenerates the layout without an empty intermediate set.
        let preset = ControlPreset(id: id, name: "", controls: fitted)
        let next = layout(of: preset, screen: nil)
        let unchanged = controls.count == next.count && zip(controls, next).allSatisfy { a, b in
            a.action == b.action && a.nx == b.nx && a.ny == b.ny && a.scale == b.scale
        }
        return unchanged ? nil : next
    }
}

extension ControlPresetStore {
    /// A layout's zones as loaded: fresh ids (an id keys the zone's touch
    /// state), rectangles kept on screen.
    static func zones(of p: ControlPreset) -> [GestureZone] {
        (p.zones ?? []).map { z in
            var z = z
            z.id = UUID()
            z.w = min(max(z.w, 0.06), 1); z.h = min(max(z.h, 0.08), 1)
            z.x = min(max(z.x, 0), 1 - z.w); z.y = min(max(z.y, 0), 1 - z.h)
            return z
        }
    }
}

// MARK: - Persistence and overlay actions

/// Owns madeira-control-presets.json and applies layouts to TouchControlsModel.
/// Main thread only, like the overlay that drives it.
final class ControlPresetsModel: ObservableObject {
    static let shared = ControlPresetsModel()
    static let enabled = GamepadInput.flag("MADEIRA_CONTROL_PRESETS")
    /// Opt-in. "No madeira-controls.json" is not a fresh install: the file is
    /// only written once the controls or their visibility change, so an
    /// existing user who never touched them has none either and would get an
    /// 18-button overlay they did not ask for. Nothing on disk tells the two
    /// apart reliably, so the built-in is applied automatically only on request.
    static let xboxDefault = GamepadInput.optIn("MADEIRA_CONTROLS_XBOX_DEFAULT")

    @Published private(set) var store = ControlPresetStore()
    /// A file that exists and cannot be read is left untouched: saving is
    /// refused instead of overwriting it.
    private(set) var readOnly = false
    private var logged = 0

    private static var url: URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("madeira-control-presets.json")
    }

    private init() {
        guard let d = try? Data(contentsOf: Self.url) else { return }
        do {
            store = try ControlPresetStore.decoded(d)
        } catch {
            readOnly = true
            log("unreadable file kept, saving disabled: \(error.localizedDescription)")
        }
    }

    /// The controller built-in needs touch XInput; without it its buttons are inert.
    private static var touchPad: Bool { MainActor.assumeIsolated { GamepadInput.touchEnabled } }

    /// What the layout menu lists.
    var available: [ControlPreset] {
        (Self.touchPad ? ControlPresetStore.builtIns : []) + store.user
    }

    var active: ControlPreset? { TouchControlsModel.shared.layoutID.flatMap { store.preset($0) } }

    /// On-screen controls that no layout holds: switching away would lose them.
    var currentIsUnsaved: Bool {
        let m = TouchControlsModel.shared
        return m.layoutID == nil && (!m.controls.isEmpty || !GestureZonesModel.shared.zones.isEmpty)
    }

    /// With MADEIRA_CONTROLS_XBOX_DEFAULT=1, a user with no madeira-controls.json gets the controller layout the
    /// first time the landscape overlay appears.
    var defaultPending: Bool {
        TouchControlsModel.shared.needsDefaultLayout && Self.enabled && Self.xboxDefault && Self.touchPad
    }

    private func log(_ line: String) {
        guard logged < 64 else { return }
        logged += 1
        fputs("[controls-layout] ml1970 \(line)\n", stderr)
    }

    @discardableResult private func persist() -> Bool {
        guard !readOnly else { return false }
        do {
            try store.encoded().write(to: Self.url, options: .atomic)
            return true
        } catch {
            log("write failed: \(error.localizedDescription)")
            return false
        }
    }

    /// Actual canvas, not an assumed device shape. The Xbox factory handles
    /// its own landscape normalisation; short-edge grip also fits portrait.
    static func currentScreen() -> ControlPresetScreen {
        if let screen = TouchControlsHost.screen { return screen }
        let scenes = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
        let scene = scenes.first { $0.activationState == .foregroundActive }
        guard let window = scene?.windows.first(where: { $0.isKeyWindow }) else { return .referencePhone }
        let i = window.safeAreaInsets
        let screen = ControlPresetScreen(width: Double(window.bounds.width), height: Double(window.bounds.height),
                                         left: Double(i.left), right: Double(i.right),
                                         top: Double(i.top), bottom: Double(i.bottom))
        return screen.isUsable ? screen : .referencePhone
    }

    /// Rebuild only built-ins, including old per-game copies restored at the
    /// same window size. Fresh control IDs invalidate pre-resize finger owners.
    func reflowBuiltIn(screen: ControlPresetScreen) {
        let m = TouchControlsModel.shared
        guard Self.enabled, !m.editing, let id = m.layoutID, ControlPresetStore.isBuiltIn(id) else {
            m.fitsCanvas = true
            return
        }
        guard screen.isUsable else { return }
        let sizeScale = min(m.sizeScale, ControlPresetLayout.sizeLimit(for: id, screen: screen))
        // Both built-ins can be temporarily too large for a compact split
        // window. Keep their IDs and pad connection, but hide input until the
        // window can fit a complete layout again. Do not lower the saved size
        // just because an intermediate window cannot fit any controls.
        guard let fitting = ControlPresetLayout.controls(for: id, screen: screen,
                                                         sizeScale: sizeScale),
              !fitting.isEmpty else {
            m.fitsCanvas = false
            return
        }
        m.sizeScale = sizeScale
        m.fitsCanvas = true
        guard let next = ControlPresetStore.reflow(id: id, controls: m.controls,
                                                   screen: screen, editing: m.editing,
                                                   sizeScale: m.sizeScale) else { return }
        m.selected = nil
        m.setControlsForGeometry(next)
    }

    /// Never over a layout the user already has: only when no controls file existed.
    func applyDefaultIfNeeded(screen: ControlPresetScreen) {
        let m = TouchControlsModel.shared
        guard m.needsDefaultLayout else { return }
        guard defaultPending && m.controls.isEmpty else {
            m.needsDefaultLayout = false
            return
        }
        // Retry on the next overlay if this canvas cannot fit the built-in yet.
        if load(ControlPresetLayout.xboxID, screen: screen, reason: "new-user-default") {
            m.needsDefaultLayout = false
        }
    }

    /// Replace the on-screen layout with this one. False leaves the current
    /// layout untouched, so a caller can keep or clear its source explicitly.
    @discardableResult
    func load(_ id: String, screen: ControlPresetScreen, reason: String = "chosen") -> Bool {
        guard let p = store.preset(id) else { return false }
        let m = TouchControlsModel.shared
        let sizeScale = min(m.sizeScale, ControlPresetLayout.sizeLimit(for: p.id, screen: screen))
        let controls = ControlPresetStore.layout(of: p, screen: screen, sizeScale: sizeScale)
        // No safe fit at the editor's minimum size: leave the current layout
        // intact rather than silently loading reference-phone geometry.
        guard !ControlPresetStore.isBuiltIn(p.id) || !controls.isEmpty else {
            log("layout does not fit current canvas id=\(p.id)")
            return false
        }
        m.selected = nil
        m.sizeScale = sizeScale
        m.fitsCanvas = true
        m.controls = controls
        GestureZonesModel.shared.selected = nil
        GestureZonesModel.shared.zones = ControlPresetStore.zones(of: p)
        m.layoutID = p.id
        log("loaded layout=\(ControlPresetStore.isBuiltIn(p.id) ? p.id : "custom") controls=\(controls.count) reason=\(reason)")
        return true
    }

    /// Keep the unsaved on-screen controls as the next "Custom Layout N".
    @discardableResult func keepCurrent() -> Bool {
        guard !readOnly else { return false }
        let m = TouchControlsModel.shared
        var s = store
        guard case .created(let id) = s.save(name: s.nextCustomName(), controls: m.controls,
                                             zones: GestureZonesModel.shared.zones) else { return false }
        store = s
        m.layoutID = id
        persist()
        log("kept on-screen controls as a custom layout controls=\(m.controls.count)")
        return true
    }

    /// "Create new layout": an empty custom layout, made active, opened in the editor.
    @discardableResult func createLayout() -> Bool {
        guard !readOnly else { return false }
        var s = store
        guard case .created(let id) = s.save(name: s.nextCustomName(), controls: []) else { return false }
        store = s
        persist()
        let m = TouchControlsModel.shared
        m.selected = nil
        m.controls = []
        GestureZonesModel.shared.selected = nil
        GestureZonesModel.shared.zones = []
        m.layoutID = id
        m.visible = true
        m.editing = true
        log("created custom layout")
        return true
    }

    /// Delete a custom layout. The on-screen copy of a deleted active layout
    /// becomes the controller layout, or stays as unsaved controls without it.
    @discardableResult func delete(_ id: String) -> Bool {
        guard !readOnly else { return false }
        var s = store
        guard s.delete(id: id) else { return false }
        store = s
        persist()
        log("deleted custom layout")
        let m = TouchControlsModel.shared
        if m.layoutID == id {
            // A deleted layout must not stay as this copy's source: if the
            // fallback cannot load (tiny window), the copy becomes unsaved.
            let restored = Self.touchPad
                && load(ControlPresetLayout.xboxID, screen: Self.currentScreen(), reason: "deleted")
            if !restored { m.layoutID = nil }
        }
        return true
    }

    /// An edit session ended. Edits to a custom layout are written back to it;
    /// a built-in stays as shipped, so an edited copy of one becomes unsaved
    /// controls that the menu offers to keep before switching away.
    func editingEnded(baseline: [TouchControl], zoneBaseline: [GestureZone]) {
        guard Self.enabled else { return }
        let m = TouchControlsModel.shared
        guard let id = m.layoutID else { return }
        if ControlPresetStore.isBuiltIn(id) {
            if baseline != m.controls || zoneBaseline != GestureZonesModel.shared.zones {
                m.layoutID = nil
                log("edited built-in kept as unsaved controls=\(m.controls.count)")
            }
            return
        }
        var s = store
        guard !readOnly, s.overwrite(id: id, controls: m.controls, zones: GestureZonesModel.shared.zones) else { return }
        store = s
        persist()
        log("saved custom layout controls=\(m.controls.count)")
    }
}

// MARK: - Layout menu (landscape overlay, library session menu)

extension ControlPreset {
    /// Stored names and IDs stay language-independent; a user's own name is
    /// literal text, even when it happens to match a translated catalog key.
    var displayName: String {
        switch id {
        case ControlPresetLayout.xboxID: return L("Xbox controller")
        case ControlPresetLayout.shortEdgeID: return L("Short-edge grip")
        default: return name
        }
    }
}

/// The layout menu: the controller built-in, the user's custom layouts,
/// "Create new layout" (opens the editor on an empty layout) and deleting the
/// active custom layout. Shown only while touch controls are on. `.glass` is
/// the overlay's round top-bar button; `.row` is a labelled row of the library
/// session's Session menu.
struct ControlLayoutMenu: View {
    enum Style { case glass, row }

    @ObservedObject private var presets = ControlPresetsModel.shared
    @ObservedObject private var m = TouchControlsModel.shared
    private let style: Style
    /// Called after a layout was loaded, created or deleted, with true when the
    /// editor was opened (a library session saves the game's profile, and closes
    /// its menu to show the editor).
    private let didChoose: ((_ openedEditor: Bool) -> Void)?

    init(style: Style = .glass, didChoose: ((_ openedEditor: Bool) -> Void)? = nil) {
        self.style = style
        self.didChoose = didChoose
    }

    private enum Choice: Equatable { case load(String), create }
    @State private var pending: Choice?
    @State private var confirmDelete: ControlPreset?

    var body: some View {
        Group {
            if style == .row {
                LabeledContent("Controller layout") { menu }
            } else {
                menu
            }
        }
        .alert("Keep the current controls?", isPresented: shown($pending)) {
            if !presets.readOnly {
                Button("Keep as \u{201C}\(presets.store.nextCustomName())\u{201D}") {
                    let choice = pending
                    pending = nil
                    presets.keepCurrent()
                    perform(choice)
                }
            }
            Button("Replace", role: .destructive) {
                let choice = pending
                pending = nil
                perform(choice)
            }
            Button("Cancel", role: .cancel) { pending = nil }
        } message: {
            Text("The controls on screen are not saved in a layout.")
        }
        .alert("Delete \u{201C}\(confirmDelete?.name ?? "")\u{201D}?", isPresented: shown($confirmDelete)) {
            Button("Delete", role: .destructive) {
                if let p = confirmDelete, presets.delete(p.id) { didChoose?(false) }
                confirmDelete = nil
            }
            Button("Cancel", role: .cancel) { confirmDelete = nil }
        }
    }

    private var menu: some View {
        Menu {
            Section("Controller layout") {
                ForEach(presets.available) { p in
                    Button { request(.load(p.id)) } label: {
                        if m.layoutID == p.id { Label(p.displayName, systemImage: "checkmark") }
                        else if ControlPresetStore.isBuiltIn(p.id) { Label(p.displayName, systemImage: "gamecontroller") }
                        else { Text(p.name) }
                    }
                }
            }
            if !presets.readOnly {
                Button("Create new layout", systemImage: "plus") { request(.create) }
            }
            if let a = presets.active, !ControlPresetStore.isBuiltIn(a.id), !presets.readOnly {
                Button("Delete \u{201C}\(a.name)\u{201D}", systemImage: "trash", role: .destructive) {
                    confirmDelete = a
                }
            }
        } label: {
            switch style {
            case .glass:
                // Same look as the overlay's glass buttons; stroke glyph only.
                Image(systemName: "square.stack.3d.up")
                    .font(.system(size: 18, weight: .regular))
                    .foregroundStyle(.white)
                    .frame(width: 44, height: 44)
                    .background(GlassShape(circle: true))
            case .row:
                HStack(spacing: 4) {
                    Text(presets.active?.displayName ?? L("Custom"))
                    Image(systemName: "chevron.up.chevron.down").font(.caption)
                }
            }
        }
        .accessibilityLabel("Controller layout")
    }

    private func shown<T>(_ b: Binding<T?>) -> Binding<Bool> {
        Binding(get: { b.wrappedValue != nil }, set: { if !$0 { b.wrappedValue = nil } })
    }

    private func request(_ choice: Choice) {
        UIImpactFeedbackGenerator(style: .light).impactOccurred()
        if presets.currentIsUnsaved { pending = choice } else { perform(choice) }
    }

    private func perform(_ choice: Choice?) {
        switch choice {
        case .load(let id):
            presets.load(id, screen: ControlPresetsModel.currentScreen())
            didChoose?(false)
        case .create:
            if presets.createLayout() { didChoose?(true) }
        case nil: break
        }
    }
}
