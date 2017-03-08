import base64
import datetime
import hashlib
import json
import logging
import marshal

from google.appengine.ext import ndb

from ndb_audit import Audit, AuditMixin, Tag, audit_put_multi_async, tag_multi_from_rev_hash_async, _hash_str
from test import NDBUnitTest


class FooProperty(ndb.BlobProperty):
    def _to_base_type(self, value):
        return marshal.dumps(value)

    def _from_base_type(self, value):
        return marshal.loads(value)


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

        custom_prop = FooProperty()

        def _account(self):
            return 'foo-account'

    class FooModel(AuditMixin, ndb.Model):
        foo = ndb.StringProperty()
        bar = ndb.IntegerProperty()

        custom_prop = FooProperty()

        def _account(self):
            return 'foo-account'

    _TEST_CLASSES = [FooExpando, FooModel]

    CUSTOM_VAL_1 = {'baz': 1}
    CUSTOM_VAL_2 = {'qux': 2}
    CUSTOM_ENC_1 = FooProperty()._to_base_type(CUSTOM_VAL_1)
    CUSTOM_ENC_2 = FooProperty()._to_base_type(CUSTOM_VAL_2)

    def test_audit_create_from_entity(self):
        for cls in self._TEST_CLASSES:
            ent = cls(key=ndb.Key(cls.__name__, 'parentfoo'), foo='a', bar=1, custom_prop=self.CUSTOM_VAL_1)
            self._trans_put(ent)
            expected_data_hash = _hash_str('{v1}bar=1|custom_prop=%s|foo=a' % self.CUSTOM_ENC_1)
            expected_rev_hash = _hash_str('{v1}None|foo-account|%s' % expected_data_hash)
            self.assertEqual(ent.data_hash, expected_data_hash)
            self.assertEqual(ent.rev_hash, expected_rev_hash)

            a = Audit.create_from_entity(ent, None)
            self.assertIsInstance(a.timestamp, datetime.datetime) # can't accurately check autogen of this
            self.assertEqual(a.kind, str(ent._get_kind()))
            self.assertEqual(_hash_str(a.key.string_id()), expected_rev_hash)
            self.assertEqual(a.data_hash, expected_data_hash)
            self.assertEqual(a.account, 'foo-account')
            self.assertEqual(a.foo, 'a')
            self.assertEqual(a.bar, 1)
            self.assertEqual(a.custom_prop, self.CUSTOM_ENC_1)
            self.assertEqual(a.key.parent(), ent.key)

    def test_audit_query_by_entity_key(self):
        for cls in self._TEST_CLASSES:
            fookey = ndb.Key(cls.__name__, 'parentfoo')
            ent1 = cls(key=fookey, foo='a', bar=1, custom_prop=self.CUSTOM_VAL_1)
            self._trans_put(ent1)
            ent2 = fookey.get()
            ent2.foo = 'b'
            ent2.bar = 2
            ent2.custom_prop = self.CUSTOM_VAL_2
            self._trans_put(ent2)
            q1 = Audit.query_by_entity_key(fookey)
            a_list = sorted(list(q1), key=lambda x: x.timestamp, reverse=True)
            logging.info(a_list)
            expected_data_hash1 = _hash_str('{v1}bar=1|custom_prop=%s|foo=a' % self.CUSTOM_ENC_1)
            first_hash = _hash_str('{v1}None|foo-account|%s' % expected_data_hash1)
            self.assertEqual(a_list[0].foo, 'b')
            self.assertEqual(a_list[0].bar, 2)
            self.assertEqual(a_list[0].custom_prop, self.CUSTOM_ENC_2)
            self.assertEqual(a_list[0].data_hash, _hash_str('{v1}bar=2|custom_prop=%s|foo=b' % self.CUSTOM_ENC_2))
            self.assertEqual(a_list[0].parent_hash, first_hash)
            self.assertEqual(a_list[1].foo, 'a')
            self.assertEqual(a_list[1].bar, 1)
            self.assertEqual(a_list[1].custom_prop, self.CUSTOM_ENC_1)
            self.assertEqual(a_list[1].rev_hash, first_hash)
            self.assertGreater(a_list[0].timestamp, a_list[1].timestamp)

    def test_blind_put(self):
        for cls in self._TEST_CLASSES:
            fookey = ndb.Key(cls.__name__, 'parentfoo')
            ent1 = cls(key=fookey, foo='a', bar=1, custom_prop=self.CUSTOM_VAL_1)
            self._trans_put(ent1)
            self.assertEqual(ent1.data_hash, _hash_str('{v1}bar=1|custom_prop=%s|foo=a' % self.CUSTOM_ENC_1))
            ent2 = cls(key=fookey, foo='b', bar=2, custom_prop=self.CUSTOM_VAL_2)
            self._trans_put(ent2)
            self.assertEqual(ent2.data_hash, _hash_str('{v1}bar=2|custom_prop=%s|foo=b' % self.CUSTOM_ENC_2))
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
            ent1 = cls(key=fookey1, foo='a', bar=1, custom_prop=self.CUSTOM_VAL_1)
            expected_data_hash1 = _hash_str('{v1}bar=1|custom_prop=%s|foo=a' % self.CUSTOM_ENC_1)
            expected_rev_hash1 = _hash_str('{v1}None|foo-account|%s' % expected_data_hash1)
            ent2 = cls(key=fookey2, foo='b', bar=2, custom_prop=self.CUSTOM_VAL_2)
            expected_data_hash2 = _hash_str('{v1}bar=2|custom_prop=%s|foo=b' % self.CUSTOM_ENC_2)
            expected_rev_hash2 = _hash_str('{v1}None|foo-account|%s' % expected_data_hash2)
            self.t_put_multi([ent1, ent2])
            self.assertEqual(ent1.data_hash, expected_data_hash1)
            self.assertEqual(ent1.rev_hash, expected_rev_hash1)
            self.assertEqual(ent2.data_hash, expected_data_hash2)
            self.assertEqual(ent2.rev_hash, expected_rev_hash2)
            a1 = Audit.build_audit_record_key(fookey1, expected_data_hash1, None, 'foo-account').get()
            a2 = Audit.build_audit_record_key(fookey2, expected_data_hash2, None, 'foo-account').get()
            self.assertEqual(a1.foo, 'a')
            self.assertEqual(a1.custom_prop, self.CUSTOM_ENC_1)
            self.assertEqual(a1.data_hash, expected_data_hash1)
            self.assertEqual(a1.rev_hash, expected_rev_hash1)
            self.assertEqual(a2.bar, 2)
            self.assertEqual(a2.custom_prop, self.CUSTOM_ENC_2)
            self.assertEqual(a2.data_hash, expected_data_hash2)
            self.assertEqual(a2.rev_hash, expected_rev_hash2)

    def test_put_when_data_unchanged(self):
        # if we are putting an entity that is unchanged, the data, rev_hash, etc should be unchanged and no new
        # audit entity should be written.  it's as if the put is silently ignored even though it actually gets put
        for cls in self._TEST_CLASSES:
            fookey = ndb.Key(cls.__name__, 'parentfoo')
            ent1 = cls(key=fookey, foo='a', bar=1, custom_prop='baz')
            self._trans_put(ent1)
            orig_data_hash = ent1.data_hash
            self.assertIsNotNone(orig_data_hash)
            orig_rev_hash = list(Audit.query_by_entity_key(ent1))[0].rev_hash
            self.assertIsNotNone(orig_rev_hash)
            ent1.foo = 'a'
            ent1.bar = 1
            ent1.custom_prop = 'baz'
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
            ent1.custom_prop = self.CUSTOM_VAL_2
            self._trans_put(ent1)
            new_data_hash = _hash_str('{v1}bar=2|custom_prop=%s|foo=b' % self.CUSTOM_ENC_2)

            def check_v2():
                self.assertEqual(ent1.data_hash, new_data_hash)
                audits = sorted(list(Audit.query_by_entity_key(ent1)), key=lambda x: x.timestamp, reverse=True)
                self.assertEqual(len(audits), 2)
                self.assertEqual(audits[0].data_hash, new_data_hash)
                self.assertEqual(audits[0].parent_hash, orig_rev_hash)

            check_v2()

            # now do another no-op put and make sure
            ent1.foo = 'b'
            ent1.bar = 2
            ent1.custom_prop = self.CUSTOM_VAL_2
            self._trans_put(ent1)
            check_v2()

    def test_tag_create_from_rev_hash(self):
        for cls in self._TEST_CLASSES:
            fookey = ndb.Key(cls.__name__, 'parentfoo')
            t1 = Tag.create_from_rev_hash(fookey, 'jcj', 'abc123', 'revfoo')
            t1.put()
            t2 = Tag.get_by_entity_key_label_async(fookey, 'abc123').get_result()
            self.assertEqual(t2.key.parent(), fookey)
            self.assertEqual(t2.label, 'abc123')
            self.assertEqual(t2.account, 'jcj')
            self.assertEqual(t2.rev_hash, 'revfoo')

    def test_tag_create_from_entity(self):
        for cls in self._TEST_CLASSES:
            fookey = ndb.Key(cls.__name__, 'parentfoo')
            ent1 = cls(key=fookey, foo='a', bar=1)
            self._trans_put(ent1)
            t1 = Tag.create_from_entity(ent1, 'abc123')
            t1.put()
            t2 = Tag.get_by_entity_key_label_async(ent1, 'abc123').get_result()
            self.assertEqual(t2.entity_key, fookey)
            self.assertEqual(t2.label, 'abc123')
            self.assertEqual(t2.account, 'foo-account')
            self.assertEqual(t2.rev_hash, ent1.rev_hash)

    def test_tag_multi(self):
        for cls in self._TEST_CLASSES:
            keys = [ndb.Key(cls.__name__, k) for k in ['parent1', 'parent2', 'parent3']]
            rev_hashes = ['foohash', 'barhash', 'bazhash']
            tag_futures = tag_multi_from_rev_hash_async(keys, rev_hashes, 'foo-account', 'abc123')
            for f, expected_k, expected_hash in zip(tag_futures, keys, rev_hashes):
                k = f.get_result()
                tag = k.get()
                self.assertEqual(tag.label, 'abc123')
                self.assertEqual(tag.account, 'foo-account')
                self.assertEqual(tag.rev_hash, expected_hash)
                self.assertEqual(tag.entity_key, expected_k)

    def test_tag_query_by_entity_key(self):
        for cls in self._TEST_CLASSES:
            fookey = ndb.Key(cls.__name__, 'parentfoo')
            q1 = Tag.query_by_entity_key(fookey)
            self.assertEqual(len(list(q1)), 0)

            ent1 = cls(key=fookey, foo='a', bar=1, custom_prop=self.CUSTOM_VAL_1)
            self._trans_put(ent1)
            t1 = Tag.create_from_entity(ent1, 'abc123')
            t1.put()
            q1 = Tag.query_by_entity_key(fookey)
            q_list = list(q1)
            logging.info(q_list)
            self.assertEqual(len(q_list), 1)
            self.assertEqual(q_list[0].rev_hash, ent1.rev_hash)
            self.assertEqual(q_list[0].label, 'abc123')
            self.assertEqual(q_list[0].account, 'foo-account')
            self.assertEqual(q_list[0].entity_key, fookey)

            # add rev hash
            q2 = Tag.query_by_entity_key(fookey, 'wronghash')
            self.assertEqual(len(list(q2)), 0)
            q2 = Tag.query_by_entity_key(fookey, ent1.rev_hash)
            self.assertEqual(len(list(q2)), 1)

    def test_structured_property(self):
        foomodel1 = FooInsideModel(foo='foomodela',bar=11)
        foomodel2 = FooInsideModel(foo='foomodelb',bar=22)
        foomodel3 = FooInsideModel(foo='foomodelc',bar=33)

        fookey = ndb.Key(FooStructuredModel, 'parentfoo')
        ent1 = FooStructuredModel(key=fookey, foo='a', bar=1, baz=[foomodel1, foomodel2, foomodel3])
        self._trans_put(ent1)
        a = sorted(list(Audit.query_by_entity_key(fookey)), key=lambda x: x.timestamp, reverse=True)[0]
        self.assertEqual(a.baz, [foomodel1, foomodel2, foomodel3])
        orig_data_hash = a.data_hash

        # test changing list
        ent1.baz = [foomodel1, foomodel2]
        self._trans_put(ent1)
        a = sorted(list(Audit.query_by_entity_key(fookey)), key=lambda x: x.timestamp, reverse=True)[0]
        self.assertEqual(a.baz, [foomodel1, foomodel2])
        self.assertNotEqual(a.data_hash, orig_data_hash)
        orig_data_hash = a.data_hash

        # test chaning item in list
        ent1.baz[0].bar = 99999
        self._trans_put(ent1)
        a = sorted(list(Audit.query_by_entity_key(fookey)), key=lambda x: x.timestamp, reverse=True)[0]
        self.assertEqual(a.baz[0].bar, 99999)
        self.assertNotEqual(a.data_hash, orig_data_hash)
        
    def test_hash_str(self):
        self.assertEqual(_hash_str(None), None)
        self.assertEqual(_hash_str(''), '')
        self.assertEqual(_hash_str('foo'), base64.urlsafe_b64encode(hashlib.sha1('foo').digest())[0:10])
