# SC-P7500 USB 공개키 읽기 시험

## LK29Q5 유지보수 박스 실험용 EFU

v3의 정지 이후 A/B 대조군과 잔량 보고 전용 C는 정상 작동했다고 사용자가 확인했습니다.
C는 낮은 잔량도 100%로 표시하지만, 수명 종료 카트리지는 여전히 수명 종료로 표시합니다.

- [D: 수명 종료 검출 두 곳만 추가 변경한 진단용 EFU](downloads/FW7560TL_LK29Q5-startup-D-lifetime-control.efu)
- [D 변경 내용·검증·시험 범위](downloads/LK29Q5-startup-D.README.ko.md)

**D의 실기 부팅과 수명 종료 카트리지 동작은 아직 미검증입니다.**
C에 코드 바이트 2개만 추가 변경하며 내부 상태·칩 통신·실제 카운터는 유지합니다.
소비량 0 처리와 카트리지 미장착 동작은 아직 포함하지 않습니다.

- [정상 동작과 100% 표시가 보고된 C](downloads/FW7560TL_LK29Q5-startup-C-remaining-report-only.efu)
- [C 변경 내용·검증·실기 보고](downloads/LK29Q5-startup-C.README.ko.md)

- [정상 동작이 보고된 원본 대조군 A/B · 비교 순서](downloads/LK29Q5-startup-controls.README.ko.md)
- [A: 원본 본문 그대로 + 선언 길이 1 증가](downloads/FW7560TL_LK29Q5-startup-A-envelope-only.efu)
- [B: 원본 실행 코드 재압축 + 선언 길이 1 증가](downloads/FW7560TL_LK29Q5-startup-B-original-code-reencoded.efu)

A/B는 원본 동작 대조군입니다. 두 파일에는 잔량 100%나 미장착 동작 패치가 없습니다.

- [시작 화면 정지가 보고된 v3 EFU — 분석용 보존](downloads/FW7560TL_LK29Q5-maintenance-diagnostic-v3.efu)
- [v3 변경 내용·검증 범위·SHA-256](downloads/LK29Q5-maintenance-diagnostic-v3.README.ko.md)
- [v3 검증 코드·결과 묶음](downloads/LK29Q5-maintenance-diagnostic-v3-validation.zip)

v3는 내부 상태 getter를 원복하고 원본의 프로필 조건 분기를 이용하는 진단본입니다.
소프트웨어/ARM 시험을 통과했지만, **실기 정상 부팅은 확인되지 않았습니다.**

- [시작 화면 정지가 보고된 v2 EFU — 분석용 보존](downloads/FW7560TL_LK29Q5-maintenance-diagnostic-v2.efu)
- [v2 변경 내용·검증 범위·SHA-256](downloads/LK29Q5-maintenance-diagnostic-v2.README.ko.md)

v2는 v1의 본문 합계·CROM 패딩 오류를 수정한 진단본입니다.
사용자는 업데이트가 진행된 뒤 유지보수 카트리지가 장착된 상태에서도 시작 화면에
계속 멈춘다고 보고했습니다. 정상 부팅·출력 성공은 확인되지 않았습니다.

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
