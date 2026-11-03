# SC-P10000 FM001PA 지역 판정 실험본 다운로드

**전체 가상 카트리지 펌웨어가 아닙니다. 지역 판정 함수만 변경했습니다.** 칩 없는 장착 인식, 저잔량 리셋, 가상 ID 영구 저장은 포함하지 않습니다. 업데이터 수락·부팅·실제 인쇄는 미검증입니다.

GitHub 파일 크기 제한 때문에 EFU를 4개로 분할했습니다. 아래 파일을 모두 같은 폴더에 다운로드한 뒤 합치세요.

- [SC-P10000_FM001PA_REGION-ONLY_EXPERIMENTAL.EFU.001](https://github.com/ZanghyunCho/Cleanroom/raw/refs/heads/delivery/p10000-fm001pa-region-only-download/downloads/p10000-fm001pa-region-only/SC-P10000_FM001PA_REGION-ONLY_EXPERIMENTAL.EFU.001)
- [SC-P10000_FM001PA_REGION-ONLY_EXPERIMENTAL.EFU.002](https://github.com/ZanghyunCho/Cleanroom/raw/refs/heads/delivery/p10000-fm001pa-region-only-download/downloads/p10000-fm001pa-region-only/SC-P10000_FM001PA_REGION-ONLY_EXPERIMENTAL.EFU.002)
- [SC-P10000_FM001PA_REGION-ONLY_EXPERIMENTAL.EFU.003](https://github.com/ZanghyunCho/Cleanroom/raw/refs/heads/delivery/p10000-fm001pa-region-only-download/downloads/p10000-fm001pa-region-only/SC-P10000_FM001PA_REGION-ONLY_EXPERIMENTAL.EFU.003)
- [SC-P10000_FM001PA_REGION-ONLY_EXPERIMENTAL.EFU.004](https://github.com/ZanghyunCho/Cleanroom/raw/refs/heads/delivery/p10000-fm001pa-region-only-download/downloads/p10000-fm001pa-region-only/SC-P10000_FM001PA_REGION-ONLY_EXPERIMENTAL.EFU.004)

Linux/macOS:

```sh
cat SC-P10000_FM001PA_REGION-ONLY_EXPERIMENTAL.EFU.00[1-4] > SC-P10000_FM001PA_REGION-ONLY_EXPERIMENTAL.EFU
shasum -a 256 SC-P10000_FM001PA_REGION-ONLY_EXPERIMENTAL.EFU
```

Windows 명령 프롬프트(cmd):

```bat
copy /b SC-P10000_FM001PA_REGION-ONLY_EXPERIMENTAL.EFU.001+SC-P10000_FM001PA_REGION-ONLY_EXPERIMENTAL.EFU.002+SC-P10000_FM001PA_REGION-ONLY_EXPERIMENTAL.EFU.003+SC-P10000_FM001PA_REGION-ONLY_EXPERIMENTAL.EFU.004 SC-P10000_FM001PA_REGION-ONLY_EXPERIMENTAL.EFU
certutil -hashfile SC-P10000_FM001PA_REGION-ONLY_EXPERIMENTAL.EFU SHA256
```

복원한 파일 크기: **109,918,497 바이트**

SHA-256: `a670c9f796c98ddefcd77fe6a3cdb373c0d210ea14e1b4446f06b1041943ba25`

변경 범위와 미검증 항목은 [상세 설명](README.ko.md)을 확인하세요. 분할 파일의 체크섬은 [PARTS-SHA256SUMS.txt](PARTS-SHA256SUMS.txt)에 있습니다.
