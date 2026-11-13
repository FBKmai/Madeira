#!/usr/bin/env python3
"""App translations (app/Madeira/Localizable.xcstrings).

SwiftUI looks up every literal Text/Button/Label/Toggle/Section/... title in the string
catalog, so the app shows German, Spanish, Korean, Brazilian Portuguese, Russian or
Simplified Chinese when the device uses one, and English otherwise (a text the catalog
lacks stays English).

Checks: the catalog is in the app's resources with its languages; every key is still a
literal in the app's Swift (so a changed English text is noticed); every key has all six
languages; links, line breaks and trailing spaces survive translation. A text with
interpolations is keyed with %@ for each one (only String interpolations are translated
this way); its translations use %1$@, %2$@... so the words can move.
"""
from pathlib import Path
import json, re, sys

# Windows consoles may use a legacy code page; untranslated UI must not crash the check.
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='backslashreplace')

root = Path(__file__).resolve().parents[2]
app = root / 'app/Madeira'
failures = 0


def check(condition, label):
    global failures
    print(('PASS: ' if condition else 'FAIL: ') + label)
    if not condition:
        failures += 1


catalog = json.loads((app / 'Localizable.xcstrings').read_text(encoding='utf-8'))
project = (app.parent / 'Madeira.xcodeproj/project.pbxproj').read_text(encoding='utf-8')
languages = ['de', 'es', 'ko', 'pt-BR', 'ru', 'zh-Hans']

check(project.count('A1009C03 /* Localizable.xcstrings in Resources */') == 2 and
      project.count('A2009C03 /* Localizable.xcstrings */') == 3, 'the catalog is in the app resources')
regions = re.search(r'knownRegions = \((.*?)\);', project, re.S)
check(regions is not None and all(l in regions.group(1) for l in ['de', 'es', 'ko', '"pt-BR"', 'ru', '"zh-Hans"']), 'the project knows the languages')
check(catalog.get('sourceLanguage') == 'en', 'English is the source language')

# SwiftUI localized titles, explicit lookups, and OnboardingView's helpers
# whose title parameter is LocalizedStringKey. Include nested app UI such as
# SwiftSteam/SteamSignInView.swift, not just the top-level Swift files.
pattern = re.compile(r'\b(?:Text|Button|Label|Toggle|Section|Picker|navigationTitle|LabeledContent|TextField|Link|NavigationLink|'
                     r'Stepper|Menu|ShareLink|alert|confirmationDialog|SecureField|ContentUnavailableView|DisclosureGroup|ProgressView|L|'
                     r'LocalizedStringKey|header|primary|secondary|jitChoice)'
                     r'\(\s*"((?:[^"\\]|\\.)*)"')
def source_text(text):
    text = re.sub(r'\\\([^()"]*\)', '%@', text)
    text = re.sub(r'\\u\{([0-9A-Fa-f]+)\}', lambda x: chr(int(x.group(1), 16)), text)
    return re.sub(r'\\(["\\nt\'])', lambda x: {'n': '\n', 't': '\t'}.get(x.group(1), x.group(1)), text)


literals = set()
explicit = set()
sources = {}
lookups = re.compile(r'\b(?:L|LocalizedStringKey)\(\s*"((?:[^"\\]|\\.)*)"')
for swift in app.rglob('*.swift'):
    source = swift.read_text(encoding='utf-8')
    sources[swift.relative_to(app).as_posix()] = source
    literals.update(source_text(m.group(1)) for m in pattern.finditer(source))
    explicit.update(source_text(m.group(1)) for m in lookups.finditer(source))

strings = catalog['strings']
# An Int interpolation is keyed %lld by SwiftUI, a String one %@; the source scan sees both as %@.
def shape(key):
    return key.replace('%lld', '%@')
stale = [k for k in strings if shape(k) not in literals]
check(not stale, 'every translated text is still in the app' + (f' (stale: {stale[:5]})' if stale else ''))
missing = [(k, l) for k, v in strings.items() for l in languages
           if not v.get('localizations', {}).get(l, {}).get('stringUnit', {}).get('value')]
check(not missing, 'every text has all six languages' + (f' (missing: {missing[:5]})' if missing else ''))
def structure_matches(source, translated):
    # Preserve TYPES too: swapping %lld for %@ can crash a formatted lookup.
    # Literal percentages ("1% lows") are not interpolation placeholders.
    types = re.findall(r'%(lld|@)', source)
    expected = [(str(i + 1), kind) for i, kind in enumerate(types)]
    slots = re.findall(r'%(\d+)\$(lld|@)', translated)
    return (( '](' in source) == ('](' in translated)
            and source.count('\n') == translated.count('\n')
            and source.endswith(' ') == translated.endswith(' ')
            and sorted(slots, key=lambda slot: int(slot[0])) == expected
            and source.count('%') - len(types) == translated.count('%') - len(slots))


check(structure_matches('1% lows', '1% 低帧率')
      and structure_matches('%@ / %lld', '%2$lld / %1$@')
      and not structure_matches('%lld', '%1$@')
      and not structure_matches('%@ / %@', '%1$@ / %1$@')
      and not structure_matches('%@', '%2$@'),
      'placeholder checks accept literal percentages and reordered slots, but reject type/slot corruption')
broken = []
for k, v in strings.items():
    for l in languages:
        t = v.get('localizations', {}).get(l, {}).get('stringUnit', {}).get('value', '')
        if not structure_matches(k, t):
            broken.append((k[:30], l))
check(not broken, 'placeholders, links, line breaks and trailing spaces survive' + (f' ({broken[:5]})' if broken else ''))
explicit_missing = sorted(k for k in explicit if shape(k) not in {shape(s) for s in strings})
check(not explicit_missing, 'every explicit localization lookup has catalog translations'
      + (f' (missing: {explicit_missing[:5]})' if explicit_missing else ''))

# Dynamic names are ordinary Strings, not implicit SwiftUI localization keys.
# Saved identifiers and user names must stay untouched by the display helpers.
check('var displayName: String' in sources['TouchControlPresets.swift']
      and 'default: return name' in sources['TouchControlPresets.swift']
      and 'Label(p.displayName,' in sources['TouchControlPresets.swift']
      and 'Text(presets.active?.displayName ?? L("Custom"))' in sources['TouchControlPresets.swift'],
      'built-in layout names localize at display time; custom layout names remain literal')
check('Text($0.localizedLabel).tag($0.rawValue)' in sources['Library.swift']
      and 'Toggle(OverlayStyle.localizedName(field),' in sources['Library.swift']
      and 'model.overlayFields.contains(field)' in sources['Library.swift']
      and 'L(' not in sources['GuestDisplay.swift'],
      'display and overlay titles localize without changing saved values or the geometry core')
check('localizedTitle' in sources['JITSetup.swift']
      and 'header(_ title: LocalizedStringKey' in sources['Onboarding.swift']
      and 'primary(_ title: LocalizedStringKey' in sources['Onboarding.swift']
      and 'secondary(_ title: LocalizedStringKey' in sources['Onboarding.swift']
      and 'L("Steam and Dock")' in sources['SettingsPages.swift']
      and 'L("Enter the Steam Guard code shown in the Steam app on your phone.")' in sources['SwiftSteam/SteamSignInView.swift'],
      'onboarding, settings, JIT choices and nested Steam sign-in use localized titles')
check(len(strings) >= 700, f'{len(strings)} texts translated')

# Not a failure (other threads add texts every day), but listed so they can be translated:
# texts in Text("...")/L("...") and the like that the catalog does not have yet. A text with
# a call inside an interpolation, or with no letters, is left out.
shapes = {shape(k) for k in strings}
untranslated = sorted(t for t in literals if t not in shapes and re.search(r'[A-Za-z]{2}', t)
                      and not re.search(r'\\\(', t)
                      and not re.match(r'^[A-Za-z][A-Za-z0-9+.-]*://', t))
print(f'NOTE: {len(untranslated)} texts in the app have no translation yet (they show in English):')
for t in untranslated:
    print('  - ' + t.replace('\n', '\\n'))

print('FAIL' if failures else 'PASS')
sys.exit(1 if failures else 0)
