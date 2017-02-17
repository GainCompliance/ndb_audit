import sys
from setuptools import find_packages, setup

try:
    from semantic_release import setup_hook
    setup_hook(sys.argv)
except ImportError:
    pass


with open('README.rst', 'r') as readme_file:
    long_description = readme_file.read()


setup(
    name='ndb_audit',
    packages=find_packages(
        exclude=["*.test", "*.test.*", "test.*", "test"]
    ),
    install_requires=[],
    entry_points={'console_scripts': ['semantic-release = semantic_release.cli:main']},
    version_format='{tag}',
    setup_requires=['setuptools-git-version==1.0.3'],
    description = 'Adds audit trail to any Google Datastore NDB entity',
    long_description=long_description,
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
