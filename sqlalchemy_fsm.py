import collections
import inspect as py_inspect

from functools import wraps
from sqlalchemy import types as SAtypes
from sqlalchemy import inspect


def is_valid_fsm_state(value):
    return isinstance(value, basestring) and value


class FSMMeta(object):

    transitions = conditions = sources = None

    def __init__(self, source, target, conditions):
        self.conditions = tuple(conditions)
        self.target = target

        if is_valid_fsm_state(source):
            all_sources = (source, )
        elif isinstance(source, collections.Sequence):
            all_sources = tuple(source)
        else:
            raise NotImplementedError(source)

        self.sources = frozenset(all_sources)

    def get_bound(self, instance):
        return BoundFSMMeta(self, instance)

class BoundFSMMeta(object):

    meta = instance = state_field = None
    
    def __init__(self, meta, instance):
        self.meta = meta
        self.instance = instance
        # Get the state field
        fsm_fields = [c for c in inspect(type(self.instance)).columns if isinstance(c.type, FSMField)]
        if len(fsm_fields) == 0:
            raise TypeError('No FSMField found in model')
        if len(fsm_fields) > 1:
            raise TypeError('More than one FSMField found in model')
        else:
            self.state_field = fsm_fields[0]

    @property
    def current_state(self):
        return getattr(self.instance, self.state_field.name)

    def transition_possible(self):
        return (self.current_state in self.meta.sources) or ('*' in self.meta.sources)

    def conditions_met(self, args, kwargs):
        return all(map(lambda f: f(self.instance, *args, **kwargs), self.meta.conditions))

    def to_next_state(self):
        setattr(self.instance, self.state_field.name, self.meta.target)

def transition(source='*', target=None, conditions=()):

    def inner_transition(func):
        assert not hasattr(func, '_sa_fsm'), "This attribute is claimed by using"
        func._sa_fsm = meta = FSMMeta(source, target, conditions)

        @wraps(func)
        def _change_state(instance, *args, **kwargs):
            bound_meta = meta.get_bound(instance)
            if not bound_meta.transition_possible():
                raise NotImplementedError('Cant switch from {} using method {}'.format(
                    bound_meta.current_state, func.__name__
                ))
            if not bound_meta.conditions_met(args, kwargs):
                return False
            # for condition in conditions:
            #     if not condition(instance, *args, **kwargs):
            #         return False
            func(instance, *args, **kwargs)
            bound_meta.to_next_state()
            return True

        return _change_state

    if not target:
        raise ValueError('Result state not specified')
    return inner_transition


def can_proceed(bound_method, *args, **kwargs):
    try:
        meta = bound_method._sa_fsm
    except AttributeError:
        raise NotImplementedError('This is not transition handler')

    bound_meta = meta.get_bound(bound_method.im_self)
    return bound_meta.transition_possible() and bound_meta.conditions_met(args, kwargs)


class FSMField(SAtypes.String):
    pass
