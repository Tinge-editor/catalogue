#!/usr/bin/env python3
"""Build the public v1 catalogue from approved free native packages."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

MAX_BYTES = 8_000_000
ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]*$')
FIELDS = {'id', 'version', 'name', 'description', 'author', 'license', 'categories', 'packagePath', 'sha256', 'status', 'price', 'redistributionApproved', 'rightsEvidence', 'listed'}
WIRE_FIELDS = ('id', 'version', 'name', 'description', 'author', 'license', 'categories', 'sha256')
# One-time owner-approved catalogue replacement. Exact snapshots only; later changes
# remain subject to the ordinary immutable-version checks.
APPROVED_RESET = ('27025e954cb3249c890d6cf3a2af234dae11876dc9a0948ec48d6c5c82e22c3b',
                  '3fa371924cac59959e2ba030cb77db78feb6cfbd0abdb55600b6e6444dde8dc8')


def source_digest(source):
    canonical = json.dumps(source, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    return hashlib.sha256(canonical).hexdigest()


def read_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f'duplicate JSON key: {key}')
            result[key] = value
        return result
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=pairs, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(f'invalid number {x}')))


def key(row):
    if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not ID.fullmatch(row['id']) or len(row['id'].encode()) > 64:
        raise ValueError('invalid preset id')
    if not isinstance(row.get('version'), str) or not ID.fullmatch(row['version']) or len(row['version'].encode()) > 24:
        raise ValueError('invalid version')
    return row['id'], row['version']


def load_source(path):
    source = read_json(path)
    if not isinstance(source, dict) or set(source) != {'catalogID', 'title', 'versions'} or not isinstance(source['versions'], list):
        raise ValueError('invalid source fields')
    if not isinstance(source['catalogID'], str) or not ID.fullmatch(source['catalogID']) or len(source['catalogID'].encode()) > 32:
        raise ValueError('invalid catalogue ID')
    if not isinstance(source['title'], str):
        raise ValueError('invalid title')
    seen = set()
    for row in source['versions']:
        k = key(row)
        if k in seen:
            raise ValueError(f'duplicate preset version {k}')
        seen.add(k)
        if row.get('status') != 'approved' or row.get('price') != 'free':
            raise ValueError(f'public source may contain only approved free versions: {k}')
    return source


def check_history(source, previous):
    if previous['catalogID'] != source['catalogID']:
        raise ValueError('catalogue identity changed')
    if (source_digest(previous), source_digest(source)) == APPROVED_RESET:
        return
    current = {key(row): row for row in source['versions']}
    for old in previous['versions']:
        if old['status'] != 'approved' or old['price'] != 'free':
            continue
        new = current.get(key(old))
        if new is None or {k: v for k, v in new.items() if k != 'listed'} != {k: v for k, v in old.items() if k != 'listed'}:
            raise ValueError(f'published version {key(old)} changed or removed; retain it and create a new version')


REPO = Path(__file__).resolve().parents[1]
# Experimental listing published beside, never inside, the production catalogue.
RESEARCH_SOURCE = REPO / 'experimental' / 'research-presets' / 'catalogue.json'
RESEARCH_OUTPUT = 'research-catalogue.json'
MANIFEST_FIELDS = {'formatVersion', 'catalogID', 'title', 'isDemo', 'looks'}


def load_research(path, production):
    """Return the experimental manifest bytes after structural checks; the validator runs later."""
    if path.stat().st_size > MAX_BYTES:
        raise ValueError('research catalogue exceeds 8 MB')
    data = path.read_bytes()
    manifest = read_json(path)
    if not isinstance(manifest, dict) or set(manifest) != MANIFEST_FIELDS or manifest['formatVersion'] != 1 or manifest['isDemo'] is not False or not isinstance(manifest['looks'], list):
        raise ValueError('invalid research catalogue header')
    catalog_id = manifest['catalogID']
    if not isinstance(catalog_id, str) or not ID.fullmatch(catalog_id) or len(catalog_id.encode()) > 32:
        raise ValueError('invalid research catalogue ID')
    if catalog_id in {'tinge', production['catalogID']} or manifest['title'] == production['title']:
        raise ValueError('research catalogue must not reuse the production catalogue identity')
    production_ids = {row['id'] for row in production['versions']}
    for look in manifest['looks']:
        if not isinstance(look, dict) or not isinstance(look.get('id'), str):
            raise ValueError('invalid research look')
        if look['id'] in production_ids or look['id'] == 'original' or look['id'].startswith('personal-'):
            raise ValueError(f'research look ID collides with a production or reserved ID: {look["id"]}')
    return data


def build(source_path, output, validator, previous_path=None, require_production=False, research_path=None):
    source_path = source_path.resolve()
    root = source_path.parent
    source = load_source(source_path)
    if previous_path:
        check_history(source, load_source(previous_path))
    if output.exists():
        raise ValueError('output already exists; choose a new directory')
    rows, assets, listing_ids, archived = [], [], set(), []
    for row in source['versions']:
        if row['status'] != 'approved' or row['price'] != 'free':
            continue
        if not FIELDS.issubset(row) or set(row) - FIELDS - {'lutEncoding'} or row['redistributionApproved'] is not True or not isinstance(row['rightsEvidence'], str) or not row['rightsEvidence'].strip() or not isinstance(row['listed'], bool):
            raise ValueError(f'missing approved metadata or redistribution evidence for {key(row)}')
        if not isinstance(row['packagePath'], str):
            raise ValueError('invalid package path')
        path = (root / row['packagePath']).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError(f'package missing or outside source root: {row["packagePath"]}')
        if path.stat().st_size > MAX_BYTES:
            raise ValueError('package exceeds 8 MB')
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if row['sha256'] != digest:
            raise ValueError(f'checksum mismatch for {key(row)}')
        try:
            preset_json = json.loads(data)
        except (UnicodeDecodeError, ValueError) as exc:
            raise ValueError(f'invalid package JSON for {key(row)}') from exc
        def luts(value):
            if isinstance(value, dict):
                if value.get('lut') is not None:
                    yield value['lut']
                for child in value.values():
                    yield from luts(child)
            elif isinstance(value, list):
                for child in value:
                    yield from luts(child)
        package_luts = list(luts(preset_json))
        if package_luts and row.get('lutEncoding') != {'input': 'sRGB', 'output': 'sRGB'}:
            raise ValueError(f'LUT input and output must both be explicitly confirmed sRGB for {key(row)}')
        for lut in package_luts:
            interpretation = lut.get('interpretation') if isinstance(lut, dict) else None
            if interpretation is not None and (not isinstance(interpretation, dict) or interpretation.get('input') != 'sRGB' or interpretation.get('output') != 'sRGB'):
                raise ValueError(f'LUT interpretation conflicts with sRGB catalogue metadata for {key(row)}')
        if 'lutEncoding' in row and row['lutEncoding'] != {'input': 'sRGB', 'output': 'sRGB'}:
            raise ValueError('unsupported LUT encoding')
        entry = {k: row[k] for k in WIRE_FIELDS}
        entry['package'] = base64.b64encode(data).decode('ascii')
        if not row['listed']:
            archived.append(entry)
        if row['listed']:
            if row['id'] in listing_ids:
                raise ValueError(f'duplicate listed preset ID {row["id"]}')
            listing_ids.add(row['id'])
            rows.append(entry)
        assets.append((f'assets/{row["id"]}/{row["version"]}/{digest}.json', data))
    rows.sort(key=lambda x: x['id'])
    if require_production and (source['catalogID'] != 'tinge' or not rows or any(x['id'] == 'original' or x['id'].startswith('personal-') for x in rows)):
        raise ValueError('first-party catalogue requires ID tinge and at least one non-reserved look')
    manifest = {'formatVersion': 1, 'catalogID': source['catalogID'], 'title': source['title'], 'isDemo': False, 'looks': rows}
    encoded = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    if len(encoded) > MAX_BYTES:
        raise ValueError('catalogue exceeds 8 MB')
    research = load_research(research_path, source) if research_path else None
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.catalogue-', dir=output.parent))
    try:
        (temporary / 'catalogue.json').write_bytes(encoded)
        # Publish only explicitly allowlisted, reviewed static pages.
        page = Path(__file__).resolve().parents[1] / 'public' / 'privacy.html'
        (temporary / 'privacy.html').write_bytes(page.read_bytes())
        notice = page.parent / 'preset-license.txt'
        (temporary / 'preset-license.txt').write_bytes(notice.read_bytes())
        (temporary / 'support.html').write_bytes((page.parent / 'support.html').read_bytes())
        for relative, data in assets:
            target = temporary / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        # Validate archived packages as single-entry manifests as well.
        for entry in archived:
            check = temporary / '.validate.json'
            check.write_text(json.dumps({**manifest, 'looks': [entry]}, ensure_ascii=False), encoding='utf-8')
            subprocess.run([str(validator), str(check)], check=True)
            check.unlink()
        subprocess.run([str(validator), str(temporary / 'catalogue.json')], check=True)
        if research is not None:
            # Copied byte for byte so the Pages URL serves exactly the reviewed file.
            (temporary / RESEARCH_OUTPUT).write_bytes(research)
            subprocess.run([str(validator), str(temporary / RESEARCH_OUTPUT)], check=True)
        os.rename(temporary, output)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--validator', type=Path, required=True)
    parser.add_argument('--previous', type=Path)
    args = parser.parse_args()
    try:
        research = RESEARCH_SOURCE if RESEARCH_SOURCE.is_file() else None
        build(args.source, args.output, args.validator.resolve(), args.previous, require_production=True, research_path=research)
    except (ValueError, KeyError, TypeError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'Catalogue build failed: {error}\n')
    print(f'Built {args.output}')


if __name__ == '__main__':
    main()
