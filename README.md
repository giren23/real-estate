# 전국 부동산 데이터 플랫폼

전국 모든 시군구와 모든 전용면적의 아파트 매매 실거래를 수집하고,
실거래가·평당가·거래량·인구/세대 동향을 분석하는 GitHub 기반 프로젝트입니다.

## 설치

1. 프로젝트 파일을 저장소 루트에 넣습니다.
2. GitHub Secret `MOLIT_SERVICE_KEY`를 등록합니다.
3. Actions → `Bootstrap real-estate data` → Run workflow
4. 초기 수집 개월은 1개월 권장
5. Settings → Pages → Source를 GitHub Actions로 설정

## Codespaces에서 설치

ZIP을 저장소 루트에 올린 뒤:

```bash
unzip -o real-estate-platform.zip
rm real-estate-platform.zip
git add .
git commit -m "Install real-estate platform"
git push origin main
```

## 주요 기능

- 모든 평형
- 지역/단지/면적 검색
- 실거래가·평당가 차트
- 단지별 최고·최저·중위가
- 인구·세대·전입·전출·순이동 결합
- 매일 자동 갱신
- 모바일 GitHub Pages
