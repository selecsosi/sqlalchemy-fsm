"""
Non-meta objects that are bound to a particular table & sqlalchemy instance.
"""

import warnings

import inspect as py_inspect
from functools import partial

from sqlalchemy import inspect as sqla_inspect


from . import exc, util, meta, events, cache
from .sqltypes import FSMField


@cache.weakValueCache
def COLUMN_CACHE(table_class):
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


class SqlAlchemyHandle(object):

    __slots__ = (
        "table_class", "record", "fsm_column",
        "dispatch", "column_name",
    )

    def __init__(self, table_class, table_record_instance=None):
        self.table_class = table_class
        self.record = table_record_instance
        self.fsm_column = COLUMN_CACHE.getValue(table_class)
        self.column_name = self.fsm_column.name

        if table_record_instance:
            self.dispatch = events.BoundFSMDispatcher(table_record_instance)


class BoundFSMBase(object):

    __slots__ = ("meta", "sqla_handle", "extra_call_args")

    def __init__(self, meta, sqla_handle, extra_call_args):
        self.meta = meta
        self.sqla_handle = sqla_handle
        self.extra_call_args = extra_call_args

    @property
    def target_state(self):
        return self.meta.target

    @property
    def current_state(self):
        return getattr(
            self.sqla_handle.record,
            self.sqla_handle.column_name
        )

    def transition_possible(self):
        return (
            '*' in self.meta.sources
        ) or (
            self.current_state in self.meta.sources
        )


class BoundFSMFunction(BoundFSMBase):

    __slots__ = BoundFSMBase.__slots__ + ("set_func", "my_args")

    def __init__(self, meta, sqla_handle, set_func, extra_call_args):
        super(BoundFSMFunction, self).__init__(meta, sqla_handle, extra_call_args)
        self.set_func = set_func
        self.my_args = self.meta.extra_call_args + self.extra_call_args + \
            (self.sqla_handle.record, )

    def get_call_iface_error(self, fn, args, kwargs):
        """Returhs 'Type' error describing function's api mismatch (if one exists)

        or None
        """
        try:
            py_inspect.getcallargs(fn, *args, **kwargs)
        except TypeError as err:
            return err
        return None

    def conditions_met(self, args, kwargs):
        conditions = self.meta.conditions
        if not conditions:
            # Performance - skip the check
            return True

        args = self.my_args + tuple(args)

        kwargs = dict(kwargs)

        out = True
        for condition in conditions:
            # Check that condition is call-able with args provided
            if self.get_call_iface_error(condition, args, kwargs):
                out = False
            else:
                out = condition(*args, **kwargs)

            if not out:
                # Preconditions failed
                break

        if out:
            # Check that the function itself can be called with these args
            err = self.get_call_iface_error(self.set_func, args, kwargs)
            if err:
                warnings.warn(
                    "Failure to validate handler call args: {}".format(err))
                # Can not map call args to handler's
                out = False
                if conditions:
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

        args = self.my_args + tuple(args)

        # self.sqla_handle.dispatch.before_state_change(
        #     source=old_state, target=new_state
        # )

        self.set_func(*args, **kwargs)
        setattr(
            sqla_target,
            self.sqla_handle.column_name,
            new_state
        )
        # self.sqla_handle.dispatch.after_state_change(
        #     source=old_state, target=new_state
        # )

    def __repr__(self):
        return "<{} meta={!r} instance={!r} function={!r}>".format(
            self.__class__.__name__,
            self.meta,
            self.sqla_handle,
            self.set_func,
        )


class TansitionStateArtithmetics(object):
    """Helper class aiding in merging transition state params."""

    def __init__(self, metaA, metaB):
        self.metaA = metaA
        self.metaB = metaB

    def source_intersection(self):
        """Returns intersected sources meta sources."""
        sources_a = self.metaA.sources
        sources_b = self.metaB.sources

        if '*' in sources_a:
            return sources_b
        elif '*' in sources_b:
            return sources_a
        elif sources_a.issuperset(sources_b):
            return sources_a.intersection(sources_b)
        else:
            return False

    def target_intersection(self):
        target_a = self.metaA.target
        target_b = self.metaB.target
        if target_a == target_b:
            # Also covers the case when both are None
            out = target_a
        elif None in (target_a, target_b):
            # Return value that is not None
            out = target_a or target_b
        else:
            # Both are non-equal strings
            out = None
        return out

    def joint_conditions(self):
        """Returns union of both conditions."""
        return self.metaA.conditions + self.metaB.conditions

    def joint_args(self):
        return self.metaA.extra_call_args + self.metaB.extra_call_args


@cache.dictCache
def InheritedBoundClasses(key):

    (child_cls, parent_meta) = key
    
    def _getSubTransitions(child_cls):
        sub_handlers = []
        for name in dir(child_cls):
            try:
                attr = getattr(child_cls, name)
                if attr._sa_fsm_meta:
                    sub_handlers.append((name, attr))
            except AttributeError:
                # Skip non-fsm methods
                continue
        return sub_handlers

    def _getBoundSubMetas(child_cls, sub_transitions, parent_meta):
        out = []

        for (name, transition) in sub_transitions:
            sub_meta = transition._sa_fsm_meta
            arithmetics = TansitionStateArtithmetics(parent_meta, sub_meta)

            sub_sources = arithmetics.source_intersection()
            if not sub_sources:
                raise exc.SetupError(
                    'Source state superset {super} '
                    'and subset {sub} are not compatable'.format(
                        super=parent_meta.sources,
                        sub=sub_meta.sources
                    )
                )

            sub_target = arithmetics.target_intersection()
            if not sub_target:
                raise exc.SetupError(
                    'Targets {super} and {sub} are not compatable'.format(
                        super=parent_meta.target,
                        sub=sub_meta.target
                    )
                )

            merged_sub_meta = meta.FSMMeta(
                sub_sources, sub_target,
                arithmetics.joint_conditions(),
                arithmetics.joint_args(),
                sub_meta.bound_cls
            )
            out.append((merged_sub_meta, transition._sa_fsm_transition_fn))

        return out

    out_cls = type(
        '{}::sqlalchemy_handle'.format(
            child_cls.__name__,
        ),
        (child_cls, ),
        {
            '_sa_fsm_sqlalchemy_handle': None,
            '_sa_fsm_sqlalchemy_metas': (),
        }
    )
    sub_transitions = _getSubTransitions(out_cls)
    out_cls._sa_fsm_sqlalchemy_metas = tuple(
        _getBoundSubMetas(
            out_cls, sub_transitions, parent_meta
        )
    )

    return out_cls


class BoundFSMClass(BoundFSMBase):

    __slots__ = BoundFSMBase.__slots__ + ("bound_sub_metas", )

    def __init__(self, meta, sqlalchemy_handle, child_cls, extra_call_args):
        super(BoundFSMClass, self).__init__(
            meta, sqlalchemy_handle, extra_call_args
        )
        child_cls = InheritedBoundClasses.getValue((child_cls, meta))
        child_object = child_cls()
        child_object._sa_fsm_sqlalchemy_handle = sqlalchemy_handle
        self.bound_sub_metas = [
            meta.get_bound(
                sqlalchemy_handle,
                set_fn,
                (child_object, )
            )
            for (meta, set_fn) in child_object._sa_fsm_sqlalchemy_metas
        ]

    @cache.caching_attr
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
