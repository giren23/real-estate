from realestate.collectors.complexes import _items

def test_complex_items_support_json_response():
    rows, total = _items({
        "response": {
            "header": {"resultCode": "00"},
            "body": {
                "items": [{"kaptCode": "A1", "kaptName": "이매촌한신"}],
                "totalCount": 1,
            },
        }
    })
    assert total == 1
    assert rows[0]["kaptName"] == "이매촌한신"
