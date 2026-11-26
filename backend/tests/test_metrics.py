from conftest import login


def test_prometheus_metrics_endpoint(client):
    # Trigger an API request
    res = client.get('/api/v1/health')
    assert res.status_code == 200

    # Scrape metrics endpoint
    metrics_res = client.get('/metrics')
    assert metrics_res.status_code == 200
    assert 'text/plain' in metrics_res.headers.get('content-type', '')
    body = metrics_res.text
    assert 'http_requests_total' in body
    assert 'http_request_duration_seconds' in body
    assert 'yandu_active_users' in body
    assert 'yandu_active_sessions' in body
    assert 'yandu_total_registered_users' in body
    assert 'yandu_user_registrations_total' in body
    assert 'yandu_visitor_funnel_events_total' in body
    assert 'yandu_anonymous_uv_rolling_1h' in body


def test_visitor_tracking_and_funnel(client):
    # 1. Anonymous visitor browsing sets yandu_vid cookie
    res = client.get('/api/v1/items/')
    assert res.status_code == 200
    assert 'yandu_vid' in res.cookies

    # 2. Unauthenticated request triggering 401
    res401 = client.get('/api/v1/users/me/overview')
    assert res401.status_code == 401

    # 3. Check metrics reflect visitor events
    metrics_res = client.get('/metrics')
    assert 'yandu_visitor_funnel_events_total{stage="browse"}' in metrics_res.text
    assert 'yandu_visitor_funnel_events_total{stage="auth_prompt_hit"}' in metrics_res.text


def test_admin_analytics_endpoints(client):
    # Login as admin
    login(client, 'admin')

    # Test user growth analytics
    res_growth = client.get('/api/v1/admin/analytics/user-growth?days=30')
    assert res_growth.status_code == 200
    growth_data = res_growth.json()
    assert 'total_users' in growth_data
    assert 'trend' in growth_data
    assert isinstance(growth_data['trend'], list)

    # Test visitor funnel analytics
    res_funnel = client.get('/api/v1/admin/analytics/visitor-funnel?days=7')
    assert res_funnel.status_code == 200
    funnel_data = res_funnel.json()
    assert 'total_unique_visitors' in funnel_data
    assert 'unregistered_browsers' in funnel_data
    assert 'funnel' in funnel_data
    assert len(funnel_data['funnel']) == 4
    assert 'friction_drop_off_pct' in funnel_data

    # Test business overview analytics
    res_biz = client.get('/api/v1/admin/analytics/business-overview')
    assert res_biz.status_code == 200
    biz_data = res_biz.json()
    assert 'liquidity' in biz_data
    assert 'ai_attribution' in biz_data
    assert 'friction' in biz_data
    assert 'dwell_insights' in biz_data
    assert biz_data['liquidity']['avg_days_to_sell'] is None
    assert 'sell_through_rate_pct' in biz_data['liquidity']
    assert 'first_inquiry_rate_72h_pct' in biz_data['liquidity']
    assert 'zombie_rate_pct' in biz_data['liquidity']
    assert 'total_gmv_yuan' in biz_data['liquidity']
    assert 'avg_order_value_yuan' in biz_data['liquidity']
    assert 'recent_30d_gmv_yuan' in biz_data['liquidity']
    assert 'push_to_chat_cvr_pct' in biz_data['ai_attribution']
    assert 'draft_abandonment_pct' in biz_data['friction']
    assert 'page_distribution' in biz_data['dwell_insights']
    assert 'hesitation_items' in biz_data['dwell_insights']


def test_dwell_time_tracking_and_advanced_metrics(client):
    # 1. Post a page dwell report
    dwell_payload = {
        'page': 'item_detail',
        'duration_seconds': 45
    }
    res = client.post('/api/v1/analytics/dwell', json=dwell_payload)
    assert res.status_code == 200
    assert res.json() == {'ok': True}

    # 2.check Prometheus metrics for new gauges
    metrics_res = client.get('/metrics')
    assert metrics_res.status_code == 200
    body = metrics_res.text
    assert 'yandu_first_inquiry_rate_72h_pct' in body
    assert 'yandu_zombie_listing_rate_pct' in body
    assert 'yandu_page_dwell_seconds_total' in body


def test_visitor_deduplication_and_healthcheck_exclusion(client):
    from app.main import visitor_tracker
    visitor_tracker._anon_vids.clear()

    # 1. Healthchecks and metrics scrapes without cookies must NOT inflate visitor count
    for _ in range(10):
        client.cookies.clear()
        assert client.get('/api/v1/health').status_code == 200
        assert client.get('/metrics').status_code == 200
    assert visitor_tracker.get_rolling_uv() == 0

    # 2. Multiple parallel requests before cookie is saved from same IP+UA only count as 1 visitor
    for route in ('/api/v1/items/', '/api/v1/wanted/', '/api/v1/announcements'):
        client.cookies.clear()
        client.get(route)
    assert visitor_tracker.get_rolling_uv() == 1

    # 3. Once logged in, the same browser is removed from anonymous visitor count
    login(client, 'admin')
    res = client.get('/api/v1/admin/analytics/business-overview')
    assert res.status_code == 200
    assert res.json()['realtime']['rolling_anon_uv'] == 0



def test_model_metrics_count_one_operation_and_ignore_direct_local_mode(monkeypatch, tmp_path):
    from app import services
    from app.config import Settings
    from app.observability import collect_provider_usage
    from prometheus_client import REGISTRY

    def value(metric, **labels):
        return REGISTRY.get_sample_value(metric, labels) or 0

    item_failure = 'yandu_model_calls_total', {'node': 'item_parse', 'status': 'error'}
    fallback = 'yandu_model_fallbacks_total', {'node': 'item_parse'}
    token = 'yandu_model_tokens_total', {'node': 'item_parse', 'kind': 'input'}
    latency = 'yandu_model_latency_seconds_count', {'node': 'item_parse'}
    counters = [item_failure, fallback, token, latency]
    before = [value(metric, **labels) for metric, labels in counters]

    def bad_remote(*args, **kwargs):
        collect_provider_usage({'usage': {'prompt_tokens': 10}})
        collect_provider_usage({'usage': {'prompt_tokens': 12, 'completion_tokens': 'invalid'}})
        return {'not_a_draft': True}

    monkeypatch.setattr(services, 'chat_json', bad_remote)
    settings = Settings(ai_mode='remote', deepseek_key='test', data_dir=tmp_path)
    services.parse_item('一把伞', settings)
    services.parse_item('一把伞', Settings(ai_mode='local', data_dir=tmp_path))
    assert [value(metric, **labels) - old for (metric, labels), old in zip(counters, before)] == [1, 1, 12, 1]


def test_candidate_metrics_count_invalid_result_and_skip_empty_batch(monkeypatch, tmp_path):
    import pytest
    from app import buyer_agent
    from app.config import Settings
    from prometheus_client import REGISTRY

    def errors():
        return REGISTRY.get_sample_value(
            'yandu_model_calls_total', {'node': 'candidate_review', 'status': 'error'}) or 0

    monkeypatch.setattr(buyer_agent, 'chat_json', lambda *a, **kw: {'assessments': []})
    settings = Settings(ai_mode='remote', deepseek_key='test', data_dir=tmp_path)
    before = errors()
    assert buyer_agent.review_candidates({}, [], settings) == []
    with pytest.raises(buyer_agent.ModelUnavailable):
        buyer_agent.review_candidates({}, [{'id': 'demo'}], settings)
    assert errors() == before + 1
