from dataclasses import replace
from datetime import timedelta

import pytest
from sqlalchemy import func, select, text

from app import concept_learning, concepts
from app.concepts import Catalog
from app.concept_learning import ConceptRunner, Rejected, apply_proposal
from app.main import term_matches
from app.matching import local_review
from app.models import Concept, ConceptAlias, ConceptJob, ConceptProposal, Item, ItemConcept, now
from app.services import normalize
from conftest import login, publish

DIGITAL = '数码与影音'


@pytest.fixture(autouse=True)
def restore_catalog():
    yield
    concepts.reset()


def titles(response):
    assert response.status_code == 200, response.text
    return {row['title'] for row in response.json()['items']}


def learn(app, item_id, assignments, model='test-model'):
    """Run the production validation/persistence path with a stubbed model payload."""
    with app.state.session_factory() as db:
        concepts.configure(Catalog.load(db), legacy=False)
        return apply_proposal(db, db.get(Item, item_id), {'assignments': assignments}, model)


def laptop_assignment(**changes):
    payload = {'name': '笔记本', 'definition': '适合随身携带的个人电脑', 'parent': '电脑',
               'parent_definition': '以计算为主要用途的电子设备', 'category': DIGITAL,
               'aliases': ['笔记本', 'macbook'], 'evidence': '苹果笔记本'}
    payload.update(changes)
    return payload


def remote_settings(app):
    return replace(app.state.settings, ai_mode='remote', deepseek_key='test-key')


def test_model_learning_persists_family_hierarchy_and_links(client, app):
    login(client, 'seller')
    item = publish(client, title='MacBook Air M1', description='苹果笔记本，13 寸，功能正常',
                   category=DIGITAL, price=3200, tags=['笔记本', 'macbook']).json()
    learn(app, item['id'], [laptop_assignment()])

    with app.state.session_factory() as db:
        rows = {row.name: row.id for row in db.scalars(select(Concept))}
        assert set(rows) == {'笔记本', '电脑'}
        laptop = db.get(Concept, rows['笔记本'])
        assert laptop.parent_id == rows['电脑']
        assert laptop.category == DIGITAL
        assert db.get(ConceptAlias, 'macbook').concept_id == rows['笔记本']
        assert db.get(ItemConcept, (item['id'], rows['笔记本'])) is not None
        audit = db.scalar(select(ConceptProposal))
        assert (audit.status, audit.reason, audit.model) == ('APPLIED', 'learned', 'test-model')

    ids, aliases = concepts.expand_term('电脑')
    assert {rows['电脑'], rows['笔记本']} <= set(ids)
    assert {'macbook', '笔记本'} <= set(aliases)
    assert concepts.expand_term('笔记本')[0] == [rows['笔记本']]
    assert '笔记本' in normalize('MacBook Air')
    assert '电脑' in normalize('MacBook Air')

    assert 'MacBook Air M1' in titles(client.get('/api/v1/items/', params={'q': '电脑'}))
    assert 'MacBook Air M1' in titles(client.get('/api/v1/items/', params={'q': '笔记本'}))


def test_existing_family_is_reused_across_items(client, app):
    login(client, 'seller')
    first = publish(client, title='MacBook Air M1', description='苹果笔记本，13 寸',
                    category=DIGITAL, price=3200, tags=['笔记本']).json()
    learn(app, first['id'], [laptop_assignment()])
    with app.state.session_factory() as db:
        laptop_id = db.scalar(select(Concept.id).where(Concept.name == '笔记本'))

    second = publish(client, title='ThinkPad X1 Carbon', description='联想笔记本 thinkpad，功能正常',
                     category=DIGITAL, price=2800, tags=['笔记本']).json()
    learn(app, second['id'], [{'concept_id': laptop_id, 'aliases': ['thinkpad'],
                               'evidence': '联想笔记本'}])

    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Concept)) == 2
        assert db.get(ItemConcept, (second['id'], laptop_id)) is not None
        assert db.get(ConceptAlias, 'thinkpad').concept_id == laptop_id


def test_empty_assignments_are_applied_as_no_family(client, app):
    login(client, 'seller')
    item = publish(client, title='宿舍收纳盒', description='白色收纳盒，九成新',
                   category='宿舍生活与家电', price=20, tags=['收纳']).json()
    assert learn(app, item['id'], []).links == []
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Concept)) == 0
        audit = db.scalar(select(ConceptProposal))
        assert (audit.status, audit.reason) == ('APPLIED', 'no_family')


def test_non_object_payload_is_rejected_as_invalid_schema(client, app):
    login(client, 'seller')
    item = publish(client, title='MacBook Air M1', description='苹果笔记本，13 寸',
                   category=DIGITAL, price=3200, tags=['笔记本']).json()
    with pytest.raises(Rejected) as error:
        with app.state.session_factory() as db:
            apply_proposal(db, db.get(Item, item['id']), ['not', 'an', 'object'], 'test-model')
    assert error.value.reason == 'invalid_schema'
    with app.state.session_factory() as db:
        audit = db.scalar(select(ConceptProposal))
        assert (audit.status, audit.reason) == ('REJECTED', 'invalid_schema')


def test_alias_outside_item_text_is_rejected(client, app):
    login(client, 'seller')
    item = publish(client, title='MacBook Air M1', description='苹果笔记本，13 寸',
                   category=DIGITAL, price=3200, tags=['笔记本']).json()
    with pytest.raises(Rejected) as error:
        learn(app, item['id'], [laptop_assignment(aliases=['thinkpad'])])
    assert error.value.reason == 'ungrounded_alias'
    with app.state.session_factory() as db:
        assert db.scalar(select(ConceptProposal)).reason == 'ungrounded_alias'


def test_learned_accessory_does_not_join_product_family(client, app):
    login(client, 'seller')
    mouse = publish(client, title='静音无线鼠标', description='无线鼠标，附接收器',
                    category=DIGITAL, price=80, tags=['鼠标', '静音']).json()
    pad = publish(client, title='加大鼠标垫', description='桌面鼠标垫，未拆封',
                  category=DIGITAL, price=15, tags=['鼠标垫']).json()
    learn(app, mouse['id'], [{'name': '鼠标', 'definition': '计算机指针输入设备', 'category': DIGITAL,
                              'aliases': ['鼠标'], 'evidence': '无线鼠标'}])
    learn(app, pad['id'], [{'name': '鼠标垫', 'definition': '鼠标下方使用的垫子', 'category': DIGITAL,
                            'aliases': ['鼠标垫'], 'evidence': '桌面鼠标垫'}])

    found = titles(client.get('/api/v1/items/', params={'q': '鼠标'}))
    assert '静音无线鼠标' in found
    assert '加大鼠标垫' not in found
    assert not term_matches('鼠标', '大号鼠标垫')
    assert ' 鼠标 ' not in normalize('大号鼠标垫')

    smart = client.post('/api/v1/items/smart-search', json={'query': '想收一个鼠标'}).json()['items']
    assert '静音无线鼠标' in {row['title'] for row in smart}
    assert '加大鼠标垫' not in {row['title'] for row in smart}


def test_async_matching_uses_learned_aliases(client, app):
    login(client, 'seller')
    item = publish(client, title='MacBook Air M1', description='苹果笔记本，13 寸',
                   category=DIGITAL, price=3200, tags=['macbook']).json()
    learn(app, item['id'], [laptop_assignment()])
    review = local_review({'keywords': ['笔记本'], 'excluded_keywords': [], 'preferences': []},
                          {'id': 'i1', 'title': 'MacBook Air M1', 'description': '苹果笔记本',
                           'tags': ['macbook'], 'price_cents': 320000, 'campus': '燕园校本部',
                           'condition_grade': '9成新'})
    assert review.verdict == 'MATCH'
    assert review.evidence[0].quote == 'MacBook Air M1'


def test_fabricated_evidence_is_rejected_and_audited(client, app):
    login(client, 'seller')
    item = publish(client, title='MacBook Air M1', description='苹果笔记本，13 寸',
                   category=DIGITAL, price=3200, tags=['笔记本']).json()
    with pytest.raises(Rejected) as error:
        learn(app, item['id'], [laptop_assignment(evidence='这是一台游戏本')])
    assert error.value.reason == 'fabricated_evidence'
    with app.state.session_factory() as db:
        assert db.scalar(select(Concept)) is None
        audit = db.scalar(select(ConceptProposal))
        assert (audit.status, audit.reason) == ('REJECTED', 'fabricated_evidence')


def test_alias_conflict_and_unknown_concept_are_rejected(client, app):
    login(client, 'seller')
    laptop = publish(client, title='MacBook Air M1', description='苹果笔记本，13 寸',
                     category=DIGITAL, price=3200, tags=['笔记本', 'macbook']).json()
    learn(app, laptop['id'], [laptop_assignment()])

    tablet = publish(client, title='iPad 平板', description='ipad 平板，附 macbook 充电器',
                     category=DIGITAL, price=1800, tags=['平板']).json()
    with pytest.raises(Rejected) as conflict:
        learn(app, tablet['id'], [{'name': '平板', 'definition': '触屏便携设备', 'category': DIGITAL,
                                   'aliases': ['平板', 'macbook'], 'evidence': 'ipad 平板'}])
    assert conflict.value.reason == 'alias_conflict'

    with pytest.raises(Rejected) as unknown:
        learn(app, tablet['id'], [{'concept_id': 'missing', 'aliases': ['平板'],
                                   'evidence': 'ipad 平板'}])
    assert unknown.value.reason == 'unknown_concept'

    with app.state.session_factory() as db:
        reasons = [row.reason for row in db.scalars(
            select(ConceptProposal).where(ConceptProposal.status == 'REJECTED'))]
        assert reasons == ['alias_conflict', 'unknown_concept']
        assert db.scalar(select(func.count()).select_from(Concept)) == 2


def test_attribute_and_forbidden_alias_are_rejected(client, app):
    login(client, 'seller')
    item = publish(client, title='静音无线鼠标', description='静音无线鼠标，功能正常',
                   category=DIGITAL, price=200, tags=['静音', '鼠标']).json()
    with pytest.raises(Rejected) as error:
        learn(app, item['id'], [{'name': '静音鼠标', 'definition': '带静音特性的鼠标',
                                 'aliases': ['静音'], 'evidence': '静音无线鼠标'}])
    assert error.value.reason == 'forbidden_alias'


def test_catalog_cycle_blocks_further_learning(client, app):
    login(client, 'seller')
    item = publish(client, title='MacBook Air M1', description='苹果笔记本，13 寸',
                   category=DIGITAL, price=3200, tags=['笔记本']).json()
    with app.state.session_factory() as db:
        # Simulate a corrupted catalog: the FK is bypassed to write a cycle.
        db.execute(text('PRAGMA foreign_keys=OFF'))
        db.add_all([Concept(id='ca', name='甲类', definition='甲', parent_id='cb', source='test'),
                    Concept(id='cb', name='乙类', definition='乙', parent_id='ca', source='test')])
        db.commit()
    with pytest.raises(Rejected) as error:
        learn(app, item['id'], [laptop_assignment()])
    assert error.value.reason == 'cycle'


def test_catalog_depth_limit_blocks_runaway_hierarchy(client, app):
    login(client, 'seller')
    item = publish(client, title='MacBook Air M1', description='苹果笔记本，13 寸',
                   category=DIGITAL, price=3200, tags=['笔记本']).json()
    with app.state.session_factory() as db:
        parent = None
        for level in range(7):
            db.add(Concept(id=f'deep{level}', name=f'层{level}', definition='层级测试',
                           parent_id=parent, source='test'))
            db.flush()
            parent = f'deep{level}'
        db.commit()
    with pytest.raises(Rejected) as error:
        learn(app, item['id'], [{'name': '深类', 'definition': '超过深度上限', 'parent': '层6',
                                 'aliases': ['笔记本'], 'evidence': '苹果笔记本'}])
    assert error.value.reason == 'depth'


def test_query_time_never_calls_the_model(client, app, monkeypatch):
    login(client, 'seller')
    item = publish(client, title='MacBook Air M1', description='苹果笔记本，13 寸',
                   category=DIGITAL, price=3200, tags=['笔记本']).json()
    learn(app, item['id'], [laptop_assignment()])

    def explode(*args, **kwargs):
        raise AssertionError('concept learning must not run during queries')

    monkeypatch.setattr(concept_learning, 'propose', explode)
    assert 'MacBook Air M1' in titles(client.get('/api/v1/items/', params={'q': '电脑'}))
    response = client.post('/api/v1/items/smart-search', json={'query': '收一台电脑'})
    assert response.status_code == 200
    assert 'MacBook Air M1' in {row['title'] for row in response.json()['items']}


def test_enqueue_only_in_remote_mode(client, app):
    login(client, 'seller')
    item = publish(client, title='MacBook Air M1', description='苹果笔记本，13 寸',
                   category=DIGITAL, price=3200, tags=['笔记本']).json()
    with app.state.session_factory() as db:
        assert app.state.concept_learning.enqueue(db, item['id']) is False
        db.commit()
        assert db.get(ConceptJob, item['id']) is None

    runner = ConceptRunner(app.state.session_factory, remote_settings(app), app.state.mutation_lock)
    with app.state.session_factory() as db:
        assert runner.enqueue(db, item['id']) is True
        db.commit()
        job = db.get(ConceptJob, item['id'])
        assert (job.status, job.attempts, job.error_code) == ('PENDING', 0, '')
        assert runner.enqueue(db, item['id']) is False


def test_runner_applies_stubbed_proposal(client, app, monkeypatch):
    login(client, 'seller')
    item = publish(client, title='MacBook Air M1', description='苹果笔记本，13 寸',
                   category=DIGITAL, price=3200, tags=['笔记本']).json()
    runner = ConceptRunner(app.state.session_factory, remote_settings(app), app.state.mutation_lock)
    with app.state.session_factory() as db:
        runner.enqueue(db, item['id'])
        db.commit()
    monkeypatch.setattr(concept_learning, 'propose',
                        lambda *args, **kwargs: {'assignments': [laptop_assignment()]})
    runner.process(item['id'])

    with app.state.session_factory() as db:
        job = db.get(ConceptJob, item['id'])
        assert (job.status, job.attempts, job.error_code) == ('DONE', 1, '')
        laptop_id = db.scalar(select(Concept.id).where(Concept.name == '笔记本'))
        assert db.get(ItemConcept, (item['id'], laptop_id)) is not None


def test_learning_failure_keeps_item_published_and_retries(client, app, monkeypatch):
    login(client, 'seller')
    item = publish(client, title='MacBook Air M1', description='苹果笔记本，13 寸',
                   category=DIGITAL, price=3200, tags=['笔记本']).json()
    runner = ConceptRunner(app.state.session_factory, remote_settings(app), app.state.mutation_lock)
    with app.state.session_factory() as db:
        runner.enqueue(db, item['id'])
        db.commit()

    def fail(*args, **kwargs):
        raise RuntimeError('provider down')

    monkeypatch.setattr(concept_learning, 'propose', fail)
    runner.process(item['id'])
    with app.state.session_factory() as db:
        job = db.get(ConceptJob, item['id'])
        assert (job.status, job.attempts, job.error_code) == ('PENDING', 1, 'learning_error')
        assert db.get(Item, item['id']).status == 'ACTIVE'
        assert db.scalar(select(Concept)) is None

    for _ in range(2):
        with app.state.session_factory() as db:
            db.get(ConceptJob, item['id']).available_at = now() - timedelta(seconds=1)
            db.commit()
        runner.process(item['id'])
    with app.state.session_factory() as db:
        job = db.get(ConceptJob, item['id'])
        assert (job.status, job.attempts) == ('FAILED', 3)


def test_legacy_table_is_used_only_for_local_mode(client, app):
    with app.state.session_factory() as db:
        concepts.configure(Catalog.load(db), legacy=True)
    assert '电脑' in normalize('MacBook Air')
    assert term_matches('鼠标', '静音无线鼠标')
    assert not term_matches('鼠标', '大号鼠标垫')

    with app.state.session_factory() as db:
        concepts.configure(Catalog.load(db), legacy=False)
    assert '电脑' not in normalize('MacBook Air')