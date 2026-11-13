#!/usr/bin/env python3
"""Portable structural/integrity check; not a replacement for the iOS validator."""
import base64
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import sys

MAX_BYTES = 8_000_000
ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]*$')
CATEGORIES = {'Subtle', 'Natural', 'Film', 'Creative'}
# Highest engine the current Tinge app renders; keep in step with Preset.supportedEngineVersions.
MAX_ENGINE = 11


def number(value, low, high):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def curve(points):
    return (isinstance(points, list) and len(points) == 5 and all(number(v, 0, 1) for v in points)
            and all(a <= b for a, b in zip(points, points[1:])))


def point_curve(points):
    """2–16 [x, y] points in 0…1, x strictly increasing and y non-decreasing (engine 11)."""
    return (isinstance(points, list) and 2 <= len(points) <= 16
            and all(isinstance(p, list) and len(p) == 2 and number(p[0], 0, 1) and number(p[1], 0, 1) for p in points)
            and all(a[0] < b[0] and a[1] <= b[1] for a, b in zip(points, points[1:])))


def tones(entries, count):
    return (isinstance(entries, list) and len(entries) == count and all(
        isinstance(e, dict) and set(e) == {'hue', 'saturation', 'luminance'} for e in entries))


def grading(value):
    return (isinstance(value, dict) and set(value) == {'tones', 'blending', 'balance'} and tones(value['tones'], 4)
            and all(number(t['hue'], 0, 1) and number(t['saturation'], 0, 1) and number(t['luminance'], -1, 1) for t in value['tones'])
            and number(value['blending'], 0, 1) and number(value['balance'], -1, 1))


# Field -> (first engine version that has it, check). Each new engine-11 dial adds its entry here.
ADVANCED_FIELDS = {
    'red': (5, lambda v: number(v, 0.5, 1.5)),
    'green': (5, lambda v: number(v, 0.5, 1.5)),
    'blue': (5, lambda v: number(v, 0.5, 1.5)),
    'curve': (5, curve),
    'highlights': (6, lambda v: number(v, -1, 1)),
    'shadows': (6, lambda v: number(v, -1, 1)),
    'colorMix': (6, lambda v: tones(v, 8) and all(all(number(e[k], -1, 1) for k in e) for e in v)),
    'channelCurves': (6, lambda v: isinstance(v, list) and len(v) == 3 and all(curve(c) for c in v)),
    'whites': (7, lambda v: number(v, -1, 1)),
    'blacks': (7, lambda v: number(v, -1, 1)),
    'grainSize': (8, lambda v: number(v, 0, 1)),
    'grainRoughness': (8, lambda v: number(v, 0, 1)),
    'colorGrading': (8, grading),
    'vibrance': (11, lambda v: number(v, -1, 1)),
    'vignette': (11, lambda v: number(v, -1, 1)),
    'vignetteMidpoint': (11, lambda v: number(v, 0, 1)),
    'monochrome': (11, lambda v: isinstance(v, list) and len(v) == 8 and all(number(x, -1, 1) for x in v)),
    'warmth': (11, lambda v: number(v, -1, 1)),
    'tint': (11, lambda v: number(v, -1, 1)),
    'halation': (11, lambda v: number(v, 0, 1)),
    'halationThreshold': (11, lambda v: number(v, 0, 1)),
    'bloom': (11, lambda v: number(v, 0, 1)),
    'bloomThreshold': (11, lambda v: number(v, 0, 1)),
    'grainColor': (11, lambda v: number(v, 0, 1)),
    'curvePoints': (11, point_curve),
    'channelCurvePoints': (11, lambda v: isinstance(v, list) and len(v) == 3 and all(point_curve(c) for c in v)),
    'clarity': (11, lambda v: number(v, -1, 1)),
    'filmToe': (11, lambda v: number(v, 0, 1)),
    'filmShoulder': (11, lambda v: number(v, 0, 1)),
    'calibration': (11, lambda v: isinstance(v, list) and len(v) == 3 and all(
        isinstance(p, dict) and set(p) == {'hue', 'saturation'} and number(p['hue'], -1, 1) and number(p['saturation'], -1, 1) for p in v)),
}


def check_advanced(advanced, engine):
    require(engine >= 5 and isinstance(advanced, dict), 'invalid advanced adjustments')
    require({'red', 'green', 'blue', 'curve'} <= set(advanced), 'advanced adjustments need red, green, blue and curve')
    for field, value in advanced.items():
        require(field in ADVANCED_FIELDS, f'unsupported advanced field {field}')
        first, check = ADVANCED_FIELDS[field]
        if value is None:
            continue
        require(engine >= first, f'advanced field {field} needs engine {first}')
        require(check(value), f'invalid advanced field {field}')
    # Point curves replace the five-value curves, which must then be neutral or absent, as in the app.
    if advanced.get('curvePoints') is not None:
        require(advanced['curve'] == [0, 0.25, 0.5, 0.75, 1], 'curvePoints needs a neutral curve')
    if advanced.get('channelCurvePoints') is not None:
        require(advanced.get('channelCurves') is None, 'channelCurvePoints replaces channelCurves')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_preset(preset, depth=0):
    require(isinstance(preset, dict) and depth <= 31, 'invalid preset nesting')
    schema, engine = preset.get('schemaVersion'), preset.get('engineVersion')
    require(type(schema) is int and type(engine) is int and schema == engine and 1 <= schema <= MAX_ENGINE, 'unsupported schema or engine')
    for name in ('id', 'name'):
        require(isinstance(preset.get(name), str) and 0 < len(preset[name]) <= 128, 'invalid preset identity')
    require(isinstance(preset.get('description'), str) and len(preset['description']) <= 4096, 'invalid description')
    adj = preset.get('adjustments')
    bounds = {'exposure': (-2, 2), 'contrast': (0.5, 1.5), 'saturation': (0, 2), 'temperature': (-1500, 1500), 'tint': (-100, 100)}
    require(isinstance(adj, dict) and set(adj) == set(bounds), 'invalid adjustment fields')
    for field, (low, high) in bounds.items():
        v = adj[field]
        require(type(v) in (int, float) and math.isfinite(v) and low <= v <= high, 'invalid adjustment range')
    if preset.get('advanced') is not None:
        check_advanced(preset['advanced'], engine)
    if preset.get('base') is not None:
        require(isinstance(preset['base'], list) and len(preset['base']) <= 1, 'invalid base')
        for child in preset['base']:
            check_preset(child, depth + 1)
    if preset.get('lut') is not None:
        lut = preset['lut']
        require(schema >= 5 and isinstance(lut, dict), 'invalid LUT')
        size = lut.get('dimension')
        require(type(size) is int and 2 <= size <= 33, 'invalid LUT size')
        raw = base64.b64decode(lut.get('rgba', ''), validate=True)
        require(len(raw) == size ** 3 * 16, 'invalid LUT sample count')
        for i, (value,) in enumerate(struct.iter_unpack('<f', raw)):
            require(math.isfinite(value) and 0 <= value <= 1 and (i % 4 != 3 or value == 1), 'invalid LUT sample')


def main(path):
    data = Path(path).read_bytes()
    require(len(data) <= MAX_BYTES, 'manifest too large')
    root = json.loads(data, parse_constant=lambda x: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
    require(isinstance(root, dict) and set(root) == {'formatVersion', 'catalogID', 'title', 'isDemo', 'looks'} and root['formatVersion'] == 1 and root['isDemo'] is False, 'invalid catalogue header')
    require(isinstance(root['catalogID'], str) and ID.fullmatch(root['catalogID']) and len(root['catalogID']) <= 32, 'invalid catalogue ID')
    require(isinstance(root['title'], str) and root['title'].strip() and len(root['title']) <= 100, 'invalid catalogue title')
    require(isinstance(root['looks'], list) and len(root['looks']) <= 100, 'invalid look count')
    seen = set()
    for look in root['looks']:
        require(isinstance(look, dict) and set(look) == {'id','version','name','description','author','license','categories','sha256','package'}, 'invalid look fields')
        for name, maximum in [('id', 64), ('version', 24)]:
            require(isinstance(look[name], str) and ID.fullmatch(look[name]) and len(look[name]) <= maximum, 'invalid look identity')
        require(look['id'] not in seen, 'duplicate look ID')
        seen.add(look['id'])
        for name, maximum in [('name',64), ('description',2000), ('author',256), ('license',1024)]:
            v=look[name]
            require(isinstance(v,str) and v.strip() and len(v) <= maximum and not any(ord(c)<32 and c!='\n' for c in v), 'invalid look text')
        cats = look['categories']
        require(isinstance(cats,list) and 0 < len(cats) <= 4 and all(isinstance(c,str) for c in cats) and len(cats)==len(set(cats)) and set(cats)<=CATEGORIES, 'invalid categories')
        package = base64.b64decode(look['package'], validate=True)
        require(len(package) <= MAX_BYTES and hashlib.sha256(package).hexdigest() == look['sha256'], 'package checksum mismatch')
        presets = json.loads(package, parse_constant=lambda x: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
        require(isinstance(presets,list) and len(presets)==1, 'package must contain one preset')
        check_preset(presets[0])
    print(f'Portable checks passed for {len(root["looks"])} looks; independent iOS validation is required.')


if __name__ == '__main__':
    try:
        if len(sys.argv) != 2:
            raise ValueError('usage: verify_manifest.py CATALOGUE.json')
        main(sys.argv[1])
    except (ValueError, TypeError, KeyError, OSError, RecursionError) as error:
        print(f'Invalid catalogue: {error}', file=sys.stderr)
        sys.exit(1)
