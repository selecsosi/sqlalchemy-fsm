"""
Non-meta objects that are bound to a particular table & sqlalchemy instance.
"""

import warnings
import inspect as py_inspect

from functools import partial


from . import exc, util, meta, events


class BoundFSMFunction(object):

    meta = instance = state_field = internal_handler = None

    def __init__(self, meta, instance, internal_handler):
        self.meta = meta
        self.instance = instance
        self.internal_handler = internal_handler
        # Get the state field
        self.state_field = util.get_fsm_column(type(instance))
        self.dispatch = events.BoundFSMDispatcher(instance)

    @property
    def target_state(self):
        return self.meta.target

    @property
    def current_state(self):
        return getattr(self.instance, self.state_field.name)

    def transition_possible(self):
        return (
            self.current_state in self.meta.sources
        ) or (
            '*' in self.meta.sources
        )

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
                warnings.warn(
                    "Failure to validate handler call args: {}".format(err))
                # Can not map call args to handler's
                out = False
                if self.meta.conditions:
                    raise exc.SetupError(
                        "Mismatch beteen args accepted by preconditons "
                        "({!r}) & handler ({!r})".format(
                            self.meta.conditions, self.internal_handler
                        )
                    )
        return out

    def to_next_state(self, args, kwargs):
        old_state = self.current_state
        new_state = self.target_state

        args = self.meta.extra_call_args + (self.instance, ) + tuple(args)

        self.dispatch.before_state_change(
            source=old_state, target=new_state
        )

        self.internal_handler(*args, **kwargs)
        setattr(self.instance, self.state_field.name, new_state)
        self.dispatch.after_state_change(
            source=old_state, target=new_state
        )

    def __repr__(self):
        return "<{} meta={!r} instance={!r}>".format(
            self.__class__.__name__, self.meta, self.instance)


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
            raise exc.SetupError(
                "Can transition with multiple handlers ({})".format(
                    can_transition_with
                )
            )
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
            # Only two cases are supported:
            #   same target values and sub_meta target being set to `False`
            if sub_meta_target and (sub_meta_target != my_target):
                return None
            return my_target

        out = []

        for sub_handler in self.sub_handlers:
            handler_self = sub_handler.__self__
            sub_meta = sub_handler._sa_fsm

            sub_sources = source_intersection(sub_meta.sources)
            if not sub_sources:
                raise exc.SetupError(
                    'Source state superset {super} '
                    'and subset {sub} are not compatable'.format(
                        super=my_sources, sub=sub_meta.sources
                    )
                )

            sub_target = target_intersection(sub_meta.target)
            if not sub_target:
                raise exc.SetupError(
                    'Targets {super} and {sub} are not compatable'.format(
                        super=my_target, sub=sub_meta.target
                    )
                )
            sub_conditions = my_conditions + sub_meta.conditions
            sub_args = (handler_self, ) + my_args + sub_meta.extra_call_args

            sub_meta = meta.FSMMeta(
                sub_meta.payload, sub_sources, sub_target,
                sub_conditions, sub_args, sub_meta.bound_cls
            )
            out.append(sub_meta.get_bound(instance))

        return out


class BoundFSMClass(BoundFSMObject):

    def __init__(self, meta, instance, internal_handler):
        bound_object = internal_handler()
        super(BoundFSMClass, self).__init__(meta, instance, bound_object)
