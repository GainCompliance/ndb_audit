""" Adds audit trail to any NDB entity (including Expando-based models)

Data structures are optimized for write performance and query-ability at the expense of
read performance and size of data.  However, it is minimally invasive on the entity you add it to.
It only adds a single property to the main entity and does not prevent you from doing normal get by key

You should read the below description of the data model (and especially entity groups) to ensure you don't
cause datastore contention problems with EGs that are too big

**Features**
* Full history of an entity's changes are recorded in a way that should be easily query-able
* Audit history is atomically updated when the entity is put, even if all the entitie's properties are the same
* Supports user (string), timestamp (datetime), data_hash (sha-1 of properties), transaction_id (string) tracking
* Strongly consistent retrieval of audit history
* Flexible "tagging" system to track progress along the chain of changes by a user, system, etc
* (Future) "at revision" fetching of data
* (Future) Diffing between revisions
* (Future) Collision detection and merging

**Data Model**

For a given entity 'E' of kind 'EKind', ndb_audit will monitor all puts to entities who include the AuditMixin.  Upon
put a new Audit entity 'A' will be created which will be a complete copy of the entity.  The entity A will have
the following:

* A will be of kind 'Audit'
* (Future) A will carry the namespace of E if present
* A will contain a copy of every datastore property of E as it was when it was put
* The parent entity of A will be E
* The key of A will be ndb.Key(parent=<key of E>, pairs=[('Audit', <rev_hash of entity>)])
* An attribute will be added to E called 'd', and a python property will be added to your class
  to access this value as data_hash.  This value is added to your entity to allow caching based on the data_hash
  by all clients.  At a given value for data_hash E will always be the same.  The data_hash is a truncated SHA-1 hash of
  properties of the entity
* An attribute will be added to E called 'h', and a python property will be added to your class
    to access this value as rev_hash.  This value is added to your entity to allow you to track which revision the
    current entity is at.  The rev_hash is a truncated SHA-1 hash of parent rev_hash, account string, and data_hash
    properties of the entity
* No other properties will be added to E, instead you will have to fetch the audit entities --
  this is to keep overhead on E as small as possible

**Index Required**

TODO

**Usage**

TODO

**License**

The MIT License (MIT)

Copyright (c) 2016 Gain Compliance, Inc.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""

import datetime
import hashlib
import logging
import os

from google.appengine.ext import ndb

HASH_LENGTH = 8

class AuditMixin(object):
    """ a mixin for adding audit to NDB models, see file docstring for more information """

    # data_hash is added to each entity to make it more cacheable
    # this should never be set directly.  It is computed *only upon put*.  Before that it will be out of date
    # if you change the entity's properties
    # may not be globally unique -- shortened for storage/performance
    data_hash = ndb.StringProperty(indexed=False, default=None, name='d')

    # rev_hash is the unique identifier of a revision of the entity.  it is composed of the previous revisions rev_hash
    # (the parent hash), the account, and the current data_hash
    # this should never be set directly.  It is computed *only upon put*.  Before that it could be out of data
    # if you change the entity's properties
    # may not be globally unique -- shortened for storage/performance
    rev_hash = ndb.StringProperty(indexed=False, default=None, name='h')

    # can be set to true during batch updates
    _skip_pre_hook = False

    def _update_data_hash(self):
        """ modelled after git commit/parent hashes, although merging not implemented yet """
        props = self._to_dict(exclude=['data_hash', 'rev_hash'])
        prop_str = '{v1}%s' % '|'.join(['%s=%s' % (k,str(props[k])) for k in sorted(props.iterkeys())])
        self.data_hash = hashlib.sha1(prop_str).hexdigest()[0:HASH_LENGTH] # shortening hash for performance/storage
        return self.data_hash

    def _build_audit_entity(self, parent_hash, account):
        return Audit.create_from_entity(self, parent_hash, account)

    def _batch_put_hook(self):
        """ sets new data_hash, turns off regular put hook and returns audit entity ready for saving """
        # TODO: think through exception handling here
        cur_data_hash = self.data_hash
        new_data_hash = self._update_data_hash()
        if cur_data_hash == new_data_hash:
            logging.debug('ndb_audit put_hook data_hash unchanged for %s, %s' % (self.key, self.data_hash))
            new_aud = None # do not write an audit entity
        else:
            new_aud = self._build_audit_entity(self.rev_hash, self._account())
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
    # rev hash uniquely identifies this change by parent_hash, account, and data_hash
    # TODO: should we store this since it's also embedded in the key?  for now yes
    rev_hash = ndb.StringProperty(indexed=True, required=True, name='h')
    # data hash uniquely identified the NDB properties of the entity
    data_hash = ndb.StringProperty(indexed=False, required=True, name='d')
    parent_hash = ndb.StringProperty(indexed=False, default=None, name='p')
    account = ndb.StringProperty(indexed=False, required=True, name='a')
    timestamp = ndb.DateTimeProperty(indexed=True, required=True, name='ts')
    request_id = ndb.StringProperty(indexed=True, required=True, name='r')

    @classmethod
    def create_from_entity(cls, entity, parent_hash, account,
                           request_id=os.environ.get('REQUEST_LOG_ID', ''), timestamp=None):
        """ given an Auditable entity, create a new Audit entity suitable for storing"""
        if request_id and len(request_id) > 16:
            request_id = request_id[0:16] # shorten request id for storage/performance

        if not timestamp:
            timestamp = datetime.datetime.utcnow()

        a_key = Audit.build_audit_record_key(entity.key, entity.data_hash, parent_hash, account)
        rev_hash = hashlib.sha1(a_key.string_id()).hexdigest()[0:HASH_LENGTH] # shorten hash for storage/performance
        a = Audit(key=a_key,
                  kind=entity._get_kind(),
                  rev_hash=rev_hash,
                  data_hash=entity.data_hash,
                  parent_hash=parent_hash,
                  account=account,
                  timestamp=timestamp,
                  request_id=request_id)
        props = entity._to_dict()
        if 'data_hash' in props:
            del props['data_hash'] # causes issues I think due to a bug in populate
        if 'rev_hash' in props:
            del props['rev_hash']

        # special handling for structured properties
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

        a.populate(**props)
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
        Note: this is in timestamp order, ordering by the commit history tree is not done yet
              THEREFORE, in cases of system clock lag and concurrent modfiication these could
              appear out of order
        """
        if not isinstance(entity_or_key, ndb.Key):
            entity_or_key = entity_or_key.key
        q = Audit.query(ancestor=entity_or_key).order(-Audit.timestamp)
        return q

class Tag(ndb.Model):
    """ a tag is a pointer to a specific data hash with a label.  Its parent is the Auditable entity
    "labels" are flexible, they can be any string safe for use in an NDB key.  The key is composed of the parent
    entity and the label so that tags can be efficiently fetched and only one tag per entity per label can exist
    index.yaml entry required for this entity:
    TODO
    """

    data_hash = ndb.StringProperty(indexed=False, required=True, name='d')
    timestamp = ndb.DateTimeProperty(indexed=False, required=True, name='ts')


    @classmethod
    def create_from_entity(cls, entity, label):
        return Tag.create_from_data_hash(entity.key, label, entity.data_hash)


    @classmethod
    def create_from_data_hash(cls, entity_key, label, data_hash):
        """ for putting when you don't have the keys """
        key = Tag.build_tag_key(entity_key, label)
        t = Tag(key=key, data_hash=data_hash, timestamp=datetime.datetime.utcnow())
        return t


    @classmethod
    def build_tag_key(cls, entity_or_key, label):
        if isinstance(entity_or_key, ndb.Model):
            entity_or_key = entity_or_key.key
        return ndb.Key(parent=entity_or_key, pairs=[('Tag', str(label))])
