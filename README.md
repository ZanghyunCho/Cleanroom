# SC-P7500 USB 공개키 읽기 시험

## P704 KH03P9 Stage 2: 잉크 10개 슬롯 잔량 100% / 사용량 0

- [Stage 2 EFU 다운로드](downloads/FW4838TL_KH03P9-P704-Stage2-all-ink-zero.efu)
- [변경·검증 범위](downloads/P704-KH03P9-Stage2.README.ko.md)
- [검증 결과](downloads/P704-KH03P9-Stage2.validation.json) · [재현 코드·자료](downloads/P704-KH03P9-Stage2-validation.zip)

사용자가 실기 통과를 보고한 P704 Stage 1을 유지하고 잉크 10개 슬롯으로 확장했습니다. 공통 회계·칩 사용량 접근·잔량 이벤트를 수정했으며 ARM 비교 1,295건과 최종 포장 검사를 통과했습니다. Stage 2의 실기 업데이트·부팅·칩 기록은 미검증입니다. 미장착·통신·인증 등 별도 오류 상태는 보존합니다.

## P704 KH03P9 Stage 1: 유지보수 잔량 100% / 사용량 0

- [Stage 1 EFU 다운로드](downloads/FW4838TL_KH03P9-P704-Stage1-maintenance-zero.efu)
- [변경 범위와 실기 확인](downloads/P704-KH03P9-Stage1.README.ko.md)
- [검증 결과](downloads/P704-KH03P9-Stage1.validation.json) · [검증 코드·자료](downloads/P704-KH03P9-Stage1-validation.zip)

P704 장착 카트리지의 알려진 ZA/YA 사용량·동기화·보고 경로를 0으로, 정상 잔량 보고를 100%로 수정했습니다. 원본/수정 ARM 비교 125건과 최종 포장 검사를 통과했습니다. 실제 업데이트·부팅·칩 기록은 미검증이며, 카트리지 미장착 기능은 포함하지 않습니다.

## I2 비정품 사용 확인 반복 경로 시험본

I1의 100% 표시가 작동하지만 비정품 확인이 반복된다는 사용자 보고에 따른 후보입니다. I1에서 특정 비정품 사용 승인 조회 한 곳만 변경했습니다. ARM 시험 9,160건과 포장 검사를 통과했지만 **실제 프린터의 경고 제거는 미검증**입니다. 실제 정품 인증이 아니라 해당 승인 조건을 완료된 것으로 취급합니다. I1의 잔량·소비 변경과 LOONA 로고를 유지합니다.

- [I2 EFU 다운로드](downloads/FW7560TL_LK29Q5-LOONA-I2-ink-approval.efu)
- [변경·검증·시험 순서](downloads/LK29Q5-ink-I2.README.ko.md)
- [상세 검증 결과](downloads/FW7560TL_LK29Q5-LOONA-I2-ink-approval.validation.json)
- [소스·검증 자료](downloads/LK29Q5-ink-I2-validation.zip)

## P704 KH03P9 A/B 대조군

- [A: 원본 본문 · 선언 길이 +1](downloads/FW4838TL_KH03P9-startup-A-envelope-only.efu)
- [B: 원본 코드 재압축 · 포장](downloads/FW4838TL_KH03P9-startup-B-original-code-reencoded.efu)
- [검증 범위와 시험 순서](downloads/P704-KH03P9-startup-controls.README.ko.md)
- [검증 결과](downloads/FW4838TL_KH03P9-startup-controls.validation.json) · [재현 코드와 분석 자료](downloads/P704-KH03P9-startup-controls-validation.zip)

공식 KH03P9 기반 포장 대조군입니다. 실제 업데이트·부팅은 미검증이며, 유지보수 카트리지 동작을 변경하지 않습니다.

## SC-P5300 Series KU25Q4 S2 전체 카트리지 잔량·사용량 시험본

사용자에게 통과가 보고된 S1의 유지보수 처리를 보존하고 10개 잉크 슬롯의 잔량 조회 100%·사용량 0 처리를 추가했습니다. 최종 파일에서 추출한 코드의 ARM 시험 7,063개와 포장 검사를 통과했습니다. **S2 실기 업데이트·부팅·소비 후 고정은 미검증**입니다.

- [S2 EFU 다운로드](downloads/FWCL14TL_KU25Q4-S2-all-cartridge-zero-usage.efu)
- [변경·검증·실기 확인 항목](downloads/KU25Q4-S2.README.ko.md)
- [상세 검증 결과](downloads/FWCL14TL_KU25Q4-S2-all-cartridge-zero-usage.validation.json)
- [재현 코드·ARM 시험 자료](downloads/KU25Q4-S2-validation.zip)

## SC-P5300 Series KU25Q4 S1 유지보수 사용량 0 시험본

두 유지보수 슬롯의 정상 숫자 잔량 100%, 사용량 읽기·설정·증가와 소수 누적값의 0 처리를 적용했습니다. 최종 EFU에서 추출한 코드로 ARM 시험 1,923개와 포장 검사를 통과했습니다. **실기 업데이트·부팅·실제 소비 후 고정은 미검증**입니다.

- [S1 EFU 다운로드](downloads/FWCL14TL_KU25Q4-S1-maintenance-zero-usage.efu)
- [변경·검증·실기 확인 항목](downloads/KU25Q4-S1.README.ko.md)
- [상세 검증 결과](downloads/FWCL14TL_KU25Q4-S1-maintenance-zero-usage.validation.json)
- [재현 코드·ARM 시험 자료](downloads/KU25Q4-S1-validation.zip)

## SC-P5300 Series KU25Q4 A·B 대조군

- [A: 원본 본문 유지·선언 길이 +1](downloads/FWCL14TL_KU25Q4-A-envelope-only.efu)
- [B: 원본 실행 코드 재압축·포장](downloads/FWCL14TL_KU25Q4-B-original-code-reencoded.efu)
- [변경 범위·검증·대조 순서](downloads/KU25Q4-controls.README.ko.md)
- [재현 스크립트·검증 자료](downloads/KU25Q4-controls-validation.zip)

두 대조군은 원본 실행 동작을 유지합니다. 포장·복원 검사를 통과했으며 **실기 업데이트·부팅은 미검증**입니다.


## I1 잉크 잔량·장착/브랜딩 보고 시험본

E+LOONA 기준의 I1 진단 후보입니다. 잔량 보고 100%, 식별한 두 소비 증가 경로의 증가량 0, 정상 장착·브랜딩 분류의 알림 출력을 적용했습니다. G/G2 변경은 포함하지 않습니다. ARM 시험 1,671건과 포장 검사를 통과했지만 **실기 부팅·인쇄 및 모든 정품/호환성 경고 제거는 미검증**입니다. 기존 잉크 종료·통신 오류를 일괄 해제하지 않습니다.

- [I1 EFU 다운로드](downloads/FW7560TL_LK29Q5-LOONA-I1-ink-report.efu)
- [변경·검증 범위·시험 안내](downloads/LK29Q5-ink-I1.README.ko.md)
- [상세 검증 결과](downloads/FW7560TL_LK29Q5-LOONA-I1-ink-report.validation.json)
- [소스·검증 자료](downloads/LK29Q5-ink-I1-validation.zip)


## G2 유지보수 카트리지 재검증 시험본

G2는 G의 버스 경로 분리와 조건부 원본 재검증을 결합한 진단 후보입니다. LOONA 로고를 유지합니다. ARM 시험 975건과 EFU 포장 검사를 통과했지만 **실기 부팅·미장착·제거 문제 해결 여부는 미검증**입니다. 먼저 장착 상태의 정상 부팅부터 확인합니다.

- [G2 EFU 다운로드](downloads/FW7560TL_LK29Q5-LOONA-G2.efu)
- [변경·제한·시험 순서](downloads/LK29Q5-startup-G2.README.ko.md)
- [검증 결과](downloads/FW7560TL_LK29Q5-LOONA-G2.validation.json)
- [소스·검증 자료](downloads/LK29Q5-startup-G2-validation.zip)

F1/F1+LOONA는 사용자 실기 보고상 장착 시 정상이고 미장착 부팅·작동 중 제거 시 진행되지 않습니다. 재장착 후 재부팅해야 정상화됩니다. 이전 G는 실제 실패 경로를 입증하지 못해 적용 보류했으며, G2 역시 진단 시험본입니다.


## LOONA 부팅 로고 시험본

제공된 검은 배경 LOONA 로고를 E/F1 각각에 추가한 시험본입니다. 기존 기준의 유지보수 코드를 보존합니다. **새 EFU의 실기 부팅·표시는 미검증입니다.** 현재 사용하는 기준에 맞춰 하나를 선택합니다.

- [E + LOONA](downloads/FW7560TL_LK29Q5-LOONA-E.efu)
- [F1 + LOONA](downloads/FW7560TL_LK29Q5-LOONA-F1.efu)
- [검증 범위·선택 방법·복구 안내](downloads/LK29Q5-LOONA.README.ko.md)
- [복원한 화면 미리보기](downloads/LK29Q5-LOONA-preview.png)

## LK29Q5 유지보수 박스 실험용 EFU

사용자는 E가 매우 정상적으로 동작한다고 보고했습니다. 실제 사용량 증가 중단을
작업 전후 비교로 확인한 결과는 아직 아닙니다. 다음은 원본 칩 생략 조건을 분리하는 F1입니다.

- [F1: 칩 생략 조건 1바이트 추가 진단본](downloads/FW7560TL_LK29Q5-startup-F1-profile-exemption.efu)
- [F1 검증 범위·실기 시험 순서](downloads/LK29Q5-startup-F1.README.ko.md)

**F1의 실기 부팅·칩 미인식 동작은 미검증입니다.** 먼저 카트리지를 장착한 상태로
정상 부팅되는지 확인합니다. 이 단계에서 멈추면 E로 되돌리고 미장착 시험은 진행하지 않습니다.
실제 폐잉크 수거 구조는 계속 필요합니다.

- [정상 동작이 보고된 E](downloads/FW7560TL_LK29Q5-startup-E-zero-new-consumption.efu)
- [E 변경 내용·검증·사용자 보고](downloads/LK29Q5-startup-E.README.ko.md)

- [수명 종료 카트리지의 100% 인식이 보고된 D](downloads/FW7560TL_LK29Q5-startup-D-lifetime-control.efu)
- [D 변경 내용·검증·사용자 보고](downloads/LK29Q5-startup-D.README.ko.md)

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


## I3 실시간 잉크 상태 보고 시험본

I2에서도 비정품 경고가 남는다는 보고에 따라, 별도 동기 상태 보고의 브랜딩 필드 한 곳을 추가 변경한 후보입니다. T44L 모델·용량 정보와 I1/I2의 기존 잔량·소비 변경, LOONA를 유지합니다. ARM 시험 9,784건과 EFU 검사를 통과했지만 **실제 경고 제거는 미검증**입니다.

- [I3 EFU 다운로드](downloads/FW7560TL_LK29Q5-LOONA-I3-ink-status.efu)
- [변경·검증 범위·시험 순서](downloads/LK29Q5-ink-I3.README.ko.md)
- [상세 검증 결과](downloads/FW7560TL_LK29Q5-LOONA-I3-ink-status.validation.json)
- [소스·검증 자료](downloads/LK29Q5-ink-I3-validation.zip)
