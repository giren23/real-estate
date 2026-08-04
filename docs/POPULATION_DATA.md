# 인구·세대·가감동향

`data/raw/population/population.csv`에 다음 형식으로 넣으면 실거래 월별 데이터와 결합됩니다.

```csv
region_code,region_name,month,population,households,move_in,move_out
41135,경기도 성남시 분당구,2026-01,473000,199000,5200,5500
```

자동 계산:
- 전월 대비 인구 증감·증감률
- 세대수 증감
- 순이동 = 전입 - 전출
