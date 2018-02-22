import gc
import pytest
import sqlalchemy

import sqlalchemy_fsm

from tests.conftest import Base


class Benchmarked(Base):
    __tablename__ = 'benchmark_test'
    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    state = sqlalchemy.Column(sqlalchemy_fsm.FSMField)

    def __init__(self, *args, **kwargs):
        self.state = 'new'
        super(Benchmarked, self).__init__(*args, **kwargs)

    @sqlalchemy_fsm.transition(source='*', target='published')
    def published(self):
        pass

    @sqlalchemy_fsm.transition(source='*', target='hidden')
    def hidden(self):
        pass


class TestPerformanceSimple(object):

    @pytest.fixture
    def model(self, session):
        out = Benchmarked()
        session.add(out)
        session.commit()
        return out

    @pytest.mark.parametrize("in_expected_state", [True, False])
    def test_state_check(self, in_expected_state, benchmark, model, session):
        if in_expected_state:
            model.published.set()
        else:
            model.hidden.set()
        session.commit()
        # Expected state - published
        rv = benchmark(lambda: model.published())
        assert rv == in_expected_state

    def test_cls_selector(self, benchmark):
        benchmark(
            lambda: Benchmarked.published()
        )

    def test_set_performance(self, benchmark, model):

        def set_fn():
            """Cycle through two set() ops."""

            model.published.set()
            model.hidden.set()

        benchmark(set_fn)
