"""Fixed diagnostic enums; never return values from private metadata."""

def classify(item, normalize, primitives, atoms):
    reasons=set()
    if not isinstance(item,dict): return ['invalidSchema']
    allowed={'token','return','parameters','genericCount','static','visibility','calls','branches','exceptions','candidateReferences'}
    if not set(item).issubset(allowed): reasons.add('invalidSchema')
    if type(item.get('token')) is not int or not 0x06000001<=item['token']<=0x06ffffff: reasons.add('invalidMethodToken')
    if type(item.get('static')) is not bool or item.get('visibility') not in ('Public','Private','Family','Assembly','FamANDAssem','FamORAssem','PrivateScope'): reasons.add('invalidVisibility')
    def check_type(node,depth=0):
        if depth>=8: reasons.add('budgetExceeded');return
        if not isinstance(node,dict): reasons.add('invalidSignature');return
        kind=node.get('kind')
        shapes={'primitive':{'kind','name'},'named':{'kind','name'},'byref':{'kind','element'},'pointer':{'kind','element'},'array':{'kind','element','rank'},'generic':{'kind','element','arguments'},'methodParameter':{'kind','index'},'typeParameter':{'kind','index'}}
        if not isinstance(kind,str) or kind not in shapes: reasons.add('unsupportedTypeForm');return
        if set(node)!=shapes[kind]: reasons.add('invalidSignature')
        if kind in ('primitive','named'):
            name=node.get('name')
            if not isinstance(name,str): reasons.add('invalidSignature')
            elif name not in (primitives if kind=='primitive' else atoms): reasons.add('unsupportedTypeAtom')
        elif kind in ('byref','pointer','array','generic'):
            check_type(node.get('element'),depth+1)
            if kind=='array' and (type(node.get('rank')) is not int or not 1<=node['rank']<=32):reasons.add('invalidSignature')
            if kind=='generic':
                args=node.get('arguments')
                if not isinstance(args,list) or not args: reasons.add('invalidSignature')
                elif len(args)>32: reasons.add('budgetExceeded')
                else:
                    for arg in args:check_type(arg,depth+1)
        elif type(node.get('index')) is not int or not 0<=node['index']<32:reasons.add('invalidSignature')
    check_type(item.get('return'))
    params=item.get('parameters'); count=item.get('genericCount')
    if type(count) is not int or count<0: reasons.add('invalidSignature')
    elif count>32: reasons.add('budgetExceeded')
    if not isinstance(params,list): reasons.add('invalidSignature')
    elif len(params)>64: reasons.add('budgetExceeded')
    else:
        for param in params: check_type(param)
    def integer(value,maximum=65535):return type(value) is int and 0<=value<=maximum
    branches=item.get('branches',[]);regions=item.get('exceptions',[])
    if not isinstance(branches,list) or not isinstance(regions,list): reasons.add('invalidControlFlow')
    elif len(branches)>100000 or len(regions)>65536: reasons.add('budgetExceeded')
    else:
        for row in branches:
            if not isinstance(row,dict) or set(row)!={'offset','target'} or not all(integer(row[k]) for k in ('offset','target')):reasons.add('invalidControlFlow')
        keys={'kind','tryOffset','tryLength','handlerOffset','handlerLength'}
        for row in regions:
            if not isinstance(row,dict) or set(row)!=keys or row.get('kind') not in ('Catch','Filter','Finally','Fault') or not all(integer(row[k],65536) for k in keys-{'kind'}):reasons.add('invalidControlFlow')
    candidates=item.get('candidateReferences',[])
    if not isinstance(candidates,list):reasons.add('invalidSchema')
    elif len(candidates)>4096:reasons.add('budgetExceeded')
    else:
        ids={'action-1':1,'exception':0,'nullable-1':1,'bill':0,'incident-parms':0,'thing-category':0}
        for row in candidates:
            if not isinstance(row,dict) or set(row)!={'id','kind','arity'} or not isinstance(row.get('id'),str) or row['id'] not in ids or row.get('kind') not in ('reference','definitionUse') or type(row.get('arity')) is not int or row['arity']!=ids[row['id']]:reasons.add('invalidSchema')
    calls=item.get('calls')
    if not isinstance(calls,list):reasons.add('invalidCallsite')
    elif len(calls)>4096:reasons.add('budgetExceeded')
    else:
        for row in calls:
            if not isinstance(row,dict) or set(row)!={'offset','kind','target'} or not integer(row.get('offset')) or row.get('kind') not in ('call','callvirt','newobj') or not isinstance(row.get('target'),str):reasons.add('invalidCallsite')
    return sorted(reasons)
