"""Package the three verified local diagnostic EFUs for GitHub downloads."""
from pathlib import Path
import hashlib
import io
import json
import zipfile

ROOT = Path(__file__).resolve().parent
DESTINATION = ROOT.parents[1] / 'downloads/P10000-FM001PA-CONTROL-DIAG'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    manifest = json.loads((ROOT / 'validation/control-isolation-packages.json').read_text())
    guide = (ROOT / 'CONTROL-ISOLATION.ko.md').read_text()
    packages = {}
    for variant, package in manifest['packages'].items():
        label = variant.upper()
        dest = DESTINATION / label
        dest.mkdir(parents=True, exist_ok=True)
        filename = package['output']
        efu = (ROOT / 'build' / filename).read_bytes()
        assert sha(efu) == package['sha256']
        archive_name = f'P10000-CONTROL-DIAG-{label}.zip'
        archive = ROOT / 'build' / archive_name
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_STORED) as z:
            for name, data in [(filename, efu), ('시험안내.md', guide.encode()),
                               ('SHA256SUMS.txt', (sha(efu) + '  ' + filename + '\n').encode())]:
                info = zipfile.ZipInfo(name, (2026, 11, 4, 0, 0, 0))
                z.writestr(info, data)
        parts = []
        with archive.open('rb') as source:
            index = 1
            while chunk := source.read(40 * 1024 * 1024):
                name = f'{archive_name}.{index:03d}'
                (dest / name).write_bytes(chunk)
                parts.append({'file': name, 'bytes': len(chunk), 'sha256': sha(chunk)})
                index += 1
        combined = b''.join((dest / p['file']).read_bytes() for p in parts)
        assert sha(combined) == sha(archive.read_bytes())
        with zipfile.ZipFile(io.BytesIO(combined)) as z:
            assert z.testzip() is None
            assert sha(z.read(filename)) == package['sha256']
            assert set(z.namelist()) == {filename, '시험안내.md', 'SHA256SUMS.txt'}
        (dest / 'SHA256SUMS.txt').write_text(
            ''.join(p['sha256'] + '  ' + p['file'] + '\n' for p in parts)
            + package['sha256'] + '  ' + filename + '\n')
        (dest / 'README.ko.md').write_text(
            f'# {label} 진단 EFU\n\n'
            '**원인 분리용이며 실기 동작 미검증입니다.** [전체 비교 방법](../README.ko.md)을 읽으세요.\n\n'
            '이 폴더의 `.zip.001`·`.zip.002`·`.zip.003`을 모두 같은 폴더에 받은 뒤 '
            '**7-Zip에서 `.zip.001`을 열어 압축 해제**하세요. GitHub 파일 페이지의 '
            'Download raw file을 사용하세요.\n\n'
            f'추출 파일: `{filename}`\n\nEFU SHA-256: `{package["sha256"]}`\n')
        packages[label] = {'efu': filename, 'efu_sha256': package['sha256'], 'parts': parts,
                           'reassembled_zip_and_EFU_verified': True}
    (DESTINATION / 'README.ko.md').write_text(
        '# SC-P10000 FM001PA 제어 변경 분리 진단\n\n'
        '**원인 분리용 진단 EFU입니다. 실기 성공을 확인한 해결판은 아닙니다.**\n\n'
        '**먼저 [BOTH](BOTH/README.ko.md)를 받으세요.** 원본 제어를 보존한 V2에 '
        '잔량·상태와 정품 정보 정규화 두 함수만 추가했습니다. '
        'V2가 정상 동작했던 것과 같은 실제 장착·잉크 공급 조건에서 비교합니다. '
        '**잉크 미장착 가상화는 포함하지 않았습니다.**\n\n'
        '| 파일 | 비교 목적 |\n| --- | --- |\n'
        '| [BOTH](BOTH/README.ko.md) | 두 정규화 함수를 함께 적용; 첫 비교 대상 |\n'
        '| [STATUS](STATUS/README.ko.md) | 잔량·상태 정규화만 적용 |\n'
        '| [INFO](INFO/README.ko.md) | 정품/리필/지역 정보 정규화만 적용 |\n\n'
        '각 폴더의 분할 파일 세 개를 전부 다운로드하여 같은 폴더에 놓고, '
        '**7-Zip에서 `.zip.001`을 열어 해제**하세요. 각 파일 페이지에서 '
        'Download raw file을 누르세요. 우선 BOTH 세 파일만 받으면 됩니다.\n\n'
        'BOTH가 정상이면 다른 V3 변경 또는 상호작용 쪽으로 범위를 좁힐 수 있습니다. '
        'BOTH에서도 재현되면 STATUS와 INFO를 따로 비교합니다. '
        '세 파일을 한꺼번에 설치하는 방식이 아닙니다.\n\n'
        '펌프 강제 구동·정지 비트 해제는 넣지 않았습니다. 내부 캐시 변경이며 화면 전용 변경은 아닙니다. '
        '정상 사용 기준은 기존 V2입니다.\n\n'
        '[상세 변경·검증·한계](../../firmware/P10000/CONTROL-ISOLATION.ko.md)\n')
    (DESTINATION / 'package-manifest.json').write_text(json.dumps(packages, indent=2) + '\n')
    print(json.dumps({k: {'parts': len(v['parts']), 'verified': True} for k, v in packages.items()}))


if __name__ == '__main__':
    main()
