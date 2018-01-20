"""API functions."""


def _get_bound_meta(bound_method):
    try:
        meta = bound_method._sa_fsm
    except AttributeError:
        raise NotImplementedError('This is not transition handler')
    return meta.get_bound(bound_method.__self__)


def can_proceed(bound_method, *args, **kwargs):
    bound_meta = _get_bound_meta(bound_method)
    return bound_meta.transition_possible() and bound_meta.conditions_met(
        args, kwargs)


def is_current(bound_method):
    bound_meta = _get_bound_meta(bound_method)
    return bound_meta.target_state == bound_meta.current_state
