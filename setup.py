from setuptools import find_packages, setup

setup(
    name='ndb_audit',
    packages=find_packages(
        exclude=["*.test", "*.test.*", "test.*", "test"]
    ),
    version = '0.0.1',
    description = 'Adds audit trail to any NDB entity',
    author='Jason Jones',
    author_email='jason@gaincompliance.com',
    url='https://github.com/GainCompliance/ndb-audit',
    classifiers=[
        'Programming Language :: Python',
        'Programming Language :: Python :: 2'
    ]
)
