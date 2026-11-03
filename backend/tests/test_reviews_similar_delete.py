from conftest import login, publish


def start_conversation(client, profile='buyer', item_id='sample-1'):
    login(client, profile)
    response = client.post(f'/api/v1/items/{item_id}/conversations', json={'body': '希望当面交易'})
    assert response.status_code == 201, response.text
    return response.json()['conversation']['id']


def deal(client, conversation_id, action, expected=200):
    response = client.post(f'/api/v1/conversations/{conversation_id}/deal', json={'action': action})
    assert response.status_code == expected, response.text
    return response.json()


def confirmed_deal(client):
    conversation_id = start_conversation(client)
    deal(client, conversation_id, 'request')
    login(client, 'seller')
    deal(client, conversation_id, 'reserve')
    deal(client, conversation_id, 'sold')
    login(client, 'buyer')
    deal(client, conversation_id, 'confirm')
    return conversation_id


def test_reviews_require_a_confirmed_deal(client):
    conversation_id = start_conversation(client)
    assert client.post(f'/api/v1/conversations/{conversation_id}/reviews',
                       json={'rating': 5}).status_code == 409

    deal(client, conversation_id, 'request')
    login(client, 'seller')
    deal(client, conversation_id, 'reserve')
    deal(client, conversation_id, 'sold')
    login(client, 'buyer')
    # A sold item still waits for the buyer's confirmation.
    assert client.post(f'/api/v1/conversations/{conversation_id}/reviews',
                       json={'rating': 5}).status_code == 409

    deal(client, conversation_id, 'confirm')
    response = client.post(f'/api/v1/conversations/{conversation_id}/reviews',
                           json={'rating': 5, 'body': ' 交易顺利，谢谢 ', 'tags': ['沟通顺畅', '准时守约', '沟通顺畅']})
    assert response.status_code == 201, response.text
    review = response.json()
    assert review['rating'] == 5
    assert review['body'] == '交易顺利，谢谢'
    assert review['tags'] == ['沟通顺畅', '准时守约']
    assert review['reviewer_id'] == 'demo-buyer'
    assert review['reviewee_id'] == 'demo-seller'
    assert review['item_title'] == '罗技 MX Master 3S 静音鼠标'
    assert client.post(f'/api/v1/conversations/{conversation_id}/reviews',
                       json={'rating': 4}).status_code == 409


def test_reviews_are_two_sided_and_public(client):
    conversation_id = confirmed_deal(client)
    assert client.post(f'/api/v1/conversations/{conversation_id}/reviews',
                       json={'rating': 5, 'body': '卖家很准时'}).status_code == 201
    login(client, 'seller')
    assert client.post(f'/api/v1/conversations/{conversation_id}/reviews',
                       json={'rating': 4, 'body': '买家沟通顺畅'}).status_code == 201

    result = client.get(f'/api/v1/conversations/{conversation_id}/reviews').json()
    assert result['deal_status'] == 'CONFIRMED'
    assert result['can_review'] is False
    assert len(result['reviews']) == 2

    seller_summary = client.get('/api/v1/users/demo-seller/reviews').json()
    assert seller_summary['summary']['average'] == 5.0
    assert seller_summary['summary']['count'] == 1
    assert seller_summary['summary']['distribution'][0] == {'rating': 5, 'count': 1}
    assert seller_summary['reviews'][0]['reviewer']['nickname'] == '林同学'

    buyer_summary = client.get('/api/v1/users/demo-buyer/reviews').json()
    assert buyer_summary['summary']['average'] == 4.0
    assert buyer_summary['reviews'][0]['item_title'] == '罗技 MX Master 3S 静音鼠标'

    # Public aggregates are readable without a session.
    client.cookies.clear()
    assert client.get('/api/v1/users/demo-seller/reviews').status_code == 200

    login(client, 'admin')
    assert client.get(f'/api/v1/conversations/{conversation_id}/reviews').status_code == 404
    assert client.get('/api/v1/users/not-a-user/reviews').status_code == 404


def test_review_payload_is_validated(client):
    conversation_id = confirmed_deal(client)
    for payload in ({'rating': 0}, {'rating': 6}, {'rating': 5, 'tags': ['不存在的标签']},
                    {'rating': 5, 'body': 'x' * 501}, {'rating': 5, 'tags': ['描述相符'] * 6}):
        assert client.post(f'/api/v1/conversations/{conversation_id}/reviews',
                           json=payload).status_code == 422, payload


def test_similar_items_rank_shared_category_tags_and_price(client):
    login(client, 'seller')
    first = publish(client, title='高数辅导书上册', category='课程资料与书籍', tags=['高数', '教材'],
                    price=40, campus='燕园校本部').json()['id']
    second = publish(client, title='高数习题集', category='课程资料与书籍', tags=['高数'],
                     price=45, campus='燕园校本部').json()['id']
    publish(client, title='闲置显示器', category='数码与影音', tags=['显示器'],
            price=300, campus='万柳学区')
    digital = publish(client, title='闲置键盘', category='数码与影音', tags=['键盘'],
                      price=120, campus='万柳学区').json()['id']
    sold = publish(client, title='高数笔记复印版', category='课程资料与书籍', tags=['高数', '教材'],
                   price=40, campus='燕园校本部').json()['id']
    assert client.patch(f'/api/v1/items/{sold}/status', json={'status': 'SOLD'}).status_code == 200

    response = client.get(f'/api/v1/items/{first}/similar?limit=12')
    assert response.status_code == 200
    items = response.json()['items']
    ids = [item['id'] for item in items]
    assert first not in ids
    assert sold not in ids
    # Demo book sample-2 is also a 高数 textbook, so it can rank above the new book;
    # what matters is that book-like candidates come before unrelated categories.
    assert ids.index(second) < ids.index(digital)
    assert all(item['status'] == 'ACTIVE' for item in items)


def test_similar_items_rejects_unknown_item(client):
    assert client.get('/api/v1/items/missing/similar').status_code == 404


def test_delete_conversation_hides_for_one_side_and_restores_on_new_message(client):
    conversation_id = start_conversation(client)
    login(client, 'seller')
    assert client.post(f'/api/v1/conversations/{conversation_id}/messages',
                       json={'body': '在的，可以面交'}).status_code == 201

    login(client, 'buyer')
    assert client.delete(f'/api/v1/conversations/{conversation_id}').status_code == 200
    assert client.get('/api/v1/conversations').json() == []
    assert client.get('/api/v1/notification-summary').json()['chat'] == 0
    # A deep link still works, and the seller's list is untouched.
    assert client.get(f'/api/v1/conversations/{conversation_id}').status_code == 200
    login(client, 'seller')
    assert [row['id'] for row in client.get('/api/v1/conversations').json()] == [conversation_id]

    assert client.post(f'/api/v1/conversations/{conversation_id}/messages',
                       json={'body': '明天下午三点可以吗'}).status_code == 201
    login(client, 'buyer')
    rows = client.get('/api/v1/conversations').json()
    assert [row['id'] for row in rows] == [conversation_id]
    assert rows[0]['unread_count'] == 1
    assert client.get('/api/v1/notification-summary').json()['chat'] == 1


def test_delete_conversation_blocks_open_deals_and_outsiders(client):
    conversation_id = start_conversation(client)
    deal(client, conversation_id, 'request')
    assert client.delete(f'/api/v1/conversations/{conversation_id}').status_code == 409

    login(client, 'seller')
    deal(client, conversation_id, 'reserve')
    deal(client, conversation_id, 'sold')
    login(client, 'buyer')
    deal(client, conversation_id, 'confirm')
    assert client.delete(f'/api/v1/conversations/{conversation_id}').status_code == 200

    login(client, 'admin')
    assert client.delete(f'/api/v1/conversations/{conversation_id}').status_code == 404


def test_admin_summary_and_announcement_delete(client):
    login(client, 'admin')
    created = client.post('/api/v1/admin/announcements',
                          json={'title': '临时公告', 'body': '这是一条用于测试删除的公告'})
    assert created.status_code == 201
    announcement_id = created.json()['id']
    assert announcement_id in [row['id'] for row in client.get('/api/v1/admin/announcements').json()]

    summary = client.get('/api/v1/admin/summary').json()
    assert set(summary) == {'reports', 'chat_reports', 'feedback', 'announcements', 'pending_total'}
    assert summary['announcements'] >= 1
    assert summary['pending_total'] == summary['reports'] + summary['chat_reports'] + summary['feedback']

    assert client.delete(f'/api/v1/admin/announcements/{announcement_id}').status_code == 200
    remaining = [row['id'] for row in client.get('/api/v1/admin/announcements').json()]
    assert announcement_id not in remaining
    assert client.delete(f'/api/v1/admin/announcements/{announcement_id}').status_code == 404

    login(client, 'buyer')
    assert client.get('/api/v1/admin/summary').status_code == 403
    assert client.delete(f'/api/v1/admin/announcements/{announcement_id}').status_code == 403
