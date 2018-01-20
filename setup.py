#!/usr/bin/env python
import os

from setuptools import setup

THIS_DIR = os.path.dirname(os.path.abspath(__file__))

def get_production_requirements():
    """Returns list of production requirements from ./requirements/production.txt"""
    with open(os.path.join(THIS_DIR, "requirements", "production.txt"), "r") as fobj:
        return [
            line.strip()
            for line in fobj.readlines()
            if line.strip()
        ]

setup(
    name='sqlalchemy_fsm',
    packages=['sqlalchemy_fsm'],
    py_modules=['sqlalchemy_fsm'],
    description='Finite state machine field for sqlalchemy',
    author='Peter & Ilja',
    author_email='ilja@wise.fish',
    version='0.0.2',
    url='https://github.com/dagoof/sqlalchemy-fsm',
    install_requires=get_production_requirements(),
    setup_requires=['pytest-runner'],
    tests_require=['pytest']
)