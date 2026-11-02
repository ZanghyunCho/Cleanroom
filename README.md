# SC-P7500 USB 공개키 읽기 시험

Windows 10/11용 Python GUI와 읽기 전용 USB 보조 프로그램입니다.

- [사용 설명서](p7500_usb_probe/README.ko.md)
- [다운로드 ZIP](downloads/P7500-USB-Key-Read-Probe-v0.1.zip)

GitHub에서 ZIP 파일을 선택한 다음 **Download raw file** 버튼으로 PC에 저장하세요. ZIP SHA-256은 `718a99506d1abbf9e5af699cac9a8853159777564cd381b6edc63515461542dc`입니다.

Python 3.10 이상이 필요합니다. 압축을 풀고 `run_gui.bat`을 실행한 뒤, 기존 서비스 도구의 `EprisDrv.dll`을 선택하세요.

소프트웨어 시험 20개와 원본 DLL 요청 패킷 대조를 통과했습니다. 실제 Windows USB 통신과 서비스 주소의 물리 플래시 대응은 아직 미검증입니다.
