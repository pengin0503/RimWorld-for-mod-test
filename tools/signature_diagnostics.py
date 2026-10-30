"""Bounded public positions of unsupported atoms, never their private names."""

# Hypotheses only: a name observation does not prove assembly resolution.
NAME_CANDIDATES = {'System.Collections.IEnumerator': 'ienumerator',
                   'Verse.ThingFilterUI+UIState': 'filter-ui-state'}


def valid_metadata(value):
    return (isinstance(value, dict) and set(value) == {'handle', 'scope', 'depth'}
            and value.get('handle') in ('definition', 'reference')
            and value.get('scope') in ('module', 'assembly', 'other')
            and type(value.get('depth')) is int and 0 <= value['depth'] < 8)


def unsupported_positions(overloads, atoms):
    rows = []
    truncated = False
    if not isinstance(overloads, list):
        return {'items': rows, 'truncated': False}
    for item in overloads[:16]:
        if not isinstance(item, dict):
            continue
        token = item.get('token')
        if type(token) is not int or not 0x06000001 <= token <= 0x06ffffff:
            continue
        roots = [(item.get('return'), {'token': token, 'site': 'return', 'path': []})]
        params = item.get('parameters')
        if isinstance(params, list):
            roots.extend((node, {'token': token, 'site': 'parameter', 'index': i, 'path': []})
                         for i, node in enumerate(params[:64]))
        stack = list(reversed(roots))
        visited = 0
        while stack:
            node, position = stack.pop()
            visited += 1
            if visited > 4096 or len(rows) >= 128:
                truncated = True
                break
            if len(position['path']) >= 8:
                truncated = True
                continue
            if not isinstance(node, dict):
                continue
            kind = node.get('kind')
            if kind == 'named' and isinstance(node.get('name'), str) and node['name'] not in atoms:
                row = dict(position)
                if node['name'] in NAME_CANDIDATES:
                    row['candidate'] = NAME_CANDIDATES[node['name']]
                if valid_metadata(node.get('metadata')):
                    row['metadata'] = dict(node['metadata'])
                rows.append(row)
            children = []
            if kind in ('byref', 'pointer', 'array', 'generic'):
                children.append((node.get('element'), {**position, 'path': [*position['path'], 'element']}))
            if kind == 'generic' and isinstance(node.get('arguments'), list):
                children.extend((arg, {**position, 'path': [*position['path'], i]})
                                for i, arg in enumerate(node['arguments'][:32]))
            stack.extend(reversed(children))
    return {'items': rows, 'truncated': truncated}
