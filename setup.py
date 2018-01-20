#!/usr/bin/env python
import os
from codecs import open
from setuptools import setup

import m2r

THIS_DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(THIS_DIR, 'README.md'), encoding='utf-8') as fobj:
    README = m2r.convert(fobj.read())

setup(
    name='sqlalchemy_fsm',
    packages=['sqlalchemy_fsm'],
    py_modules=['sqlalchemy_fsm'],
    description='Finite state machine field for sqlalchemy',
    long_description=README,
    author='Peter & Ilja',
    author_email='ilja@wise.fish',
    license='MIT',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Topic :: Database',
    ],
    keywords='sqlalchemy finite state machine fsm',
    version='1.1.3',
    url='https://github.com/VRGhost/sqlalchemy-fsm',
    install_requires=['SQLAlchemy>=1.1.3'],
    setup_requires=['pytest-runner'],
    tests_require=['pytest']
)