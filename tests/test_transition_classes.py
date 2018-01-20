import unittest
import sqlalchemy
import pytest

from sqlalchemy_fsm import FSMField, transition, can_proceed, is_current
from sqlalchemy_fsm.exc import SetupError, PreconditionError, InvalidSourceStateError

from tests.conftest import Base


## Alternative syntax - separately defined transaction and sqlalchemy classes
class SeparatePublishHandler(object):

    @transition(source='new')
    def do_one(self, instance):
        instance.side_effect = "SeparatePublishHandler::did_one"

    @transition(source='hidden')
    def do_two(self, instance):
        instance.side_effect = "SeparatePublishHandler::did_two"

@transition(target='pre_decorated_publish')
class SeparateDecoratedPublishHandler(object):

    @transition(source='new')
    def do_one(self, instance):
        instance.side_effect = "SeparatePublishHandler::did_one"

    @transition(source='hidden')
    def do_two(self, instance):
        instance.side_effect = "SeparatePublishHandler::did_two"

class AltSyntaxBlogPost(Base):

    __tablename__ = 'AltSyntaxBlogPost'
    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key = True)
    state = sqlalchemy.Column(FSMField)
    side_effect = sqlalchemy.Column(sqlalchemy.String)

    def __init__(self, *args, **kwargs):
        self.state = 'new'
        self.side_effect = 'default'
        super(AltSyntaxBlogPost, self).__init__(*args, **kwargs)

    @transition(source='new', target='hidden')
    def hide(self):
        pass

    pre_decorated_publish = SeparateDecoratedPublishHandler
    post_decorated_publish = transition(target='post_decorated_publish')(SeparatePublishHandler)

class TestAltSyntaxBlogPost(object):

    @pytest.fixture
    def model(self):
        return AltSyntaxBlogPost()

    def test_pre_decorated_publish(self, model):
        model.pre_decorated_publish()
        assert model.state == 'pre_decorated_publish'
        assert model.side_effect == 'SeparatePublishHandler::did_one'

    def test_pre_decorated_publish_from_hidden(self, model):
        model.hide()
        assert model.state == 'hidden'
        assert is_current(model.hide)
        assert not is_current(model.pre_decorated_publish)
        model.pre_decorated_publish()
        assert model.state == 'pre_decorated_publish'
        assert is_current(model.pre_decorated_publish)
        assert model.side_effect == 'SeparatePublishHandler::did_two'

    def test_post_decorated_from_hidden(self, model):
        model.post_decorated_publish()
        assert model.state == 'post_decorated_publish'
        assert model.side_effect == 'SeparatePublishHandler::did_one'

    def test_post_decorated_publish_from_hidden(self, model):
        model.hide()
        assert model.state == 'hidden'
        model.post_decorated_publish()
        assert model.state == 'post_decorated_publish'
        assert model.side_effect == 'SeparatePublishHandler::did_two'

    def test_class_query(self, session, model):
        records = [AltSyntaxBlogPost() for idx in range(10)]
        hidden_records = records[:2]
        pre_decorated_published = records[3:5]
        post_decorated_published = records[-2:]

        [el.hide() for el in hidden_records]
        [el.pre_decorated_publish() for el in pre_decorated_published]
        [el.post_decorated_publish() for el in post_decorated_published]

        session.add_all(records)
        session.commit()

        all_ids = [el.id for el in records]
        for (handler, expected_group) in [
            ('hide', hidden_records),
            ('pre_decorated_publish', pre_decorated_published),
            ('post_decorated_publish', post_decorated_published),
        ]:
            expected_ids = set(el.id for el in expected_group)
            attr = getattr(AltSyntaxBlogPost, handler)
            matching = session.query(AltSyntaxBlogPost).filter(
                attr(),
                AltSyntaxBlogPost.id.in_(all_ids),
            ).all()
            assert len(matching) == len(expected_group)
            assert set(el.id for el in matching) == expected_ids

            not_matching = session.query(AltSyntaxBlogPost).filter(
                attr() == False,
                AltSyntaxBlogPost.id.in_(all_ids),
            ).all()
            assert len(not_matching) == (len(records) - len(expected_group))
            assert expected_ids.intersection(el.id for el in not_matching) == set(), \
                expected_ids.intersection(el.id for el in not_matching)