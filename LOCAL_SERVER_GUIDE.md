# AIServer 사용 안내

## 접속 주소

- 이 PC: `http://localhost:8787/`
- 같은 공유기의 스마트폰·PC: `http://192.168.55.236:8787/`
- 외부 인터넷: `PUBLIC_URL.txt`에 적힌 `https://...trycloudflare.com` 주소

PC와 접속 기기가 같은 공유기(같은 Wi-Fi/유선망)에 연결되어 있어야 합니다. 공유기가 PC에 다른 IP를 배정하면 `ipconfig`의 IPv4 주소로 `192.168.55.236` 부분을 바꾸면 됩니다.

외부 인터넷 주소는 무료 Quick Tunnel 주소입니다. PC·로컬 서버·공개 터널이 모두 켜져 있어야 하며, 터널이 재시작되면 주소가 바뀝니다. 최신 주소는 항상 `PUBLIC_URL.txt`에서 확인할 수 있습니다.

## 처음 한 번

`Allow smartphone access (Administrator).cmd`를 두 번 클릭하고 Windows 관리자 확인창에서 **예**를 누릅니다. 외부 인터넷 전체가 아니라 같은 공유기 안의 기기만 8787 포트에 접속하도록 허용합니다.

## 평소 사용

- Windows 로그인 시 서버가 자동 시작됩니다.
- 수동 시작: `Start AIServer.cmd`
- 수동 종료: `Stop AIServer.cmd`
- 공개 접속 시작: `Start Public Access.cmd`
- 공개 접속 종료: `Stop Public Access.cmd`
- 브라우저에서 위 접속 주소를 엽니다.

## 자료 갱신

서버가 켜져 있으면 하루 한 번 최신 거래 15개 지역과 과거 이력 최대 70개 지역·연도를 순서대로 갱신합니다. 공식 자료제공 시스템의 **하루 다운로드 100회 제한**을 넘지 않도록 자동으로 멈추고 다음 날 이어서 받습니다.

우선순위는 성동구(옥수동) → 서울 전역 → 경기 전역 → 청주 → 창원 → 부산입니다. 실패 지역·연도는 `data/local/status.json`과 `data/local/logs`에 남고 다음 실행에서 다시 시도합니다.

## 데이터 위치

- 데이터베이스: `data/local/real_estate.sqlite3`
- 수집 원본 캐시: `data/local/raw`
- 진행 로그: `data/local/logs`
- 실패/진행 요약: `data/local/status.json`

이 폴더들은 GitHub에 올리지 않으며 D: 드라이브에만 보관됩니다.
