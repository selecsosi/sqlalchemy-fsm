""" Transition decorator. """
import inspect as py_inspect

from functools import wraps
from sqlalchemy.ext.hybrid import hybrid_method

from . import bound, util, exc
from .meta import FSMMeta


def transition(source='*', target=None, conditions=()):

    def inner_transition(func):

        if py_inspect.isfunction(func):
            meta = FSMMeta(
                func, source, target, conditions, (), bound.BoundFSMFunction)
        elif py_inspect.isclass(func):
            # Assume a class with multiple handles for various source states
            meta = FSMMeta(
                func, source, target, conditions, (), bound.BoundFSMClass)
        else:
            raise NotImplementedError("Do not know how to {!r}".format(func))

        @wraps(func, updated=())
        def _change_fsm_state(instance, *args, **kwargs):
            bound_meta = _change_fsm_state._sa_fsm.get_bound(instance)
            if not bound_meta.transition_possible():
                raise exc.InvalidSourceStateError(
                    'Unable to switch from {} using method {}'.format(
                        bound_meta.current_state, func.__name__
                    )
                )
            if not bound_meta.conditions_met(args, kwargs):
                raise exc.PreconditionError("Preconditions are not satisfied.")
            return bound_meta.to_next_state(args, kwargs)

        def _query_fsm_state(cls):
            column = util.get_fsm_column(cls)
            target = _change_fsm_state._sa_fsm.target
            assert target, "Target must be defined at this level."
            return column == target

        _change_fsm_state.__name__ = "fsm::{}".format(func.__name__)

        _change_fsm_state._sa_fsm = meta

        return hybrid_method(_change_fsm_state, _query_fsm_state)

    return inner_transition
