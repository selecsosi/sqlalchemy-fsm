#!/usr/bin/env python

from setuptools import setup

setup(
    name='sqlalchemy_fsm',
    packages=['sqlalchemy_fsm'],
    py_modules=['sqlalchemy_fsm'],
    description='Finite state machine field for sqlalchemy',
    author='Peter & Ilja',
    author_email='ilja@wise.fish',
    version='1.1.1',
    url='https://github.com/dagoof/sqlalchemy-fsm',
    install_requires=['SQLAlchemy>=1.1.1'],
    setup_requires=['pytest-runner'],
    tests_require=['pytest']
)