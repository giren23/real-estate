from realestate.core.dates import month_range

def test_month_range():
    assert month_range("202601", "202603") == ["202601", "202602", "202603"]
