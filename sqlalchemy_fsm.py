import collections
import warnings
import inspect as py_inspect

from functools import wraps, partial
from sqlalchemy import types as SAtypes
from sqlalchemy import inspect


def is_valid_fsm_state(value):
    return isinstance(value, basestring) and value

class FSMException(Exception):
    """Generic Finite State Machine Exception."""

class PreconditionError(FSMException):
    """Raised when transition conditions are not satisfied."""

class SetupError(FSMException):
    """Raised when FSM is configured incorrectly."""

class InvalidSourceStateError(FSMException, NotImplementedError):
    """Can not switch from current state to the requested state."""

class BoundFSMFunction(object):

    meta = instance = state_field = internal_handler = None
    
    def __init__(self, meta, instance, internal_handler):
        self.meta = meta
        self.instance = instance
        self.internal_handler = internal_handler
        # Get the state field
        fsm_fields = [c for c in inspect(type(self.instance)).columns if isinstance(c.type, FSMField)]
        if len(fsm_fields) == 0:
            raise SetupError('No FSMField found in model')
        elif len(fsm_fields) > 1:
            raise SetupError('More than one FSMField found in model ({})'.format(fsm_fields))
        else:
            self.state_field = fsm_fields[0]

    @property
    def target_state(self):
        return self.meta.target

    @property
    def current_state(self):
        return getattr(self.instance, self.state_field.name)

    def transition_possible(self):
        return (self.current_state in self.meta.sources) or ('*' in self.meta.sources)

    def conditions_met(self, args, kwargs):
        args = self.meta.extra_call_args + (self.instance, ) + tuple(args)
        kwargs = dict(kwargs)

        out = True
        for condition in self.meta.conditions:
            # Check that condition is call-able with args provided
            try:
                py_inspect.getcallargs(condition, *args, **kwargs)
            except TypeError:
                out = False
            else:
                out = condition(*args, **kwargs)
            if not out:
                # Preconditions failed
                break

        if out:
            # Check that the function itself can be called with these args
            try:
                py_inspect.getcallargs(self.internal_handler, *args, **kwargs)
            except TypeError as err:
                warnings.warn("Failure to validate handler call args: {}".format(err))
                # Can not map call args to handler's
                out = False
                if self.meta.conditions:
                    raise SetupError("Mismatch beteen args accepted by preconditons ({!r}) & handler ({!r})".format(
                        self.meta.conditions, self.internal_handler
                    ))
        return out

    def to_next_state(self, args, kwargs):
        args = self.meta.extra_call_args + (self.instance, ) + tuple(args)
        self.internal_handler(*args, **kwargs)
        setattr(self.instance, self.state_field.name, self.target_state)

    def __repr__(self):
        return "<{} meta={!r} instance={!r}>".format(self.__class__.__name__, self.meta, self.instance)


class BoundFSMObject(BoundFSMFunction):
    
    def __init__(self, *args, **kwargs):
        super(BoundFSMObject, self).__init__(*args, **kwargs)
        # Collect sub-handlers
        sub_handlers = []
        sub_instance = self.internal_handler
        for name in dir(sub_instance):
            try:
                attr = getattr(sub_instance, name)
                meta = attr._sa_fsm
            except AttributeError:
                # Skip non-fsm methods
                continue
            sub_handlers.append(attr)
        self.sub_handlers = tuple(sub_handlers)
        self.bound_sub_metas = tuple(self.mk_restricted_bound_sub_metas())

    @property
    def target_state(self):
        targets = tuple(set(meta.meta.target for meta in self.bound_sub_metas))
        assert len(targets) == 1, "One and just one target expected"
        return targets[0]

    def transition_possible(self):
        return any(sub.transition_possible() for sub in self.bound_sub_metas)

    def conditions_met(self, args, kwargs):
        return any(
            sub.transition_possible() and sub.conditions_met(args, kwargs)
            for sub in self.bound_sub_metas
        )

    def to_next_state(self, args, kwargs):
        can_transition_with = [
            sub for sub in self.bound_sub_metas
            if sub.transition_possible() and sub.conditions_met(args, kwargs)
        ]
        if len(can_transition_with) > 1:
            raise Exception("Can transition with multiple handlers ({})".format(can_transition_with))
        else:
            assert can_transition_with
        return can_transition_with[0].to_next_state(args, kwargs)

    def mk_restricted_bound_sub_metas(self):
        instance = self.instance
        my_sources = self.meta.sources
        my_target = self.meta.target
        my_conditions = self.meta.conditions
        my_args = self.meta.extra_call_args

        def source_intersection(sub_meta_sources):
            if '*' in my_sources:
                return sub_meta_sources
            elif '*' in sub_meta_sources:
                return my_sources
            elif my_sources.issuperset(sub_meta_sources):
                return my_sources.intersection(sub_meta_sources)
            else:
                return False

        def target_intersection(sub_meta_target):
            """Only two cases are supported: same target values and sub_meta target being set to `False`"""
            if sub_meta_target and (sub_meta_target != my_target):
                return True
            return my_target

        out = []

        for sub_handler in self.sub_handlers:
            handler_self = sub_handler.im_self
            sub_meta = sub_handler._sa_fsm

            sub_sources = source_intersection(sub_meta.sources)
            if not sub_sources:
                raise SetupError('Source state superset {super} and subset {sub} are not compatable'.format(
                    super=my_sources, sub=meta.sources))

            sub_target = target_intersection(sub_meta.target)
            if not sub_target:
                raise SetupError('Targets {super} and {sub} are not compatable'.format(
                    super=my_target, sub=sub_meta.target
                ))
            sub_conditions = my_conditions + sub_meta.conditions
            sub_args = (handler_self, ) + my_args + sub_meta.extra_call_args

            sub_meta = FSMMeta(sub_meta.payload, sub_sources, sub_target, sub_conditions, sub_args, sub_meta.bound_cls)
            out.append(sub_meta.get_bound(instance))

        return out

class BoundFSMClass(BoundFSMObject):

    def __init__(self, meta, instance, internal_handler):
        bound_object = internal_handler()
        super(BoundFSMClass, self).__init__(meta, instance, bound_object)

class FSMMeta(object):

    payload = transitions = conditions = sources = bound_cls = None
    extra_call_args = ()

    def __init__(self, payload, source, target, conditions, extra_args, bound_cls):
        self.bound_cls = bound_cls
        self.payload = payload
        self.conditions = tuple(conditions)
        self.target = target
        self.extra_call_args = tuple(extra_args)

        if is_valid_fsm_state(source):
            all_sources = (source, )
        elif isinstance(source, collections.Iterable):
            all_sources = tuple(source)
        else:
            raise NotImplementedError(source)

        self.sources = frozenset(all_sources)

    def get_bound(self, instance):
        return self.bound_cls(self, instance, self.payload)

    def __repr__(self):
        return "<{} sources={!r} target={!r} conditions={!r} extra call args={!r} payload={!r}>".format(
            self.__class__.__name__, self.sources, self.target,
            self.conditions, self.extra_call_args, self.payload,
        )

def _get_bound_meta(bound_method):
    try:
        meta = bound_method._sa_fsm
    except AttributeError:
        raise NotImplementedError('This is not transition handler')

    return meta.get_bound(bound_method.im_self)

def transition(source='*', target=None, conditions=()):

    def inner_transition(func):

        @wraps(func, updated=())
        def _change_fsm_state(instance, *args, **kwargs):
            bound_meta = _change_fsm_state._sa_fsm.get_bound(instance)
            if not bound_meta.transition_possible():
                raise InvalidSourceStateError('Cant switch from {} using method {}'.format(
                    bound_meta.current_state, func.__name__
                ))
            if not bound_meta.conditions_met(args, kwargs):
                raise PreconditionError("Preconditions are not satisfied.")
            return bound_meta.to_next_state(args, kwargs)

        _change_fsm_state.__name__ = "fsm::{}".format(func.__name__)

        if py_inspect.isfunction(func):
            meta = FSMMeta(func, source, target, conditions, (), BoundFSMFunction)
        elif py_inspect.isclass(func):
            # Assume a class with multiple handles for various source states
            meta = FSMMeta(func, source, target, conditions, (), BoundFSMClass)
        else:
            raise NotImplementedError("Do not know how to {!r}".format(func))

        _change_fsm_state._sa_fsm = meta

        return _change_fsm_state

    return inner_transition


def can_proceed(bound_method, *args, **kwargs):
    bound_meta = _get_bound_meta(bound_method)
    return bound_meta.transition_possible() and bound_meta.conditions_met(args, kwargs)

def is_current(bound_method):
    bound_meta = _get_bound_meta(bound_method)
    return bound_meta.target_state == bound_meta.current_state

class FSMField(SAtypes.String):
    pass
