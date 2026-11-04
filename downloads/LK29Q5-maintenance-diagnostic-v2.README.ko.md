# LK29Q5 유지보수 박스 진단용 v2

[v2 EFU 다운로드](FW7560TL_LK29Q5-maintenance-diagnostic-v2.efu)
· [SHA-256](FW7560TL_LK29Q5-maintenance-diagnostic-v2.efu.sha256)
· [검증 기록](LK29Q5-maintenance-diagnostic-v2.manifest.json)

GitHub에서 파일을 연 뒤 **Download raw file** 버튼으로 저장하세요.

**실기 설치·부팅·출력 성공은 아직 미검증인 진단용 파일입니다.**
v1에서 보고된 Recovery Mode 진입이 실제로 해결됐다고 확인한 버전은 아닙니다.

## v1 대비 수정

- 첫 섹션의 본문 합계 필드를 실제 값 `0xA561`로 갱신.
- 재압축 후 패딩을 3토큰으로 재계산: `691069 + 3 = 691072`, 16의 배수.
- 변경된 본문의 내부 SHA-1을 다시 계산.
- 원래 Epson 공개키·최신 수신 모듈·두 번째 CROM 프레임 보존.
- 선언 본문 길이는 실제 159,977,472바이트보다 1 큰 159,977,473바이트.

유지보수 박스 기능 패치 자체는 v1의 ARM 시험 80건을 통과한 모듈과 같습니다.
잔량 100, 소비 보고 0 및 추가 누적 중단, 사용 가능 반환과 정상 알림을
합성 RAM 시험에서 확인했습니다. 기존 저장 소비 이력은 삭제하지 않습니다.

## 확인한 범위

원본 ARM 합계 함수로 117,047,296바이트 전체를 검사해 성공(1)을 확인했습니다.
원본 로더의 기술자·DMA 설정과 LZ 재구성도 대조했습니다.
LZ 시험에는 Huffman 완료 경계 fixture를 사용했으므로 실제 하드웨어 Huffman
해제기의 검증은 아닙니다. ZIP CRC와 재추출 해시 검사는 통과했습니다.

PC 업데이터, 전체 EFU의 ARM 수신, 전체 부팅 및 실제 CSIC·USB·플래시 작업은
아직 검증하지 않았습니다. 원래 서명 바이트는 보존했지만 본문 변경으로 일반
ECDSA 검증은 실패하며, 선언 길이 차이에 관한 연구 경로에 의존합니다.

[v1 실패 원인 분석](LK29Q5-maintenance-prototype.RECOVERY.ko.md)의 v2 비교값은
이 진단본을 가리킵니다.

SHA-256:

```text
eae73400d8dea242ef462f9f74eedebe3893caeb11cb4c6d81e5c62b5998132f
```

Windows PowerShell:

```powershell
Get-FileHash .\FW7560TL_LK29Q5-maintenance-diagnostic-v2.efu -Algorithm SHA256
```
