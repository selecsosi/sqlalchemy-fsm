from functools import wraps

from sqlalchemy.orm.instrumentation import register_class

import sqlalchemy.orm.events


@sqlalchemy.event.dispatcher
class FSMSchemaEvents(sqlalchemy.orm.events.InstanceEvents):
    """Define event listeners for FSM Schema (table) objects."""

    def before_state_change(self, source, target):
        """Event that is fired before the model changes
        form `source` to `target` state."""

    def after_state_change(self, source, target):
        """Event that is fired after the model changes
        form `source` to `target` state."""


class InstanceRef(object):
    """This class has to be passed to the dispatch call as instance.

    No idea why it is required.

    """

    __slots__ = ('target', )

    def __init__(self, target):
        self.target = target

    def obj(self):
        return self.target


class BoundFSMDispatcher(object):
    """Utility method that simplifies sqlalchemy event dispatch."""

    # dispatcher = FSMSchemaEvents

    def __init__(self, instance):
        self.manager = register_class(type(instance))
        self.ref = InstanceRef(instance)

        for name in dir(self.manager.dispatch):
            if name.startswith('_'):
                # Skip private fields
                continue

            attr = getattr(self.manager.dispatch, name)
            if callable(attr):
                setattr(self, name, self._makeBoundDispatchHandle(name))

    def _makeBoundDispatchHandle(self, name):
        handle = getattr(self.manager.dispatch, name)

        def _wrapped_handle(*args, **kwargs):
            return handle(self.ref, *args, **kwargs)
        _wrapped_handle.__name__ = name

        return _wrapped_handle
