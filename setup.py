#!/usr/bin/env python

from setuptools import setup

setup(name='Sqlalchemy FSM',
      version='1.0',
      description='Finite state machine field for sqlalchemy',
      author='Peter',
      url='https://github.com/dagoof/sqlalchemy-fsm',
      py_modules=['sqlalchemy_fsm'],
      setup_requires=['pytest-runner'],
      tests_require=['pytest']
     )