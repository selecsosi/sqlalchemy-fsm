"""
Non-meta objects that are bound to a particular table & sqlalchemy instance.
"""

import warnings
import inspect as py_inspect

from sqlalchemy import inspect as sqla_inspect


from . import exc, util, meta, events
from .sqltypes import FSMField


class SqlAlchemyHandle(object):

    table_class = record = fsm_column = dispatch = None

    def __init__(self, table_class, table_record_instance=None):
        self.table_class = table_class
        self.record = table_record_instance
        self.fsm_column = self.get_fsm_column(table_class)

        if table_record_instance:
            self.dispatch = events.BoundFSMDispatcher(table_record_instance)

    def get_fsm_column(self, table_class):
        fsm_fields = [
            col
            for col in sqla_inspect(table_class).columns
            if isinstance(col.type, FSMField)
        ]

        if len(fsm_fields) == 0:
            raise exc.SetupError('No FSMField found in model')
        elif len(fsm_fields) > 1:
            raise exc.SetupError(
                'More than one FSMField found in model ({})'.format(
                    fsm_fields
                )
            )
        return fsm_fields[0]


class BoundFSMBase(object):

    meta = sqla_handle = None

    def __init__(self, meta, sqla_handle):
        self.meta = meta
        self.sqla_handle = sqla_handle

    @property
    def target_state(self):
        return self.meta.target

    @property
    def current_state(self):
        return getattr(
            self.sqla_handle.record,
            self.sqla_handle.fsm_column.name
        )

    def transition_possible(self):
        return (
            self.current_state in self.meta.sources
        ) or (
            '*' in self.meta.sources
        )


class BoundFSMFunction(BoundFSMBase):

    set_func = None

    def __init__(self, meta, sqla_handle, set_func):
        super(BoundFSMFunction, self).__init__(meta, sqla_handle)
        self.set_func = set_func

    def conditions_met(self, args, kwargs):
        args = self.meta.extra_call_args + \
            (self.sqla_handle.record, ) + \
            tuple(args)

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
                py_inspect.getcallargs(self.set_func, *args, **kwargs)
            except TypeError as err:
                warnings.warn(
                    "Failure to validate handler call args: {}".format(err))
                # Can not map call args to handler's
                out = False
                if self.meta.conditions:
                    raise exc.SetupError(
                        "Mismatch beteen args accepted by preconditons "
                        "({!r}) & handler ({!r})".format(
                            self.meta.conditions, self.set_func
                        )
                    )
        return out

    def to_next_state(self, args, kwargs):
        old_state = self.current_state
        new_state = self.target_state

        sqla_target = self.sqla_handle.record

        args = self.meta.extra_call_args + (sqla_target, ) + tuple(args)

        self.sqla_handle.dispatch.before_state_change(
            source=old_state, target=new_state
        )

        self.set_func(*args, **kwargs)
        setattr(
            sqla_target,
            self.sqla_handle.fsm_column.name,
            new_state
            )
        self.sqla_handle.dispatch.after_state_change(
            source=old_state, target=new_state
        )

    def __repr__(self):
        return "<{} meta={!r} instance={!r}>".format(
            self.__class__.__name__, self.meta, self.sqla_handle)


class BoundFSMObject(BoundFSMBase):

    def __init__(self, meta, sqlalchemy_handle, child_object):
        super(BoundFSMObject, self).__init__(meta, sqlalchemy_handle)
        # Collect sub-handlers
        sub_handlers = []
        for name in dir(child_object):
            try:
                attr = getattr(child_object, name)
                meta = attr._sa_fsm_bound_meta
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
        sqla_handle = self.sqla_handle
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
            handler_fn = sub_handler._sa_fsm_transition_fn
            handler_self = sub_handler._sa_fsm_self
            sub_meta = sub_handler._sa_fsm_meta

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
                sub_sources, sub_target,
                sub_conditions, sub_args, sub_meta.bound_cls
            )
            out.append(sub_meta.get_bound(sqla_handle, handler_fn))

        return out


class BoundFSMClass(BoundFSMObject):

    def __init__(self, meta, sqlalchemy_handle, child_cls):
        child_cls_with_bound_sqla = type(
            '{}::sqlalchemy_handle::{}'.format(
                child_cls.__name__,
                id(sqlalchemy_handle)
            ),
            (child_cls, ),
            {
                '_sa_fsm_sqlalchemy_handle': sqlalchemy_handle,
            }
        )

        bound_object = child_cls_with_bound_sqla()
        super(BoundFSMClass, self).__init__(
            meta, sqlalchemy_handle, bound_object)
