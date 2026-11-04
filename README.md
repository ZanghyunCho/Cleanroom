# SC-P7500 USB 공개키 읽기 시험

## LK29Q5 유지보수 박스 실험용 EFU

- [진단용 v2 EFU](downloads/FW7560TL_LK29Q5-maintenance-diagnostic-v2.efu)
- [v2 변경 내용·검증 범위·SHA-256](downloads/LK29Q5-maintenance-diagnostic-v2.README.ko.md)

v2는 v1의 본문 합계·CROM 패딩 오류를 수정한 진단본입니다.
원본 ARM 대조 검사는 통과했으나 실기 설치·부팅·동작은 미검증입니다.

- [실패 보고된 v1 EFU — 분석용 보존](downloads/FW7560TL_LK29Q5-maintenance-prototype.efu)
- [변경 내용·검증 범위·SHA-256](downloads/LK29Q5-maintenance-prototype.README.ko.md)
- [Recovery Mode 진입 분석](downloads/LK29Q5-maintenance-prototype.RECOVERY.ko.md)

이 v1 후보는 실기 업데이트 후 Recovery Mode 진입이 보고되었습니다.
섹션 본문 합계와 CROM 토큰 패딩의 포장 결함을 확인했습니다.
기존 v1 파일은 원인 분석용으로 보존합니다.

## USB 읽기 시험 도구

Windows 10/11용 Python GUI와 읽기 전용 USB 보조 프로그램입니다.

- [사용 설명서](p7500_usb_probe/README.ko.md)
- [다운로드 ZIP](downloads/P7500-USB-Key-Read-Probe-v0.4.zip)

GitHub에서 ZIP 파일을 선택한 다음 **Download raw file** 버튼으로 PC에 저장하세요. ZIP SHA-256은 `1e264bcbb70858e50b06174298aef7fb124a00ed2a0d09144b1c08ef862bb555`입니다.

Python 3.10 이상이 필요합니다. 압축을 풀고 `run_gui.bat`을 실행한 뒤, 기존 서비스 도구의 `EprisDrv.dll`을 선택하세요.

소프트웨어 시험 34개와 원본 DLL 요청 패킷 대조를 통과했습니다. 실제 Windows USB 통신과 서비스 주소의 물리 플래시 대응은 아직 미검증입니다.

v0.2는 USB ID와 NVRAM 시리얼을 별도로 표시하며, 수신 HEX 보기·기존 JSON 재분석·연결 단계 기록을 지원합니다.

v0.3의 영역 범위 읽기는 D6의 4KiB 백업 범위 안과 경계 밖을 구분해 시험하고, 현재 일반/Repair 모드를 사용자 기록으로 남깁니다. 프린터 모드를 자동 변경하지 않습니다.

v0.4는 **영역 전체 2회 읽기**로 A3 64KiB / D6 4KiB를 읽고 회차별 BIN·SHA-256·불일치/누락 구간과 중간 JSONL을 저장합니다. 새 전체 읽기의 실기 시험은 아직 수행하지 않았습니다.
