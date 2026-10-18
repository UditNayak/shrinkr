def test_requests_are_counted_by_route(client):
    client.get("/missing-code")
    body = client.get("/metrics").text
    assert 'http_requests_total{method="GET",route="/{code}",status="404"}' in body
