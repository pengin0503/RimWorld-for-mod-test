import copy
import unittest
from tools import private_static_audit as audit

class ReasonTests(unittest.TestCase):
    def item(self):
        return {'token':0x06000001,'return':{'kind':'primitive','name':'Void'},'parameters':[],
                'genericCount':0,'static':False,'visibility':'Public','calls':[],'branches':[],'exceptions':[]}

    def test_normal_method_has_no_reasons(self):
        self.assertEqual(audit.method_reasons(self.item()), [])

    def test_multiple_failures_are_retained_without_private_values(self):
        item=self.item();item['return']={'kind':'named','name':'PRIVATE.Secret'}
        item['visibility']='PRIVATE';item['branches']=[{'offset':False,'target':1}]
        self.assertEqual(audit.method_reasons(item), ['invalidControlFlow','invalidVisibility','unsupportedTypeAtom'])

    def test_invalid_token_call_and_signature_have_distinct_reasons(self):
        for field,value,reason in [('token',False,'invalidMethodToken'),('calls',[{'offset':-1}],'invalidCallsite'),('parameters',None,'invalidSignature')]:
            item=self.item();item[field]=value
            self.assertIn(reason,audit.method_reasons(item))

    def test_unknown_schema_is_not_a_type_failure(self):
        item=self.item();item['PRIVATE']='secret'
        self.assertEqual(audit.method_reasons(item), ['invalidSchema'])

    def test_unknown_return_does_not_hide_invalid_parameter_shape(self):
        item=self.item();item['return']={'kind':'named','name':'PRIVATE.Secret'}
        item['parameters']=[{'kind':'array','rank':False,'element':{'kind':'primitive','name':'Int32'}}]
        self.assertEqual(audit.method_reasons(item), ['invalidSignature','unsupportedTypeAtom'])

    def test_public_summary_emits_only_fixed_reasons(self):
        identity={'runId':'100-1','commit':'a'*40}
        item=self.item();item['visibility']='PRIVATE';item['return']={'kind':'named','name':'PRIVATE.Secret'}
        raw={**identity,'verified':True,'types':[{'id':'game','found':True,'methods':[{'name':'InitNewGame','overloads':[item]},{'name':'FinalizeInit','overloads':[]}]}]}
        result=audit.public_summary(raw,identity)
        self.assertEqual(result['types'][0]['methods'][0]['reasons'],['invalidVisibility','unsupportedTypeAtom'])
        self.assertNotIn('PRIVATE',str(result));self.assertFalse(result['c0Passed'])
        self.assertEqual(result['staticAuditStatus'],'incomplete')

    def test_bad_generic_count_does_not_hide_parameter_failure(self):
        item=self.item();item['genericCount']=-1
        item['parameters']=[{'kind':'named','name':'PRIVATE.Secret'}]
        self.assertEqual(audit.method_reasons(item), ['invalidSignature','unsupportedTypeAtom'])

    def test_later_overload_keeps_its_fallback_reason(self):
        first=self.item();first['return']={'kind':'named','name':'PRIVATE.Secret'}
        second=self.item();second['parameters']=[{'kind':'named','name':'System.Collections.Generic.IEnumerable`1'} for _ in range(64)]
        identity={'runId':'100-1','commit':'a'*40}
        raw={**identity,'verified':True,'types':[{'id':'game','found':True,'methods':[{'name':'InitNewGame','overloads':[first,second]},{'name':'FinalizeInit','overloads':[]}]}]}
        result=audit.public_summary(raw,identity)
        self.assertEqual(result['types'][0]['methods'][0]['reasons'], ['invalidSignature','unsupportedTypeAtom'])

    def test_candidate_evidence_cannot_inject_private_schema(self):
        item=self.item();item['candidateReferences']=[{'id':'PRIVATE','kind':'definitionUse','arity':0}]
        self.assertEqual(audit.method_reasons(item), ['invalidSchema'])
