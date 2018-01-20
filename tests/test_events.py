import pytest
import sqlalchemy
import sqlalchemy.event

import sqlalchemy_fsm

from conftest import Base

class EventModel(Base):
    __tablename__ = 'event_model'
    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key = True)
    state = sqlalchemy.Column(sqlalchemy_fsm.FSMField)

    def __init__(self, *args, **kwargs):
        self.state = 'new'
        super(EventModel, self).__init__(*args, **kwargs)

    @sqlalchemy_fsm.transition(source='*', target='state_a')
    def stateA(self):
        pass

    @sqlalchemy_fsm.transition(source='*', target='state_b')
    def stateB(self):
        pass


class TestEventListener(object):

    @pytest.fixture
    def model(self):
        return EventModel()


    @pytest.mark.parametrize('event_name', [
        'before_state_change',
        'after_state_change',
    ])
    def test_events(self, model, event_name):

        listener_result = []

        def on_update(instance, source, target):
            listener_result.append((source, target))

        sqlalchemy.event.listen(EventModel, event_name, on_update)

        expected_result = []
        assert listener_result == expected_result

        for handle_name in ('state_a', 'state_b', 'state_a', 'state_a', 'state_b'):
            expected_result.append((model.state, handle_name))
            if handle_name == 'state_a':
                handle = model.stateA
            else:
                handle = model.stateB
            handle()
            assert listener_result == expected_result


        # Remove the listener & check that it had an effect
        sqlalchemy.event.remove(EventModel, event_name, on_update)
        # Call the state handle & ensure that listener had not been called.
        model.stateA()
        assert listener_result == expected_result