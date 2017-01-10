import datetime
import hashlib
import logging

from google.appengine.ext import ndb

from ndb_audit import Audit, AuditMixin, Tag, audit_put_multi_async
from test import NDBUnitTest


class FooInsideModel(ndb.Model):
    foo = ndb.StringProperty()
    bar = ndb.IntegerProperty()

class FooStructuredModel(AuditMixin, ndb.Model):
    foo = ndb.StringProperty()
    bar = ndb.IntegerProperty()
    baz = ndb.StructuredProperty(FooInsideModel, repeated=True)

    def _account(self):
        return 'foo-structured-account'


class NDBAuditUnitTest(NDBUnitTest):

    class FooExpando(AuditMixin, ndb.Expando):

        def _account(self):
            return 'foo-account'

    class FooModel(AuditMixin, ndb.Model):
        foo = ndb.StringProperty()
        bar = ndb.IntegerProperty()

        def _account(self):
            return 'foo-account'

    _TEST_CLASSES = [FooExpando, FooModel]

    def test_audit_create_from_entity(self):
        for cls in self._TEST_CLASSES:
            ent = cls(key=ndb.Key(cls.__name__, 'parentfoo'), foo='a', bar=1)
            self._trans_put(ent)
            expected_data_hash = hashlib.sha1('{v1}bar=1|foo=a').hexdigest()[0:8]
            expected_rev_hash = hashlib.sha1('{v1}None|foo-account|%s' % expected_data_hash).hexdigest()[0:8]
            self.assertEqual(ent.data_hash, expected_data_hash)
            self.assertEqual(ent.rev_hash, expected_rev_hash)

            a = Audit.create_from_entity(ent, None, 'foo-account', '0123456789abcdefghijk')
            self.assertIsInstance(a.timestamp, datetime.datetime) # can't accurately check autogen of this
            self.assertEqual(a.kind, str(ent._get_kind()))
            self.assertEqual(hashlib.sha1(a.key.string_id()).hexdigest()[0:8], expected_rev_hash)
            self.assertEqual(a.data_hash, expected_data_hash)
            self.assertEqual(a.account, 'foo-account')
            self.assertEqual(a.request_id, '0123456789abcdef')
            self.assertEqual(a.foo, 'a')
            self.assertEqual(a.bar, 1)
            self.assertEqual(a.key.parent(), ent.key)

    def test_audit_query_by_entity_key(self):
        for cls in self._TEST_CLASSES:
            fookey = ndb.Key(cls.__name__, 'parentfoo')
            ent1 = cls(key=fookey, foo='a', bar=1)
            self._trans_put(ent1)
            ent2 = fookey.get()
            ent2.foo = 'b'
            ent2.bar = 2
            self._trans_put(ent2)
            q1 = Audit.query_by_entity_key(fookey)
            a_list = list(q1)
            logging.info(a_list)
            expected_data_hash1 = hashlib.sha1('{v1}bar=1|foo=a').hexdigest()[0:8]
            first_hash = hashlib.sha1('{v1}None|foo-account|%s' % expected_data_hash1).hexdigest()[0:8]
            self.assertEqual(a_list[0].foo, 'b')
            self.assertEqual(a_list[0].bar, 2)
            self.assertEqual(a_list[0].data_hash, hashlib.sha1('{v1}bar=2|foo=b').hexdigest()[0:8])
            self.assertEqual(a_list[0].parent_hash, first_hash)
            self.assertEqual(a_list[1].foo, 'a')
            self.assertEqual(a_list[1].bar, 1)
            self.assertEqual(a_list[1].rev_hash, first_hash)
            self.assertGreater(a_list[0].timestamp, a_list[1].timestamp)

    def test_blind_put(self):
        for cls in self._TEST_CLASSES:
            fookey = ndb.Key(cls.__name__, 'parentfoo')
            ent1 = cls(key=fookey, foo='a', bar=1)
            self._trans_put(ent1)
            self.assertEqual(ent1.data_hash, hashlib.sha1('{v1}bar=1|foo=a').hexdigest()[0:8])
            ent2 = cls(key=fookey, foo='b', bar=2)
            self._trans_put(ent2)
            self.assertEqual(ent2.data_hash, hashlib.sha1('{v1}bar=2|foo=b').hexdigest()[0:8])
            self.assertEqual(ent2.foo, 'b')
            self.assertEqual(ent2.bar, 2)

            # audit entity for ent2 should have None parent_hash since it was not based on any previous
            # revision of the entity
            a2 = Audit.query_by_entity_key(ent2).fetch(1)[0]
            self.assertEqual(a2.parent_hash, None)

    @ndb.toplevel
    @ndb.transactional(xg=True)
    def t_put_multi(self, ent_list):
        audit_put_multi_async(ent_list)

    def test_put_multi(self):
        for cls in self._TEST_CLASSES:
            fookey1 = ndb.Key(cls.__name__, 'parentfoo1')
            fookey2 = ndb.Key(cls.__name__, 'parentfoo2')
            ent1 = cls(key=fookey1, foo='a', bar=1)
            expected_data_hash1 = hashlib.sha1('{v1}bar=1|foo=a').hexdigest()[0:8]
            expected_rev_hash1 = hashlib.sha1('{v1}None|foo-account|%s' % expected_data_hash1).hexdigest()[0:8]
            ent2 = cls(key=fookey2, foo='b', bar=2)
            expected_data_hash2 = hashlib.sha1('{v1}bar=2|foo=b').hexdigest()[0:8]
            expected_rev_hash2 = hashlib.sha1('{v1}None|foo-account|%s' % expected_data_hash2).hexdigest()[0:8]
            self.t_put_multi([ent1, ent2])
            self.assertEqual(ent1.data_hash, expected_data_hash1)
            self.assertEqual(ent1.rev_hash, expected_rev_hash1)
            self.assertEqual(ent2.data_hash, expected_data_hash2)
            self.assertEqual(ent2.rev_hash, expected_rev_hash2)
            a1 = Audit.build_audit_record_key(fookey1, expected_data_hash1, None, 'foo-account').get()
            a2 = Audit.build_audit_record_key(fookey2, expected_data_hash2, None, 'foo-account').get()
            self.assertEqual(a1.foo, 'a')
            self.assertEqual(a1.data_hash, expected_data_hash1)
            self.assertEqual(a1.rev_hash, expected_rev_hash1)
            self.assertEqual(a2.bar, 2)
            self.assertEqual(a2.data_hash, expected_data_hash2)
            self.assertEqual(a2.rev_hash, expected_rev_hash2)

    def test_put_when_data_unchanged(self):
        # if we are putting an entity that is unchanged, the data, rev_hash, etc should be unchanged and no new
        # audit entity should be written.  it's as if the put is silently ignored even though it actually gets put
        for cls in self._TEST_CLASSES:
            fookey = ndb.Key(cls.__name__, 'parentfoo')
            ent1 = cls(key=fookey, foo='a', bar=1)
            self._trans_put(ent1)
            orig_data_hash = ent1.data_hash
            self.assertIsNotNone(orig_data_hash)
            orig_rev_hash = list(Audit.query_by_entity_key(ent1))[0].rev_hash
            self.assertIsNotNone(orig_rev_hash)
            ent1.foo = 'a'
            ent1.bar = 1
            self._trans_put(ent1)
            self.assertEqual(orig_data_hash, ent1.data_hash)
            self.assertEqual(orig_data_hash, fookey.get().data_hash)

            # should only be a single audit entry
            audits = list(Audit.query_by_entity_key(ent1))
            self.assertEqual(len(audits), 1)
            self.assertEqual(audits[0].rev_hash, orig_rev_hash)
            self.assertIsNone(audits[0].parent_hash)

            # mutate fookey and see that it gets new audit
            ent1.foo = 'b'
            ent1.bar = 2
            self._trans_put(ent1)
            new_data_hash = hashlib.sha1('{v1}bar=2|foo=b').hexdigest()[0:8]
            def check_v2():
                self.assertEqual(ent1.data_hash, new_data_hash)
                audits = list(Audit.query_by_entity_key(ent1))
                self.assertEqual(len(audits), 2)
                self.assertEqual(audits[0].data_hash, new_data_hash)
                self.assertEqual(audits[0].parent_hash, orig_rev_hash)

            check_v2()

            # now do another no-op put and make sure
            ent1.foo = 'b'
            ent1.bar = 2
            self._trans_put(ent1)
            check_v2()

    def test_tag_create_from_data_hash(self):
        for cls in self._TEST_CLASSES:
            fookey = ndb.Key(cls.__name__, 'parentfoo')
            t1 = Tag.create_from_data_hash(fookey, 'jcj', 'abc123')
            self.assertEqual(t1.key.string_id(), 'jcj')
            self.assertEqual(t1.data_hash, 'abc123')

    def test_tag_create_from_entity(self):
        for cls in self._TEST_CLASSES:
            fookey = ndb.Key(cls.__name__, 'parentfoo')
            ent1 = cls(key=fookey, foo='a', bar=1)
            self._trans_put(ent1)
            t1 = Tag.create_from_entity(ent1, 'jcj')
            self.assertEqual(t1.key.string_id(), 'jcj')
            self.assertEqual(t1.data_hash, ent1.data_hash)

    def test_build_tag_key(self):
        for cls in self._TEST_CLASSES:
            fookey = ndb.Key(cls.__name__, 'parentfoo')
            k = Tag.build_tag_key(fookey, 'bar')
            self.assertEqual(k.parent(), fookey)
            self.assertEqual(k.string_id(), 'bar')
            ent1 = cls(key=fookey, foo='a', bar=1)
            k = Tag.build_tag_key(ent1, 'bar')
            self.assertEqual(k.parent(), fookey)
            self.assertEqual(k.string_id(), 'bar')

    def test_structured_property(self):
        foomodel1 = FooInsideModel(foo='foomodela',bar=11)
        foomodel2 = FooInsideModel(foo='foomodelb',bar=22)
        foomodel3 = FooInsideModel(foo='foomodelc',bar=33)

        fookey = ndb.Key(FooStructuredModel, 'parentfoo')
        ent1 = FooStructuredModel(key=fookey, foo='a', bar=1, baz=[foomodel1, foomodel2, foomodel3])
        self._trans_put(ent1)
        q1 = Audit.query_by_entity_key(fookey)
        a = list(q1)[0]
        self.assertEqual(a.baz, [foomodel1, foomodel2, foomodel3])
        orig_data_hash = a.data_hash

        # test changing list
        ent1.baz = [foomodel1, foomodel2]
        self._trans_put(ent1)
        a = list(q1)[0]
        self.assertEqual(a.baz, [foomodel1, foomodel2])
        self.assertNotEqual(a.data_hash, orig_data_hash)
        orig_data_hash = a.data_hash

        # test chaning item in list
        ent1.baz[0].bar = 99999
        self._trans_put(ent1)
        a = list(q1)[0]
        self.assertEqual(a.baz[0].bar, 99999)
        self.assertNotEqual(a.data_hash, orig_data_hash)
        


