Adds audit trail to any NDB entity (including Expando-based models)

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
