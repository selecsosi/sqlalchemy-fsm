"""API functions."""

def _assert_is_bound_fsm_method(what):
    try:
        what._sa_fsm_meta
    except AttributeError:
        raise NotImplementedError('This is not transition handler')
    try:
        what._sa_fsm_bound_meta
    except AttributeError:
        raise NotImplementedError('This is not bound transition handler')
    return True


def can_proceed(bound_method, *args, **kwargs):
    _assert_is_bound_fsm_method(bound_method)
    return bound_method.can_proceed(*args, **kwargs)


def is_current(bound_method):
    _assert_is_bound_fsm_method(bound_method)
    return bound_method()
