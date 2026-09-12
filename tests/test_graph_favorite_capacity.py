from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_graph_favorites_support_twenty_boards_and_series_with_valid_listing_link() -> None:
    app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

    assert "MAX_GRAPH_BOARDS = 20, MAX_SERIES_PER_GRAPH = 20" in app
    assert "slice(0,MAX_GRAPH_BOARDS)" in app
    assert "slice(0,MAX_SERIES_PER_GRAPH)" in app
    assert "new.land.naver.com/search?sk=" in app
    assert "m.land.naver.com/search/result?query=" not in app
    assert "검은색" in app and app.index('name:"검은색"') > app.index('name:"청회색"')
    assert "0 / 20" in html
