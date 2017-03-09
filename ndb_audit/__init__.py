"""
Adds audit trail to any NDB entity (including Expando-based models)
For more details see README.md
"""

import base64
import datetime
import hashlib
import logging
import os

from google.appengine.ext import ndb

__version__ = '1.1.4'

HASH_LENGTH = 8 # (in bytes out of 20 bytes for SHA-1)

class AuditMixin(object):
    """ a mixin for adding audit to NDB models, see file docstring for more information """

    # data_hash is added to each entity to make it more cacheable
    # this should never be set directly.  It is computed *only upon put*.  Before that it will be out of date
    # if you change the entity's properties
    # may not be globally unique -- shortened for storage/performance
    data_hash = ndb.StringProperty(indexed=False, default=None, name='d')

    # rev_hash is the unique identifier of a revision of the entity.  it is composed of the previous revisions rev_hash
    # (the parent hash), the account, and the current data_hash
    # this should never be set directly.  It is computed *only upon put*.  Before that it could be out of date
    # if you change the entity's properties
    # may not be globally unique -- shortened for storage/performance
    rev_hash = ndb.StringProperty(indexed=False, default=None, name='h')

    # can be set to true during batch updates
    _skip_pre_hook = False

    def _update_data_hash(self):
        """ modelled after git commit/parent hashes, although merging not implemented yet """
        props = _entity_dict(self)
        prop_str = '{v1}%s' % '|'.join(['%s=%s' % (k,str(props[k])) for k in sorted(props.iterkeys())])
        logging.info(prop_str)
        self.data_hash = _hash_str(prop_str)
        return self.data_hash

    def _build_audit_entity(self, parent_hash):
        return Audit.create_from_entity(self, parent_hash)

    def _batch_put_hook(self):
        """ sets new data_hash, turns off regular put hook and returns audit entity ready for saving """
        # TODO: think through exception handling here
        cur_data_hash = self.data_hash
        new_data_hash = self._update_data_hash()
        if cur_data_hash == new_data_hash:
            logging.debug('ndb_audit put_hook data_hash unchanged for %s, %s' % (self.key, self.data_hash))
            new_aud = None # do not write an audit entity
        else:
            new_aud = self._build_audit_entity(self.rev_hash)
            self.rev_hash = new_aud.rev_hash
            logging.debug(new_aud)
        self._skip_pre_hook = True
        return new_aud

    def _account(self):
        # users must implement this in each model to let the ndb_audit framework know which account is associated
        # with a given change.  in the mixin this function is not implemented
        raise NotImplementedError

    # NDB model hooks

    @ndb.transactional_async(xg=True, propagation=ndb.TransactionOptions.MANDATORY)
    def _pre_put_hook(self):
        if self._skip_pre_hook:
            self._skip_pre_hook = False
            return
        # TODO: think through exception handling here
        new_aud = self._batch_put_hook()
        if new_aud:
            ndb.put_multi_async([new_aud])

    def _post_put_hook(self, future):
        self._skip_pre_hook = False


@ndb.transactional_tasklet(xg=True)
def audit_put_multi_async(entities, **ctx_options):
    """ a version of ndb's put_multi_async which writes the audit entities (efficiently) as a tasklet """
    to_put = [e._batch_put_hook() for e in entities] + entities
    yield ndb.put_multi_async(to_put, **ctx_options)


class Audit(ndb.Expando):
    """ an audit record with a full copy of the entity -- see file docstring for more information
    should not be directly instantiated

    index.yaml entry required for this entity:
    TODO
    """

    _default_indexed = False # TODO: consider making true for better query-ability of entities

    kind = ndb.StringProperty(indexed=False, required=True, name='k')
    # data hash uniquely identified the NDB properties of the entity
    data_hash = ndb.StringProperty(indexed=False, required=True, name='d')
    parent_hash = ndb.StringProperty(indexed=False, default=None, name='p')
    account = ndb.StringProperty(indexed=False, required=True, name='a')
    timestamp = ndb.DateTimeProperty(indexed=False, required=True, name='ts')

    @classmethod
    def create_from_entity(cls, entity, parent_hash, timestamp=None):
        """ given an Auditable entity, create a new Audit entity suitable for storing"""
        if not timestamp:
            timestamp = datetime.datetime.utcnow()

        a_key = Audit.build_audit_record_key(entity.key, entity.data_hash, parent_hash, entity._account())
        a = Audit(key=a_key,
                  kind=entity._get_kind(),
                  data_hash=entity.data_hash,
                  parent_hash=parent_hash,
                  account=entity._account(),
                  timestamp=timestamp)


        a.populate(**_entity_dict(entity))
        return a

    @classmethod
    def build_audit_record_key(cls, entity_key, data_hash, parent_hash, account):
        """ returns key for audit record -- uses data_hash property which may not be up to date """
        return ndb.Key(parent=entity_key,
                       pairs=[('Audit', '{v1}%s|%s|%s' % (parent_hash, account, data_hash))])

    @classmethod
    def query_by_entity_key(cls, entity_or_key):
        """ given the key of the audited entity, query all audit entries in reverse order
        returns a query object
        Note: this is a strongly consistent query
        Note: these are not ordered
        """
        if not isinstance(entity_or_key, ndb.Key):
            entity_or_key = entity_or_key.key
        q = Audit.query(ancestor=entity_or_key)
        return q

    # rev hash uniquely identifies this change by parent_hash, account, and data_hash
    # may not be globally unique -- shortened for storage/performance
    @property
    def rev_hash(self):
        return _hash_str(self.key.string_id())


def tag_multi_from_rev_hash_async(entity_keys, rev_hashes, account, label):
    """ tag all of the supplied entity keys at the given rev hashes with the given label
    this is not transactional, it may only partially apply in failure scenarios.
    this is a idempotent action

    :returns NDB Future
    """
    to_put = [Tag.create_from_rev_hash(k, account, label, r) for k,r in zip(entity_keys, rev_hashes)]
    return ndb.put_multi_async(to_put)


class Tag(ndb.Model):
    """ a tag is a pointer to a specific rev hash with a label.  Its parent is the Auditable entity
    "labels" are flexible, they can be any string safe for use in an NDB key.  The key is composed of the parent
    entity and the label so that tags can be efficiently fetched and only one tag per entity per label can exist
    """

    rev_hash = ndb.StringProperty(indexed=True, required=True, name='r')
    timestamp = ndb.DateTimeProperty(indexed=False, required=True, name='ts')
    account = ndb.StringProperty(indexed=False, required=True, name='a')


    @property
    def label(self):
        return self.key.string_id()

    @property
    def entity_key(self):
        return self.key.parent()

    @classmethod
    def create_from_entity(cls, entity, label):
        return Tag.create_from_rev_hash(entity.key, entity._account(), label, entity.rev_hash)


    @classmethod
    def create_from_rev_hash(cls, entity_key, account, label, rev_hash):
        """ for putting when you don't have the keys """
        key = Tag._build_tag_key(entity_key, label)
        t = Tag(key=key, account=account, rev_hash=rev_hash, timestamp=datetime.datetime.utcnow())
        return t

    @classmethod
    def query_by_entity_key(cls, entity_or_key, rev_hash=None):
        """ given the key of the audited entity, query all tags
        :returns a query object
        Note: this is a strongly consistent query
        Note: these are not ordered
        """
        if not isinstance(entity_or_key, ndb.Key):
            entity_or_key = entity_or_key.key
        q = Tag.query(ancestor=entity_or_key)
        if rev_hash:
            q = q.filter(Tag.rev_hash == rev_hash)
        return q

    @classmethod
    def get_by_entity_key_label_async(cls, entity_or_key, label):
        return cls._build_tag_key(entity_or_key, label).get_async()

    @classmethod
    def _build_tag_key(cls, entity_or_key, label):
        if isinstance(entity_or_key, ndb.Model):
            entity_or_key = entity_or_key.key
        return ndb.Key(parent=entity_or_key, pairs=[('Tag', str(label))])


def _hash_str(data_str):
    if not data_str:
        return data_str
    return base64.urlsafe_b64encode(hashlib.sha1(data_str).digest()[0:HASH_LENGTH]).rstrip('=')


def _entity_dict(entity):
    props = entity._to_dict(exclude=['data_hash', 'rev_hash'])
     # special handling for special properties
    for k,v in props.iteritems():
        prop = entity._properties[k]
        if isinstance(prop, ndb.StructuredProperty):
            logging.debug('found StructuredProperty')
            if prop._repeated:
                # v is a list of dictionaries, but needs to be a list of objects
                # just replace with actual list from entity
                props[k] = getattr(entity, k)
            else:
                pass # TODO
        elif isinstance(prop, ndb.BlobProperty):
            logging.debug('found BlobProperty')
            # v is the unencoded/unmarshaled value but safer just to hang on to raw binary value
            base_val = prop._get_base_value(entity)
            if base_val:
                props[k] = prop._get_base_value(entity).b_val # TODO: pretty dependent on _BaseValue impl which is not great
    return props
