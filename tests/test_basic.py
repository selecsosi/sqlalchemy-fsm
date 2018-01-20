import pytest
import sqlalchemy

from sqlalchemy_fsm import FSMField, transition, can_proceed, is_current
from sqlalchemy_fsm.exc import SetupError, PreconditionError, InvalidSourceStateError

from tests.conftest import Base

class BlogPost(Base):
    __tablename__ = 'blogpost'
    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key = True)
    state = sqlalchemy.Column(FSMField)

    def __init__(self, *args, **kwargs):
        self.state = 'new'
        super(BlogPost, self).__init__(*args, **kwargs)

    @transition(source='new', target='published')
    def publish(self):
        pass

    @transition(source='published', target='hidden')
    def hide(self):
        pass

    @transition(source='new', target='removed')
    def remove(self):
        raise Exception('No rights to delete %s' % self)

    @transition(source=['published','hidden'], target='stolen')
    def steal(self):
        pass

    @transition(source='*', target='moderated')
    def moderate(self):
        pass

class TestFSMField(object):

    @pytest.fixture
    def model(self):
        return BlogPost()

    def test_initial_state_instatiated(self, model):
        assert model.state == 'new'

    def test_meta_attached(self, model):
        assert model.publish._sa_fsm
        assert 'FSMMeta' in repr(model.publish._sa_fsm)

    def test_known_transition_should_succeed(self, model):
        assert can_proceed(model.publish)
        model.publish()
        assert model.state == 'published'

        assert can_proceed(model.hide)
        model.hide()
        assert model.state == 'hidden'

    def test_unknow_transition_fails(self, model):
        assert not can_proceed(model.hide)
        with pytest.raises(NotImplementedError) as err:
            model.hide()
        assert 'Unable to switch from' in str(err)

    def test_state_non_changed_after_fail(self, model):
        with pytest.raises(Exception) as err:
            model.remove()
        assert 'No rights to delete' in str(err)
        assert can_proceed(model.remove)
        assert model.state == 'new'

    def test_mutiple_source_support_path_1_works(self, model):
        model.publish()
        model.steal()
        assert model.state == 'stolen'

    def test_mutiple_source_support_path_2_works(self, model):
        model.publish()
        model.hide()
        model.steal()
        assert model.state == 'stolen'

    def test_star_shortcut_succeed(self, model):
        assert can_proceed(model.moderate)
        model.moderate()
        assert model.state == 'moderated'


    def test_query_filter(self, session):
        model1 = BlogPost()
        model2 = BlogPost()
        model3 = BlogPost()
        model4 = BlogPost()
        model3.publish()
        model4.publish()

        session.add_all([model1, model2, model3, model4])
        session.commit()

        ids = [model1.id, model2.id, model3.id, model4.id]

        # Check that one can query by fsm handler
        query_results = session.query(BlogPost).filter(
            BlogPost.publish(),
            BlogPost.id.in_(ids),
        ).all()
        assert len(query_results) == 2, query_results
        assert model3 in query_results
        assert model4 in query_results

        negated_query_results = session.query(BlogPost).filter(
            ~BlogPost.publish(),
            BlogPost.id.in_(ids),
        ).all()
        assert len(negated_query_results) == 2, query_results
        assert model1 in negated_query_results
        assert model2 in negated_query_results


class InvalidModel(Base):
    __tablename__ = 'invalidmodel'
    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key = True)
    state = sqlalchemy.Column(FSMField)
    action = sqlalchemy.Column(FSMField)

    def __init__(self, *args, **kwargs):
        self.state = 'new'
        self.action = 'no'
        super(InvalidModel, self).__init__(*args, **kwargs)

    @transition(source='new', target='no')
    def validate(self):
        pass

class TestInvalidModel(object):
    def test_two_fsmfields_in_one_model_not_allowed(self):
        model = InvalidModel()
        with pytest.raises(SetupError) as err:
            model.validate()
        assert 'More than one FSMField found' in str(err)


class Document(Base):
    __tablename__ = 'document'
    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key = True)
    status = sqlalchemy.Column(FSMField)

    def __init__(self, *args, **kwargs):
        self.status = 'new'
        super(Document, self).__init__(*args, **kwargs)

    @transition(source='new', target='published')
    def publish(self):
        pass


class TestDocument(object):
    def test_any_state_field_name_allowed(self):
        model = Document()
        model.publish()
        assert model.status == 'published'