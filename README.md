# YTET

YTET는 YouTube URL을 넣으면 커버 이미지와 메타데이터가 포함된 오디오 파일이나, 등록 자막을 포함한 영상을 만드는 Windows용 로컬 앱입니다.

## 실행 준비

1. Windows에 Python 3.10 이상을 설치합니다.
2. Python 설치 화면에서 `Add python.exe to PATH`를 체크합니다.
3. 이 폴더를 원하는 위치에 둡니다. 예: `C:\Projects\YTET`
4. `YTET.cmd`를 더블클릭합니다.

첫 실행 때 `.venv-win` 가상환경을 만들고 필요한 패키지를 설치합니다. 설치가 끝나면 바탕화면에 `YTET` 바로가기도 생성됩니다.

앱 창이 뜨지 않으면 같은 폴더의 `app-error.log` 또는 `setup.log`를 확인하세요.

## 사용법

1. 앱 창에서 YouTube URL을 입력합니다.
2. `음원` 또는 `영상 - 자막/다중 오디오 포함`을 선택합니다.
3. 저장 폴더를 선택합니다.
4. `추출`을 누릅니다.

음원 포맷:

- `M4A/AAC`: Android/Windows에서 무난한 기본 추천
- `Original Opus`: YouTube 원본에 가장 가깝고 용량 효율이 좋음
- `MP3`: 오래된 기기나 앱 호환용

영상:

- 기본값은 `최고 품질 - 4K/8K 가능, MKV 가능`입니다. YouTube가 제공하는 최고 영상 스트림과 최고 오디오 스트림을 그대로 받아 합칩니다.
- YouTube의 4K 이상은 보통 H.264 MP4가 아니라 VP9/AV1 같은 별도 스트림으로 제공됩니다. 그래서 최고 품질 저장 결과는 `.mkv`가 될 수 있습니다.
- 용량이나 호환성이 더 중요하면 `1080p 이하 - MP4 호환/균형`, `720p 이하 - MP4 저용량`, `480p 이하 - MP4 최소 용량`을 선택합니다.
- 업로더가 등록한 한국어/영어 자막이 있으면 영상 파일 안에 자막 트랙으로 넣고, 플레이어 호환을 위해 같은 이름의 `.srt` 파일도 함께 저장합니다.
- 여러 언어 오디오가 제공되는 영상은 원본 오디오를 유지합니다. 원본 오디오가 한국어가 아니고 한국어 오디오가 제공되면 한국어 오디오 트랙도 영상 파일 안에 추가합니다.
- 자동 생성 자막만 있는 영상은 기본적으로 자막을 넣지 않습니다.

저장 파일명은 `artist - title.ext` 형식입니다. 오디오 파일 내부에는 제목, artist, 원본 URL, 커버 이미지 등 가능한 메타데이터가 들어갑니다.
영상 파일명은 `channel - title.ext` 형식입니다.

오디오 저장 시에는 최종 오디오 파일만 남깁니다. 커버 이미지와 메타데이터는 오디오 파일 안에 넣는 데만 사용하고, 별도 이미지 파일이나 `metadata.json`은 저장하지 않습니다.
영상 저장 시에는 최종 영상 파일과 한국어/영어 `.srt` 자막 파일만 남깁니다.

## 다른 PC로 옮기기

가장 안정적인 방법:

1. YTET 폴더를 통째로 복사합니다.
2. 용량을 줄이고 싶으면 복사 전에 `.venv-win` 폴더는 빼도 됩니다.
3. 새 PC에 Python 3.10 이상을 설치하고 `Add python.exe to PATH`를 체크합니다.
4. 새 PC에서 `YTET.cmd`를 더블클릭합니다.

`.venv-win`을 빼고 옮기면 새 PC에서 처음 실행할 때 패키지를 다시 설치합니다. 그래서 새 PC에는 인터넷 연결이 필요합니다.

## 폴더 안 파일

- `YTET.cmd`: 실행 파일처럼 누르는 런처
- `YouTubeAudioExtractor.cmd`: 예전 이름으로 실행해도 동작하도록 남긴 호환 런처
- `SETUP.ps1`: 첫 실행 환경 설치 스크립트
- `README.md`: 사용법
- `src`: 앱 내부 코드
- `requirements.txt`, `pyproject.toml`, `run_app.py`: 실행에 필요한 Python 구성 파일
- `setup.log`, `app-error.log`: 문제가 생겼을 때만 생기는 로그 파일

## 업데이트

YouTube 쪽 변경으로 다운로드가 실패하면 `yt-dlp`만 업데이트해 보세요.

```powershell
.\.venv-win\Scripts\python.exe -m pip install -U yt-dlp
```

## 주의

권한이 있는 콘텐츠에만 사용하세요. YouTube 서비스 약관과 지역 법규를 확인해야 합니다.

## 개발 및 배포

GitHub Actions 구성:

- `CI`: push와 pull request마다 Python 테스트를 실행합니다.
- `Release`: `main`에 push하면 `nightly` 프리릴리즈를 갱신하고, `v*` 태그를 push하면 정식 GitHub Release를 만듭니다.

로컬 테스트:

```powershell
python -m pip install -r requirements.txt
python -m pip install --no-deps -e .
python -m unittest discover -s tests
```
