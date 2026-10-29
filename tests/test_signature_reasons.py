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
