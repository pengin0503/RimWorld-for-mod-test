"""Fail-closed input planning for the qualified 1.7.4985 Linux loader.

Rules are paraphrased in docs/research/2026-10-26-load-folder-rules.md.
No game implementation or private assets are included here.
"""
import re
import xml.etree.ElementTree as ET

CURRENT = (1, 7, 4985)

class LoadPlanError(ValueError):
    def __init__(self, code, detail):
        self.code = code
        super().__init__(detail)


def parse_xml(data):
    if b'\x00' in data or len(data) > 4 * 1024 * 1024 or b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise LoadPlanError('unsafeMetadataXml', 'Metadata XML exceeds limits or declares entities')
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise LoadPlanError('invalidMetadataXml', 'Metadata XML cannot be parsed') from exc


def _version(name):
    if not re.fullmatch(r'\d+\.\d+(?:\.\d+)?', name):
        raise LoadPlanError('unsupportedLoadFolderVersion', 'Unsupported load-folder version')
    parts = tuple(map(int, name.split('.')))
    return parts + (0,) * (3-len(parts))


def _condition(item, active):
    if item.tag != 'li' or list(item) or set(item.attrib) - {'IfModActive','IfModActiveAll','IfModNotActive'}:
        raise LoadPlanError('unsupportedLoadFolderCondition', 'Unsupported load-folder entry or condition')
    enabled = True
    for name, value in item.attrib.items():
        ids = [x.strip().casefold() for x in value.split(',')]
        if any(not re.fullmatch(r'[a-z0-9_.]+', x) for x in ids):
            raise LoadPlanError('unsupportedLoadFolderCondition', 'Malformed package IDs in load-folder condition')
        matches = [x in active for x in ids]
        enabled &= (all(matches) if name == 'IfModActiveAll' else not any(matches) if name == 'IfModNotActive' else any(matches))
    return enabled


def load_folders(paths, xml, active):
    """Return game precedence order (highest first), relative to the MOD root."""
    active = {x.casefold() for x in active}
    directories = {''}
    for path in paths:
        bits = path.split('/')
        if any(x in ('','.', '..') for x in bits) or '\\' in path:
            raise LoadPlanError('unsafeLoadFolderPath', 'Unsafe object path')
        directories.update('/'.join(bits[:n]) for n in range(1,len(bits)))
    if xml is not None:
        doc = parse_xml(xml)
        if doc.tag != 'loadFolders' or doc.attrib or (doc.text or '').strip():
            raise LoadPlanError('invalidLoadFolders', 'Unsupported LoadFolders root')
        sections = {}
        for section in doc:
            if (section.text or '').strip() or (section.tail or '').strip() or any((li.tail or '').strip() for li in section):
                raise LoadPlanError('invalidLoadFolders', 'Unparsed text in load-folder definition')
            name = section.tag.lower().removeprefix('v')
            if name != 'default': _version(name)
            if name in sections or section.attrib:
                raise LoadPlanError('invalidLoadFolders', 'Duplicate or attributed LoadFolders version')
            sections[name] = section
            for item in section: _condition(item, active)
        selected = sections.get('1.7.4985')
        if selected is None or not len(selected):
            eligible = sorted((n for n in sections if n!='default' and _version(n)<=CURRENT),reverse=True)
            selected = sections[eligible[0]] if eligible else sections.get('default')
        if selected is not None:
            roots = []
            for item in reversed(list(selected)):
                if not _condition(item, active): continue
                name = item.text or ''
                if name in ('/','\\','.'): name = ''
                elif name != name.strip() or '\\' in name or name.startswith('/') or any(p in ('','.', '..') for p in name.split('/')) or ':' in name:
                    raise LoadPlanError('unsafeLoadFolderPath', 'Unsafe load-folder path')
                if name not in directories:
                    raise LoadPlanError('missingLoadFolder', 'Selected load folder is absent from R2 listing')
                roots.append(name)
            if not roots:
                raise LoadPlanError('emptyLoadFolders', 'No active load folders')
            return list(dict.fromkeys(roots))
        if sections:
            # The game falls through to its default directory policy here.
            pass
    candidates = []
    for name in directories:
        if '/' in name or not re.match(r'^\d+\.\d+', name): continue
        if not re.fullmatch(r'\d+\.\d+',name):
            raise LoadPlanError('unsupportedVersionDirectory','Version directory cannot be reproduced safely')
        if int(name.split(".")[0]) > 0:
            candidates.append(name)
    roots=[]
    if '1.7' in directories: roots.append('1.7')
    elif candidates:
        older=[n for n in candidates if _version(n)<=CURRENT]
        choice=max(older,key=_version) if older else min(candidates,key=_version)
        if str(int(choice.split('.')[0]))+'.'+str(int(choice.split('.')[1])) != choice:
            raise LoadPlanError('unsupportedVersionDirectory','Noncanonical version directory')
        roots.append(choice)
    if 'Common' in directories: roots.append('Common')
    return roots+['']


def select_asset(relative, folders, language):
    for folder in folders:
        prefix=folder+'/' if folder else ''
        if not relative.startswith(prefix): continue
        parts=relative[len(prefix):].split('/')
        if len(parts)<2: continue
        top=parts[0].casefold();name=parts[-1].casefold()
        if top in ('defs','patches') and name.endswith('.xml'): return True
        if top=='assemblies' and name.endswith('.dll'): return True
        # Def initialization constructs graphics during A; missing textures are real load errors.
        if top=='textures' and name.endswith(('.png','.jpg','.jpeg','.tga','.dds','.psd')): return True
        if top=='sounds' and name.endswith(('.wav','.ogg','.mp3','.aif','.aiff','.flac')): return True
        if top=='languages' and len(parts)>=3 and name.endswith(('.xml','.txt')):
            if any(parts[1].casefold()==x or parts[1].casefold().startswith(x+' (') for x in {'english',language.casefold()}): return True
    return False


def missing_dependencies(metadata, active):
    if metadata.tag != 'ModMetaData':
        raise LoadPlanError('invalidModMetadata','Unsupported About root')
    active={x.casefold() for x in active}
    for tag in ('modDependencies', 'modDependenciesByVersion'):
        if len(metadata.findall(tag)) > 1:
            raise LoadPlanError('invalidDependencies', 'Duplicate dependency sections')
    generic=metadata.find('modDependencies')
    versions=metadata.find('modDependenciesByVersion')
    section=generic
    if versions is not None:
        if versions.attrib or (versions.text or '').strip():
            raise LoadPlanError('invalidDependencies', 'Malformed versioned dependency list')
        seen=set()
        for item in versions:
            name=item.tag.lower().removeprefix('v')
            if item.attrib or (item.text or '').strip() or any((li.tail or '').strip() for li in item):
                raise LoadPlanError('invalidDependencies', 'Malformed versioned dependency section')
            if name in seen: raise LoadPlanError('invalidDependencies','Duplicate versioned dependencies')
            seen.add(name)
            if name=='1.7': section=item
    missing=[]
    if section is not None:
        if section.attrib or (section.text or '').strip() or any((li.tail or '').strip() for li in section):
            raise LoadPlanError('invalidDependencies', 'Malformed dependency list')
        for item in section:
            name=(item.findtext('packageId') or '').strip()
            if item.tag!='li' or item.attrib or not re.fullmatch(r'[A-Za-z0-9_.]+',name):
                raise LoadPlanError('invalidDependencies','Malformed dependency metadata')
            if name.casefold() not in active: missing.append(name)
    return missing
