import logging
import unittest

from google.appengine.datastore import datastore_stub_util  # noqa
from google.appengine.ext import ndb
from google.appengine.ext import testbed

class NDBUnitTest(unittest.TestCase):

    def setUp(self):
        # First, create an instance of the Testbed class.
        self.testbed = testbed.Testbed()
        # Then activate the testbed, which prepares the service stubs for use.
        self.testbed.activate()
        # Create a consistency policy that will simulate the High Replication
        # consistency model.
        self.policy = datastore_stub_util.PseudoRandomHRConsistencyPolicy(probability=0)
        # Initialize the datastore stub with this policy.
        self.testbed.init_datastore_v3_stub(consistency_policy=self.policy)
        # Initialize memcache stub too, since ndb also uses memcache
        self.testbed.init_memcache_stub()
        # Clear in-context cache before each test.
        ndb.get_context().clear_cache()

        logging.getLogger().setLevel(logging.INFO) # NDB is super verbose

    def tearDown(self):
        logging.getLogger().setLevel(logging.NOTSET)
        # Never forget to deactivate the testbed once the tests are
        # completed. Otherwise the original stubs will not be restored.
        self.testbed.deactivate()

    @ndb.transactional(xg=True)
    def _trans_put(self, ent):
        ent.put()
