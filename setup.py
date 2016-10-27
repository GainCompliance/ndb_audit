from setuptools import find_packages, setup

VERSION = '0.0.1'

setup(
    name='ndb_audit',
    packages=find_packages(
        exclude=["*.test", "*.test.*", "test.*", "test"]
    ),
    version = VERSION,
    description = 'Adds audit trail to any NDB entity',
    author='Jason Jones',
    author_email='jason@gaincompliance.com',
    keywords=['google', 'appengine', 'datastore', 'NDB', 'audit'],
    url='https://github.com/GainCompliance/ndb-audit',
    license='MIT',
    classifiers=[
        'Programming Language :: Python',
        'Programming Language :: Python :: 2'
    ]
)
