import unittest
import sqlalchemy


from sqlalchemy_fsm import FSMField, transition, can_proceed, is_current
from sqlalchemy_fsm.exc import SetupError, PreconditionError, InvalidSourceStateError

from tests.conftest import Base

def condition_func(instance):
    return True


class BlogPostWithConditions(Base):
    __tablename__ = 'BlogPostWithConditions'
    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key = True)
    state = sqlalchemy.Column(FSMField)

    def __init__(self, *args, **kwargs):
        self.state = 'new'
        super(BlogPostWithConditions, self).__init__(*args, **kwargs)

    def model_condition(self):
        return True

    def unmet_condition(self):
        return False

    @transition(source='new', target='published', conditions=[condition_func, model_condition])
    def publish(self):
        pass

    @transition(source='published', target='destroyed', conditions=[condition_func, unmet_condition])
    def destroy(self):
        pass


class TestConditional(unittest.TestCase):
    def setUp(self):
        self.model = BlogPostWithConditions()

    def test_initial_staet(self):
        self.assertEqual(self.model.state, 'new')

    def test_known_transition_should_succeed(self):
        self.assertTrue(can_proceed(self.model.publish))
        self.model.publish()
        self.assertEqual(self.model.state, 'published')

    def test_unmet_condition(self):
        self.model.publish()
        self.assertEqual(self.model.state, 'published')
        self.assertFalse(can_proceed(self.model.destroy))
        self.assertRaises(PreconditionError, self.model.destroy)
        self.assertEqual(self.model.state, 'published')