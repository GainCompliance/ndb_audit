|Build Status|

Adds an immutable audit trail to any
`NDB <https://cloud.google.com/appengine/docs/python/ndb/>`__ entity
(including
`Expando <https://cloud.google.com/appengine/docs/python/ndb/creating-entity-models#expando>`__-based
models) built by the `engineering team at Gain Compliance <https://gaincompliance.com>`__.

Data structures are optimized for write performance and query-ability at
the expense of read performance and size of data. However, it is
minimally invasive on the entity you add it to. It only adds two
properties to the main entity totalling 32 characters and does not
prevent you from doing normal get by key

You should read the below description of the data model (and especially
entity groups) to ensure you don't cause datastore contention problems
with EGs that are too big

Features
--------

-  Full history of an entity's changes are recorded in a way that should
   be easily query-able
-  Audit history is atomically updated when the entity is put, even if
   all the entity's properties are the same
-  Supports account (string), timestamp (datetime), data\_hash (SHA-1 of
   properties) tracking
-  Strongly consistent retrieval of audit history
-  (WIP)Flexible "tagging" system to track progress along the chain of
   changes by a user, system, etc
-  (Future) "at revision" fetching of data
-  (Future) Diffing between revisions
-  (Future) Collision detection and merging

Data Model
----------

For a given entity 'E' of kind 'EKind', ndb\_audit will monitor all puts
to entities who include the AuditMixin. Upon put a new Audit entity 'A'
will be created which will be a complete copy of the entity. The entity
A will have the following:

-  A will be of kind 'Audit'
-  A will carry the namespace if the
   `namespace\_manager <https://cloud.google.com/appengine/docs/python/refdocs/google.appengine.api.namespace_manager.namespace_manager>`__
   is used
-  A will contain a copy of every datastore property of E as it was when
   it was put
-  The parent entity of A will be E
-  The key of A will be ndb.Key(parent=, pairs=[('Audit', )])
-  An attribute will be added to E called 'd', and a python property
   will be added to your class to access this value as data\_hash. This
   value is added to your entity to allow caching based on the
   data\_hash by all clients. At a given value for data\_hash E will
   always be the same. The data\_hash is a truncated SHA-1 hash of
   properties of the entity
-  An attribute will be added to E called 'h', and a python property
   will be added to your class to access this value as rev\_hash. This
   value is added to your entity to allow you to track which revision
   the current entity is at. The rev\_hash is a truncated SHA-1 hash of
   parent rev\_hash, account string, and data\_hash properties of the
   entity
-  No other properties will be added to E, instead you will have to
   fetch the audit entities -- this is to keep overhead on E as small as
   possible


Usage
-----

TODO

.. |Build Status| image:: https://travis-ci.org/GainCompliance/ndb_audit.svg
   :target: https://travis-ci.org/GainCompliance/ndb_audit
