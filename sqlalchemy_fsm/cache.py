"""Caching tools/classes"""

import weakref

class DictCache(object):
    """Generic object that uses dict-like object for caching."""

    __slots__ = ('cache', 'getDefault')

    def __init__(self, dictObject, getDefault):
        self.cache = dictObject
        self.getDefault = getDefault

    def getValue(self, key):
        """A method is faster than __getitem__""" 
        try:
            return self.cache[key]
        except KeyError:
            out = self.getDefault(key)
            self.cache[key] = out
            return out


def weakValueCache(getFunc):
    """A decorator that makes a new DictCache using function provided as value getter"""
    return DictCache(
        weakref.WeakValueDictionary(),
        getFunc
    )

def dictCache(getFunc):
    """Generic dict cache decorator"""
    return DictCache({}, getFunc)