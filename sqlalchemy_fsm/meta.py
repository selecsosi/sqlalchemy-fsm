"""FSM meta object."""

import collections

from . import util 


class FSMMeta(object):

    payload = transitions = conditions = sources = bound_cls = None
    extra_call_args = ()

    def __init__(
        self, payload, source, target,
        conditions, extra_args, bound_cls
    ):
        self.bound_cls = bound_cls
        self.payload = payload
        self.conditions = tuple(conditions)
        self.extra_call_args = tuple(extra_args)

        if target is not None:
            if not util.is_valid_fsm_state(target):
                raise NotImplementedError(target)
            self.target = target
        else:
            self.target = None

        if util.is_valid_source_state(source):
            all_sources = (source, )
        elif isinstance(source, collections.Iterable):
            all_sources = tuple(source)

            if not all(
                util.is_valid_source_state(el)
                for el in all_sources
            ):
                raise NotImplementedError(all_sources)
        else:
            raise NotImplementedError(source)

        self.sources = frozenset(all_sources)

    def get_bound(self, instance):
        return self.bound_cls(self, instance, self.payload)

    def __repr__(self):
        return "<{} sources={!r} target={!r} conditions={!r} " \
        "extra call args={!r} payload={!r}>".format(
            self.__class__.__name__, self.sources, self.target,
            self.conditions, self.extra_call_args, self.payload,
        )
