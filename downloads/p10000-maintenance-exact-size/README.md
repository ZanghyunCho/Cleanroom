# P10000 FM001PA 유지보수 수정 — 공식 EFU와 전체 크기 일치

파일 크기: **109,893,043바이트** (공식 원본과 동일).
내부 파일 26개의 이름과 내용은 직전 유지보수 FIXED-LAYOUT 수정본과 바이트 단위로 동일하다.
공식 원본과 내부 코드가 같다는 뜻은 아니다. 유지보수 사용량 조회 8바이트 수정이 들어 있다.
외부 ZIP 압축 설정 변경, 선택적 ZIP 부가 메타데이터 제거, ZIP 주석 272바이트 추가만 수행했다.
ZIP CRC와 모든 내부 파일 동일성을 확인했다.

**인증값 미해결. 장비 수락/부팅 미검증. 이전 실험본은 업데이트 실패 후 Recovery 상태가 됐다.**
크기 일치는 인증 통과나 업데이트 성공을 보장하지 않는다. 실물 유지보수 카트리지 장착은 필요하다.

Release API는 네트워크 정책으로 차단되어 분할 게시한다. 아래 4개 파일을 모두 다운로드해 같은 폴더에서 합친다.

- [SC-P10000_FM001PA_MAINTENANCE_EXACT-SIZE_UNVERIFIED.EFU.001](https://github.com/ZanghyunCho/Cleanroom/raw/refs/heads/delivery/p10000-maintenance-exact-size/downloads/p10000-maintenance-exact-size/SC-P10000_FM001PA_MAINTENANCE_EXACT-SIZE_UNVERIFIED.EFU.001)
- [SC-P10000_FM001PA_MAINTENANCE_EXACT-SIZE_UNVERIFIED.EFU.002](https://github.com/ZanghyunCho/Cleanroom/raw/refs/heads/delivery/p10000-maintenance-exact-size/downloads/p10000-maintenance-exact-size/SC-P10000_FM001PA_MAINTENANCE_EXACT-SIZE_UNVERIFIED.EFU.002)
- [SC-P10000_FM001PA_MAINTENANCE_EXACT-SIZE_UNVERIFIED.EFU.003](https://github.com/ZanghyunCho/Cleanroom/raw/refs/heads/delivery/p10000-maintenance-exact-size/downloads/p10000-maintenance-exact-size/SC-P10000_FM001PA_MAINTENANCE_EXACT-SIZE_UNVERIFIED.EFU.003)
- [SC-P10000_FM001PA_MAINTENANCE_EXACT-SIZE_UNVERIFIED.EFU.004](https://github.com/ZanghyunCho/Cleanroom/raw/refs/heads/delivery/p10000-maintenance-exact-size/downloads/p10000-maintenance-exact-size/SC-P10000_FM001PA_MAINTENANCE_EXACT-SIZE_UNVERIFIED.EFU.004)

Windows cmd:

```bat
copy /b SC-P10000_FM001PA_MAINTENANCE_EXACT-SIZE_UNVERIFIED.EFU.001+SC-P10000_FM001PA_MAINTENANCE_EXACT-SIZE_UNVERIFIED.EFU.002+SC-P10000_FM001PA_MAINTENANCE_EXACT-SIZE_UNVERIFIED.EFU.003+SC-P10000_FM001PA_MAINTENANCE_EXACT-SIZE_UNVERIFIED.EFU.004 SC-P10000_FM001PA_MAINTENANCE_EXACT-SIZE_UNVERIFIED.EFU
certutil -hashfile SC-P10000_FM001PA_MAINTENANCE_EXACT-SIZE_UNVERIFIED.EFU SHA256
```

Linux/macOS:

```sh
cat SC-P10000_FM001PA_MAINTENANCE_EXACT-SIZE_UNVERIFIED.EFU.00[1-4] > SC-P10000_FM001PA_MAINTENANCE_EXACT-SIZE_UNVERIFIED.EFU
shasum -a 256 SC-P10000_FM001PA_MAINTENANCE_EXACT-SIZE_UNVERIFIED.EFU
```

SHA-256: `13a21394cab71e0d63e3c50641c899b70c694872fdfe9c7fddb6e457eb4857e0`
