# Deployment Guide — Samil Auto-Flow Auditor

이 앱은 **Demo Mode 기본 동작**(API 키·인터넷 불필요)이라 어디 배포해도 시연이
정상 동작합니다. 두 경로 모두 GitHub 레포(`pin9u/ax-node-assignment`,
브랜치 `claude/initial-setup-RQQMF`)에서 출발합니다.

---

## 🥇 Option A — Streamlit Community Cloud (권장)

> 무료 · Streamlit 앱 전용 · 5분 안에 공개 URL 생성

1. <https://share.streamlit.io/> 접속 → **Continue with GitHub**
2. GitHub OAuth로 `pin9u/ax-node-assignment` 레포 접근 권한 부여
3. **New app** → 다음과 같이 선택
   - Repository: `pin9u/ax-node-assignment`
   - Branch: `claude/initial-setup-RQQMF`
   - Main file path: `app.py`
   - App URL: `samil-auto-flow-auditor` (원하는 슬러그)
4. **(선택) Secrets**: Demo Mode는 키가 없어도 동작합니다.
   Real Mode까지 같이 시연하려면 *Advanced settings → Secrets* 에 아래 추가.
   ```toml
   ANTHROPIC_API_KEY = "sk-ant-…"
   CLAUDE_MODEL      = "claude-sonnet-4-6"
   ```
5. **Deploy** → 1~2분 후 `https://<slug>.streamlit.app/` 에서 접속.

> 빌드 로그가 실패하면 우측 상단 메뉴 **Manage app → Logs** 에서 원인 확인.
> 일반적으로 첫 콜드스타트 시 의존성 설치에 1분 정도 걸립니다.

### Streamlit Cloud 트러블슈팅
- *ModuleNotFoundError: streamlit_mermaid* — 본 앱은 Mermaid를
  CDN 스크립트로 직접 렌더하므로 streamlit_mermaid 패키지를 실제로 import
  하지 않습니다. requirements.txt 에 남아 있어도 문제 없음.
- *모든 시나리오에서 빈 화면이 뜸* — 사이드바에서 **🎬 Demo Mode**가
  선택되어 있는지 확인하고 **🎬 데모 시나리오 로드** 버튼을 누르세요.

---

## 🥈 Option B — Hugging Face Spaces

> 무료 · Streamlit SDK 기본 지원 · GPU 옵션 있음

1. <https://huggingface.co/new-space> 에서 새 Space 생성
   - Owner: 본인 계정
   - Space name: `samil-auto-flow-auditor`
   - License: MIT (or whatever you prefer)
   - SDK: **Streamlit**
   - Visibility: Public 또는 Private
2. *Files* 탭에서 두 가지 중 한 가지로 코드 동기화
   - **(쉬움)** **Files → Upload files → 직접 업로드** — `app.py`,
     `requirements.txt`, `assets/`, `modules/`, `samples/`, `.streamlit/`
   - **(권장)** Settings → Repository → "Link to a GitHub repository"
     (단, 양방향 미러가 필요하면 해당 경로 사용)
3. 루트에 `README.md`의 **최상단**에 다음 YAML 프런트매터를 붙여 두세요
   (HF Spaces는 이 메타데이터로 SDK·런타임을 결정).
   ```yaml
   ---
   title: Samil Auto-Flow Auditor
   emoji: 🧾
   colorFrom: orange
   colorTo: black
   sdk: streamlit
   sdk_version: "1.36.0"
   app_file: app.py
   pinned: false
   ---
   ```
   본 레포의 `huggingface_space/README.md`에 즉시 복사 가능한 풀 버전을 같이
   넣어 두었습니다.
4. Space는 자동으로 `requirements.txt`를 읽어 빌드 후 `app.py`를 띄웁니다.
5. URL: `https://huggingface.co/spaces/<owner>/samil-auto-flow-auditor`

### Hugging Face Spaces 트러블슈팅
- *PIL/Pillow ImportError* — Hugging Face는 시스템에 fontconfig가 깔려 있어
  Pillow가 한글 폰트를 자동으로 잡습니다. 별도 설정 불필요.
- *Build timeout* — 첫 빌드만 5분 가량. Settings → Hardware 에서 CPU 업그레이드 가능.

---

## 🥉 Option C — 로컬 시연 (가장 안전, 임원 발표 권장)

> 노트북에서 1분 셋업, 무선 인터넷 안 되어도 동작.

```bash
git clone https://github.com/pin9u/ax-node-assignment.git
cd ax-node-assignment
git checkout claude/initial-setup-RQQMF
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

브라우저가 자동으로 `http://localhost:8501` 을 엽니다.
사이드바에서 **🎬 Demo Mode** → 시나리오 선택 → **🎬 데모 시나리오 로드**.

> 발표 환경에서 가장 변수 적은 옵션. **임원 발표 전 1번은 반드시 로컬
> 리허설**을 권합니다 — 네트워크 끊겨도, 인증서 재발급 사고 나도 동작.

---

## 비교 표

| 옵션 | 비용 | 셋업 시간 | API 키 필요 | 오프라인 | 추천 시나리오 |
|---|---|---|---|---|---|
| A. Streamlit Cloud | Free | 5분 | 선택 | ❌ | 데모 링크 공유, 동료 리뷰 |
| B. HF Spaces | Free | 7분 | 선택 | ❌ | 포트폴리오, GPU 추후 확장 |
| C. 로컬 | Free | 1분 | 선택 | ✅ | **임원 발표 본 시연** |

---

## 보안 주의 (실 API 키 사용 시)

- API 키는 절대 git에 커밋하지 말 것 (`.env`, `secrets.toml`은 `.gitignore`에 등록됨).
- Streamlit Cloud / HF Spaces 는 둘 다 **암호화된 secrets store**를 제공.
- 키가 노출됐다면 console.anthropic.com → API Keys에서 즉시 revoke.
