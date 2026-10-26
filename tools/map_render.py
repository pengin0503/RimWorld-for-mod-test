"""Schematic top-down image and summary of a generated map (rwmtMapObservation).

The Worker writes what the game generated (terrain, roofs, things per cell, def
palettes with their mods). This module draws one coloured square per cell; it
does not use the game's textures or renderer, so the picture shows *what* is
where, not how the game would draw it. Content of the target mods is drawn in
magenta so new structures stand out. Standard library only.
"""
from __future__ import annotations

import base64
import hashlib
from pathlib import Path
import struct
import zlib

TARGET_THING = (255, 0, 255)
TARGET_TERRAIN = (255, 140, 255)
LEGEND = (
    ('targetThing', 'thing from a target mod', TARGET_THING),
    ('targetTerrain', 'terrain from a target mod', TARGET_TERRAIN),
    ('building', 'building (not natural rock)', (205, 95, 60)),
    ('naturalRock', 'natural rock', (72, 70, 68)),
    ('resourceRock', 'mineable resource', (215, 170, 60)),
    ('item', 'item', (245, 215, 80)),
    ('chunk', 'stone chunk or slag', (165, 158, 148)),
    ('colonist', 'pawn of the player faction', (60, 205, 235)),
    ('humanlike', 'other humanlike pawn', (235, 55, 55)),
    ('animal', 'animal or other pawn', (170, 110, 55)),
    ('tree', 'tree', (40, 95, 40)),
    ('plant', 'other plant (tints the ground green)', (95, 150, 70)),
    ('deepWater', 'deep water', (30, 70, 140)),
    ('water', 'shallow/moving water', (70, 120, 190)),
    ('ice', 'ice', (220, 235, 245)),
    ('rockFloor', 'natural stone floor', (125, 120, 114)),
    ('constructedFloor', 'constructed floor', (190, 170, 140)),
    ('richSoil', 'rich soil', (90, 70, 45)),
    ('soil', 'soil', (125, 98, 66)),
    ('poorSoil', 'gravel / stony soil', (150, 132, 98)),
    ('sand', 'sand / no fertility', (205, 190, 145)),
    ('otherTerrain', 'other terrain (colour from its defName)', None),
)
COLORS = {key: color for key, _, color in LEGEND}


class ObservationError(ValueError):
    """The observation file is not a readable rwmtMapObservation."""


def decode(observation):
    if observation.get('recordType') != 'rwmtMapObservation' or observation.get('schemaVersion') != 1:
        raise ObservationError('not a rwmtMapObservation v1')
    width, height = observation['width'], observation['height']
    cells = width * height
    layers = observation['layers']
    terrain = base64.b64decode(layers['terrain'])
    roof = base64.b64decode(layers['roof'])
    thing = base64.b64decode(layers['thing'])
    if len(terrain) != 2 * cells or len(roof) != cells or len(thing) != 2 * cells:
        raise ObservationError('layer sizes do not match the map size')
    return (width, height, struct.unpack(f'<{cells}H', terrain), roof, struct.unpack(f'<{cells}H', thing))


def _named_color(name):
    digest = hashlib.sha256(name.encode()).digest()
    return tuple(60 + b % 150 for b in digest[:3])


def terrain_class(entry):
    name = entry['defName'] or ''
    if entry['water']:
        return 'deepWater' if 'Deep' in name else 'water'
    if entry['ice']:
        return 'ice'
    if entry['constructed'] or (entry['floor'] and not entry['natural']):
        return 'constructedFloor'
    if entry['rock']:
        return 'rockFloor'
    fertility = entry['fertility']
    if entry['natural'] and fertility is not None and fertility >= 0:
        if fertility >= 1.2:
            return 'richSoil'
        if fertility >= 1.0:
            return 'soil'
        if fertility >= 0.5:
            return 'poorSoil'
        if fertility < 0.2:
            return 'sand'
    return 'otherTerrain'


def thing_class(entry, listed_player):
    category = entry['category']
    if category == 'Pawn':
        if entry['humanlike']:
            return 'colonist' if listed_player else 'humanlike'
        return 'animal'
    if category == 'Building':
        if entry['resourceRock']:
            return 'resourceRock'
        return 'naturalRock' if entry['naturalRock'] else 'building'
    if category == 'Item':
        return 'chunk' if entry.get('chunk') else 'item'
    if category == 'Plant':
        return 'tree' if entry['tree'] else 'plant'
    return None


def _terrain_color(entry, cls):
    if cls == 'constructedFloor' and entry.get('color') and entry['color'][:3] != [1.0, 1.0, 1.0]:
        return tuple(int(40 + 180 * c) for c in entry['color'][:3])
    color = COLORS[cls]
    return color if color is not None else _named_color(entry['defName'] or '?')


def _blend(base, top, amount):
    return tuple(int(b + (t - b) * amount) for b, t in zip(base, top))


def render(observation, targets, scale=2):
    """Return (png bytes, legend counts in cells) for the observation; targets are packageIds."""
    width, height, terrain, roof, thing = decode(observation)
    palettes = observation['palettes']
    targets = {t.lower() for t in targets}
    player_pawns = {}
    for listed in observation.get('things', []):
        x0, z0, x1, z1 = listed['rect']
        if listed.get('playerFaction'):
            for z in range(z0, z1 + 1):
                for x in range(x0, x1 + 1):
                    player_pawns[z * width + x] = True
    terrain_info = []
    for entry in palettes['terrain']:
        if entry.get('mod') in targets:
            terrain_info.append(('targetTerrain', TARGET_TERRAIN))
        else:
            cls = terrain_class(entry)
            terrain_info.append((cls, _terrain_color(entry, cls)))
    roofs = [None] + palettes['roof']
    things = [None] + palettes['thing']
    counts = {}
    rows = []
    for z in range(height - 1, -1, -1):  # z=0 is the south edge: the bottom of the image
        row = bytearray()
        for x in range(width):
            cell = z * width + x
            cls, color = terrain_info[terrain[cell]]
            entry = things[thing[cell]]
            if entry is not None:
                if entry.get('mod') in targets:
                    cls, color = 'targetThing', TARGET_THING
                else:
                    tcls = thing_class(entry, player_pawns.get(cell, False))
                    if tcls == 'plant':
                        cls, color = 'plant', _blend(color, COLORS['plant'], 0.45)
                    elif tcls is not None:
                        cls, color = tcls, COLORS[tcls]
            roof_entry = roofs[roof[cell]]
            if roof_entry is not None and cls not in ('naturalRock', 'resourceRock', 'targetThing', 'targetTerrain'):
                color = _blend(color, (0, 0, 0), 0.4 if roof_entry['thick'] else 0.2)
            counts[cls] = counts.get(cls, 0) + 1
            row.extend(bytes(color) * scale)
        for _ in range(scale):
            rows.append(bytes(row))
    legend = [{'key': key, 'label': label, 'color': list(c) if c else None, 'cells': counts[key]}
              for key, label, c in LEGEND if counts.get(key)]
    legend.append({'key': 'roof', 'label': 'roofed cell (darker)', 'color': None,
                   'cells': sum(e['cells'] for e in palettes['roof'])})
    return png(width * scale, height * scale, rows), legend


def png(width, height, rows):
    """Encode 8-bit RGB rows as a PNG."""
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    raw = b''.join(b'\x00' + row for row in rows)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def summarize(observation, targets, max_listed=200):
    """Counts per mod and the target mods' content, for result.json."""
    targets = {t.lower() for t in targets}
    palettes = observation['palettes']
    by_mod = {}
    for kind in ('thing', 'terrain'):
        for entry in palettes[kind]:
            key = 'things' if kind == 'thing' else 'terrainCells'
            amount = entry['count'] if kind == 'thing' else entry['cells']
            stats = by_mod.setdefault(entry.get('mod') or 'unknown', {'things': 0, 'terrainCells': 0})
            stats[key] += amount
    things = [None] + palettes['thing']
    target_things = [{'defName': e['defName'], 'mod': e['mod'], 'category': e['category'], 'count': e['count']}
                     for e in palettes['thing'] if e.get('mod') in targets]
    target_terrain = [{'defName': e['defName'], 'mod': e['mod'], 'cells': e['cells']}
                      for e in palettes['terrain'] if e.get('mod') in targets]
    placed = []
    for listed in observation.get('things', []):
        entry = things[listed['def']]
        if entry.get('mod') in targets and len(placed) < max_listed:
            placed.append({'defName': entry['defName'], 'mod': entry['mod'], 'x': listed['x'], 'z': listed['z'],
                           'rect': listed['rect'], 'rotation': listed['rotation'], 'faction': listed.get('faction'),
                           'stuff': listed.get('stuff')})
    listed_target = sum(1 for l in observation.get('things', []) if things[l['def']].get('mod') in targets)
    return {
        'byMod': dict(sorted(by_mod.items())),
        'targetThings': target_things,
        'targetTerrain': target_terrain,
        'targetPlacements': placed,
        'targetPlacementsOmitted': max(0, listed_target - len(placed)),
        'genStepsFromTargets': [g for g in observation.get('genSteps', []) if g.get('mod') in targets],
    }


def count_def(observation, def_type, def_name):
    """Things on the map with this ThingDef, or cells with this TerrainDef."""
    if def_type == 'TerrainDef':
        return sum(e['cells'] for e in observation['palettes']['terrain'] if e['defName'] == def_name)
    return sum(e['count'] for e in observation['palettes']['thing'] if e['defName'] == def_name)


def write_png(path, data):
    Path(path).write_bytes(data)
