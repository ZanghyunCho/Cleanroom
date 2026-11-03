# SC-P10000 FM001PA 유지보수 사용량 0 — 시험용 EFU

**공식 원본의 사용량 조회 함수 8바이트만 변경한 시험본입니다. 실제 유지보수 카트리지는 장착해야 합니다.** 잉크·지역·장착 판정 변경은 없습니다.

**이전 지역 수정 EFU는 업데이트에 실패했습니다. 이번 파일도 같은 재포장 방식을 사용하며 실패 원인은 미해결입니다. 다시 Recovery 상태에 진입할 수 있습니다. 장비 수락·부팅·실제 표시·인쇄는 미검증입니다.**

Release API가 환경 네트워크 정책으로 차단되어 파일을 4개로 나눠 게시합니다. 아래 4개를 모두 같은 폴더에 다운로드하세요.

- [SC-P10000_FM001PA_MAINTENANCE-ONLY_EXPERIMENTAL.EFU.001](https://github.com/ZanghyunCho/Cleanroom/raw/refs/heads/delivery/p10000-fm001pa-maintenance-only-download/downloads/p10000-fm001pa-maintenance-only/SC-P10000_FM001PA_MAINTENANCE-ONLY_EXPERIMENTAL.EFU.001)
- [SC-P10000_FM001PA_MAINTENANCE-ONLY_EXPERIMENTAL.EFU.002](https://github.com/ZanghyunCho/Cleanroom/raw/refs/heads/delivery/p10000-fm001pa-maintenance-only-download/downloads/p10000-fm001pa-maintenance-only/SC-P10000_FM001PA_MAINTENANCE-ONLY_EXPERIMENTAL.EFU.002)
- [SC-P10000_FM001PA_MAINTENANCE-ONLY_EXPERIMENTAL.EFU.003](https://github.com/ZanghyunCho/Cleanroom/raw/refs/heads/delivery/p10000-fm001pa-maintenance-only-download/downloads/p10000-fm001pa-maintenance-only/SC-P10000_FM001PA_MAINTENANCE-ONLY_EXPERIMENTAL.EFU.003)
- [SC-P10000_FM001PA_MAINTENANCE-ONLY_EXPERIMENTAL.EFU.004](https://github.com/ZanghyunCho/Cleanroom/raw/refs/heads/delivery/p10000-fm001pa-maintenance-only-download/downloads/p10000-fm001pa-maintenance-only/SC-P10000_FM001PA_MAINTENANCE-ONLY_EXPERIMENTAL.EFU.004)

Windows 명령 프롬프트(cmd)에서 합치기:

```bat
copy /b SC-P10000_FM001PA_MAINTENANCE-ONLY_EXPERIMENTAL.EFU.001+SC-P10000_FM001PA_MAINTENANCE-ONLY_EXPERIMENTAL.EFU.002+SC-P10000_FM001PA_MAINTENANCE-ONLY_EXPERIMENTAL.EFU.003+SC-P10000_FM001PA_MAINTENANCE-ONLY_EXPERIMENTAL.EFU.004 SC-P10000_FM001PA_MAINTENANCE-ONLY_EXPERIMENTAL.EFU
certutil -hashfile SC-P10000_FM001PA_MAINTENANCE-ONLY_EXPERIMENTAL.EFU SHA256
```

Linux/macOS:

```sh
cat SC-P10000_FM001PA_MAINTENANCE-ONLY_EXPERIMENTAL.EFU.00[1-4] > SC-P10000_FM001PA_MAINTENANCE-ONLY_EXPERIMENTAL.EFU
shasum -a 256 SC-P10000_FM001PA_MAINTENANCE-ONLY_EXPERIMENTAL.EFU
```

복원 크기: **109,918,625 바이트**

SHA-256: `0c2eb756977bc233185bf316d565e5cfa7ed9d337465339bb91cae845d513efe`

[시험 절차 및 한계](README.ko.md) · [분할 파일 체크섬](PARTS-SHA256SUMS.txt)

표시 100%는 실제 폐잉크 수용량이 아닙니다. 물리 카트리지 관리는 계속 필요합니다.
