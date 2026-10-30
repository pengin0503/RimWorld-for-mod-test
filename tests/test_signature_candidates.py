import unittest
from tools import private_static_audit as audit

class CandidateTests(unittest.TestCase):
    def test_candidate_requires_verified_source_and_target_definition(self):
        source={'module':'Assembly-CSharp.dll','sha256':audit.EXPECTED['Assembly-CSharp.dll'],'id':'exception','kind':'reference','arity':0}
        target={'module':'System.Private.CoreLib.dll','sha256':audit.EXPECTED['System.Private.CoreLib.dll'],'id':'exception','kind':'definition','arity':0}
        self.assertEqual(audit.candidate_summary([source,target]),[{'id':'exception','status':'matched'}])
        target['sha256']='0'*64
        self.assertEqual(audit.candidate_summary([source,target]),[{'id':'exception','status':'unresolved'}])

    def test_private_names_are_never_copied(self):
        self.assertEqual(audit.candidate_summary([{'id':'PRIVATE','module':'PRIVATE'}]),[])

    def test_wrong_assembly_arity_and_extra_key_are_rejected(self):
        base={'module':'Assembly-CSharp.dll','sha256':audit.EXPECTED['Assembly-CSharp.dll'],'id':'incident-parms','kind':'definitionUse','arity':0}
        for changes in [{'arity':1},{'module':'RimWorld.dll','sha256':audit.EXPECTED['RimWorld.dll']},{'PRIVATE':'secret'}]:
            self.assertEqual(audit.candidate_summary([{**base,**changes}]),[])

    def test_duplicate_definitions_remain_unresolved(self):
        source={'module':'Assembly-CSharp.dll','sha256':audit.EXPECTED['Assembly-CSharp.dll'],'id':'exception','kind':'reference','arity':0}
        target={'module':'System.Private.CoreLib.dll','sha256':audit.EXPECTED['System.Private.CoreLib.dll'],'id':'exception','kind':'definition','arity':0}
        self.assertEqual(audit.candidate_summary([source,target,target]),[{'id':'exception','status':'unresolved'}])
