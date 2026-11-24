# LiteLLM Proxy (AI Gateway) 정리

> 전체 문서(LiteLLM 정리)에서 Proxy(AI Gateway) 내용과 공통 내용만 추렸습니다. 2026년 11월 말 시점의 공식 문서, PyPI 릴리스, 보안 사고 분석 자료를 바탕으로 작성했습니다. LiteLLM은 릴리스가 매우 잦으므로 세부 옵션은 [공식 문서](https://docs.litellm.ai/docs/)에서 다시 확인하세요. 예제의 모델명(`gpt-6.1-sol`, `claude-sonnet-5` 등)은 공식 문서에 나온 예시이며, 실제로 쓸 수 있는 모델 ID는 각 프로바이더 문서를 따릅니다.

---

## 1. LiteLLM이란

LiteLLM은 100개 이상의 LLM 프로바이더를 **OpenAI API 형식 하나로** 호출하게 해 주는 오픈소스 프로젝트입니다. OpenAI, Anthropic, Google(Gemini, Vertex AI), AWS Bedrock, Azure OpenAI, 로컬에서 돌리는 Ollama·vLLM 등을 같은 방식으로 부를 수 있습니다. BerriAI가 개발하며, `litellm/enterprise/` 디렉터리를 제외한 코드는 MIT 라이선스입니다.

제공 형태는 두 가지이며, 이 문서는 Proxy를 다룹니다.

- **Python SDK**: 애플리케이션 코드에서 `import litellm`으로 쓰는 라이브러리
- **AI Gateway (Proxy Server)**: 팀이나 조직이 함께 쓰는 LLM 게이트웨이 서버. OpenAI 호환 REST API를 제공하므로 언어와 관계없이 호출할 수 있음

### 해결하는 문제

프로바이더마다 SDK, 인증 방식, 요청·응답 형식, 에러 타입이 다릅니다. 여러 모델을 함께 쓰면 아래 작업을 매번 직접 만들어야 합니다.

- 프로바이더별 SDK 연동과 응답 파싱
- 속도 제한(429)이나 장애에 대비한 재시도, 다른 모델로의 폴백
- 팀별 API 키 배포, 사용량·비용 집계, 예산 제한

LiteLLM은 이 부분을 공통 계층으로 제공합니다. 모델을 바꿀 때는 대부분 `model` 문자열만 바꾸면 됩니다.

---

## 2. 구조와 핵심 용어

```text
  애플리케이션 / 사내 서비스 / 코딩 에이전트
                   │
                   │  OpenAI 형식 요청 + virtual key
                   ▼
         ┌───────────────────┐
         │   LiteLLM Proxy   │   인증, 라우팅, 재시도·폴백,
         │   (AI Gateway)    │   비용 기록, 로깅, 가드레일
         └───────────────────┘
             │       │       │
             ▼       ▼       ▼
         OpenAI  Anthropic  Bedrock, Vertex AI, Ollama ...
```

| 용어 | 뜻 |
|---|---|
| 모델 문자열 | `프로바이더/모델` 형식의 호출 대상. 예: `anthropic/claude-sonnet-5` |
| `model_name` (모델 그룹) | 클라이언트가 요청할 때 쓰는 이름. 같은 이름을 가진 배포들이 한 그룹이 됨 |
| 배포 (deployment) | `model_list`의 항목 하나. 실제 모델, 엔드포인트, 키, 리전의 조합 |
| 폴백 (fallback) | 한 모델 그룹이 끝내 실패했을 때 넘어갈 다른 그룹 |
| master key | Proxy 관리자 키. 키 발급 같은 관리 API와 Admin UI 로그인에 사용 |
| virtual key | Proxy가 발급해 사용자·서비스에 나눠 주는 키. 모델 권한, 예산, 속도 제한을 붙일 수 있음 |

---

## 3. SDK와 Proxy 중 무엇을 쓸까

| 항목 | Python SDK | Proxy Server (AI Gateway) |
|---|---|---|
| 형태 | 앱에 포함되는 라이브러리 | 별도 서버 (기본 포트 4000) |
| 호출하는 쪽 | Python 코드 | OpenAI 호환 클라이언트면 모두 (Python, JS, Go, curl 등) |
| 프로바이더 키 | 앱이 직접 보유 | 게이트웨이만 보유, 사용자에게는 virtual key 배포 |
| 키·팀별 예산과 속도 제한 | 직접 구현 | 설정으로 제공 (Postgres 필요) |
| 운영 부담 | 없음 | 서버, Postgres(키·예산 기능), Redis(인스턴스가 여러 개일 때) |
| 잘 맞는 경우 | Python 서비스 하나, 프로토타입 | 여러 팀·서비스가 함께 쓰는 LLM 창구 |

Python 서비스 하나에서 여러 모델을 쓰는 정도라면 SDK로 시작하면 됩니다. 여러 팀, 여러 언어, 여러 서비스가 LLM을 함께 쓰고 키와 비용을 한곳에서 관리해야 할 때 Proxy를 도입합니다.

---

## 4. 설치

```bash
pip install 'litellm[proxy]'   # 또는: uv tool install 'litellm[proxy]'
```

컨테이너로 운영한다면 패키지를 설치하지 않고 공식 이미지를 씁니다(5.6절).

운영 환경에서는 버전을 고정해서 설치합니다(`'litellm[proxy]==<검증한 버전>'`). 2026년에 공식 배포 채널로 악성 버전이 두 차례 올라온 적이 있습니다. 자세한 내용은 6장에 정리했습니다.

---

## 5. Proxy Server (AI Gateway)

### 5.1 빠르게 띄워 보기

```bash
export OPENAI_API_KEY="..."                              # 프로바이더 키
export LITELLM_MASTER_KEY="sk-$(openssl rand -hex 32)"   # 게이트웨이 관리자 키
litellm --model openai/gpt-6.1-sol --host 127.0.0.1 --port 4000
```

호출해 봅니다. 다른 터미널에서 호출한다면 그 터미널에도 같은 `LITELLM_MASTER_KEY` 값을 설정합니다.

```bash
curl http://127.0.0.1:4000/v1/chat/completions \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "openai/gpt-6.1-sol", "messages": [{"role": "user", "content": "안녕하세요"}]}'
```

`--host` 기본값은 `0.0.0.0`(모든 네트워크 인터페이스)입니다. 옵션 없이 띄우면 같은 네트워크의 다른 기기에서도 접속할 수 있으므로, 로컬 테스트는 `127.0.0.1`로 띄웁니다.

### 5.2 config.yaml

실제 운영은 설정 파일로 합니다.

```yaml
model_list:
  - model_name: gpt-main                   # 클라이언트가 요청하는 이름
    litellm_params:
      model: openai/gpt-6.1-sol            # 실제로 호출할 모델
      api_key: os.environ/OPENAI_API_KEY   # 환경변수에서 읽음
  - model_name: gpt-main                   # 같은 이름이면 같은 그룹 → 로드밸런싱
    litellm_params:
      model: azure/<deployment-name>
      api_base: os.environ/AZURE_API_BASE
      api_key: os.environ/AZURE_API_KEY
      api_version: os.environ/AZURE_API_VERSION
  - model_name: claude
    litellm_params:
      model: anthropic/claude-sonnet-5
      api_key: os.environ/ANTHROPIC_API_KEY

router_settings:
  routing_strategy: simple-shuffle         # 기본값이자 공식 권장값

litellm_settings:
  num_retries: 2
  request_timeout: 600                     # 초 단위. 기본값은 6000초
  fallbacks: [{"gpt-main": ["claude"]}]    # gpt-main이 실패하면 claude로
  drop_params: true                        # 대상 모델이 지원하지 않는 파라미터는 빼고 전송

general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
```

| 섹션 | 역할 |
|---|---|
| `model_list` | 노출할 이름(`model_name`)과 실제 호출 정보(`litellm_params`) |
| `router_settings` | 라우팅 전략, cooldown, Redis 같은 Router 설정 |
| `litellm_settings` | 재시도, 타임아웃, 폴백, 캐시, 콜백, `drop_params` 같은 동작 설정 |
| `general_settings` | master key, DB, 알림 같은 서버 설정 |
| `environment_variables` | 설정 파일 안에서 지정하는 환경변수 |

`os.environ/변수명`은 그 환경변수 값을 읽습니다. 비밀 값은 이 방식으로 넣고 파일에 직접 쓰지 않습니다.

```bash
litellm --config config.yaml --host 127.0.0.1 --port 4000
```

### 5.3 프로바이더별 model 문자열과 인증 정보

`litellm_params.model`에는 `프로바이더/모델` 형식의 문자열을 씁니다. 인증 정보는 `api_key: os.environ/OPENAI_API_KEY`처럼 환경변수를 참조하며, 생략하면 아래 표의 기본 환경변수를 읽습니다.

| 프로바이더 | `model` 형식 | 주요 환경변수 |
|---|---|---|
| OpenAI | `openai/<model>` | `OPENAI_API_KEY` |
| Anthropic | `anthropic/<model>` | `ANTHROPIC_API_KEY` |
| Azure OpenAI | `azure/<deployment-name>` | `AZURE_API_KEY`, `AZURE_API_BASE`, `AZURE_API_VERSION` |
| AWS Bedrock | `bedrock/<model-id>` | AWS 기본 자격 증명(액세스 키 또는 IAM 역할), `AWS_REGION_NAME` |
| Google Vertex AI | `vertex_ai/<model>` | GCP 기본 자격 증명(ADC), `VERTEXAI_PROJECT`, `VERTEXAI_LOCATION` |
| Google AI Studio | `gemini/<model>` | `GEMINI_API_KEY` |
| Ollama (로컬) | `ollama/<model>` | 없음. 기본 주소 `http://localhost:11434` |
| OpenAI 호환 서버 (vLLM 등) | `openai/<model>` + `api_base` | 서버 설정에 따름 |

Bedrock 리전이나 Vertex AI 프로젝트·리전은 배포마다 `litellm_params`의 `aws_region_name`, `vertex_project`, `vertex_location`으로 지정할 수도 있습니다. 전체 목록은 [Providers 문서](https://docs.litellm.ai/docs/providers)에 있습니다.

### 5.4 라우팅, 재시도, 폴백

같은 `model_name`을 가진 배포들은 한 그룹이 되고, Proxy는 그룹 안에서 요청을 나눠 보냅니다. 실패하면 `num_retries`만큼 재시도하고, 끝내 실패하면 `fallbacks`에 지정한 다른 그룹으로 넘깁니다. 필요하면 5.2 설정의 각 섹션에 아래 항목을 추가합니다.

```yaml
router_settings:
  routing_strategy: simple-shuffle            # 기본값이자 공식 권장값
  allowed_fails: 3                            # 이 횟수보다 많이 실패한 배포는 잠시 후보에서 제외(cooldown)
  redis_host: os.environ/REDIS_HOST           # 인스턴스가 여러 개면 Redis로 상태 공유
  redis_port: os.environ/REDIS_PORT
  redis_password: os.environ/REDIS_PASSWORD

litellm_settings:
  context_window_fallbacks: [{"gpt-main": ["claude"]}]   # 컨텍스트 한도 초과 전용 폴백
```

- `simple-shuffle`은 배포별 `rpm`, `tpm`, `weight` 값으로 가중치를 두고 배포를 고릅니다. 공식 문서는 트래픽이 많을 때도 이 기본값을 유지하라고 권장합니다. `usage-based-routing` 계열은 요청 경로에 Redis 조회가 추가됩니다. 그 밖에 `latency-based-routing`, `least-busy`, `cost-based-routing` 전략이 있습니다.
- Proxy 인스턴스가 두 개 이상이면 Redis(7.0 이상)를 붙여 cooldown, 사용량, 속도 제한 상태를 공유합니다.

### 5.5 클라이언트에서 호출

게이트웨이가 OpenAI 호환 API를 제공하므로 OpenAI SDK의 `base_url`만 바꾸면 됩니다.

```python
import os
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:4000",
    api_key=os.environ["LITELLM_API_KEY"],  # 발급받은 virtual key
)
resp = client.chat.completions.create(
    model="gpt-main",                        # config.yaml의 model_name
    messages=[{"role": "user", "content": "안녕하세요"}],
)
print(resp.choices[0].message.content)
```

Anthropic Messages API(`/v1/messages`) 형식도 받으므로, Claude Code처럼 Anthropic API를 쓰는 도구도 게이트웨이를 거치게 할 수 있습니다.

### 5.6 Docker로 실행

```bash
docker run --rm \
  -v "$PWD/config.yaml:/app/config.yaml:ro" \
  -e OPENAI_API_KEY -e ANTHROPIC_API_KEY -e LITELLM_MASTER_KEY \
  -e AZURE_API_KEY -e AZURE_API_BASE -e AZURE_API_VERSION \
  -p 127.0.0.1:4000:4000 \
  ghcr.io/berriai/litellm:v1.108.15 \
  --config /app/config.yaml
```

- `-e`로는 config.yaml이 `os.environ/`로 참조하는 환경변수를 모두 넘깁니다.
- `v1.108.15`는 예시 태그입니다. 검증한 버전 태그나 digest로 고정하고, `latest`나 `main-stable`처럼 가리키는 대상이 바뀌는 태그는 운영에 쓰지 않습니다. 10월 사고 때는 이런 태그도 악성 이미지를 가리켰습니다.
- `-p 127.0.0.1:4000:4000`은 호스트 자신에게만 포트를 엽니다. 다른 서버에서 접근해야 하면 7장의 네트워크 항목을 먼저 확인합니다.
- Postgres까지 포함한 구성은 공식 [Docker Quick Start](https://docs.litellm.ai/docs/proxy/docker_quick_start)의 compose 파일을 참고합니다. 쓰기 전에 `ports:` 항목이 `127.0.0.1:`로 시작하는지, Postgres 포트가 밖으로 열려 있지 않은지 확인합니다.
- Kubernetes에는 공식 Helm 차트가 있습니다.

### 5.7 Virtual key, 예산, 사용량 추적

Proxy를 쓰는 주된 이유입니다. 프로바이더 키는 게이트웨이만 갖고, 사용자와 서비스에는 LiteLLM이 발급한 virtual key를 나눠 줍니다. 키마다 허용 모델, 예산, 속도 제한, 만료 기간을 걸 수 있고 사용 금액이 자동으로 기록됩니다.

필요한 설정은 다음과 같습니다. Docker로 띄운다면 이 값들도 `-e`로 넘깁니다.

- `DATABASE_URL`: PostgreSQL 연결 문자열 (`postgresql://<user>:<password>@<host>:<port>/<dbname>`)
- `LITELLM_MASTER_KEY`: 관리자 키
- `LITELLM_SALT_KEY`: DB에 저장하는 프로바이더 키를 암호화하는 키. 나중에 바꾸면 저장된 키를 읽을 수 없게 되므로 처음 정한 값을 안전하게 보관합니다.

키 발급 예시입니다. `max_budget`은 USD 단위입니다.

```bash
curl -X POST http://127.0.0.1:4000/key/generate \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"models": ["gpt-main"], "max_budget": 20, "duration": "30d", "rpm_limit": 60, "metadata": {"team": "search"}}'
```

응답의 `key` 값(`sk-...`)을 서비스에 전달합니다. 사용량은 `/key/info`, `/user/info`, `/team/info`로 조회합니다.

- 사용 금액은 커뮤니티가 관리하는 모델별 가격표로 계산한 추정치입니다. 가격표는 기본적으로 원격의 최신본을 받아 쓰며, 외부 접속이 막힌 환경에서는 `LITELLM_LOCAL_MODEL_COST_MAP="True"`로 패키지에 든 사본을 씁니다. 프로바이더와 맺은 할인·약정 가격은 반영되지 않습니다.
- DB 없이 실행하면 virtual key 요청이 실패하고(`No connected db.`), `max_budget` 같은 예산도 강제되지 않습니다. 예산 제한이 중요하면 DB를 붙이고, 프로바이더 콘솔에도 사용 한도를 걸어 둡니다.
- Admin UI는 `http://127.0.0.1:4000/ui`입니다. 사용자명은 `admin`, 비밀번호는 master key입니다. 모델 추가, 키 발급, 사용량 대시보드, Playground를 제공합니다.

### 5.8 로깅과 알림

```yaml
litellm_settings:
  success_callback: ["langfuse"]   # LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY 환경변수 필요

general_settings:
  alerting: ["slack"]              # SLACK_WEBHOOK_URL 환경변수 필요
```

- Langfuse 외에 LangSmith, Datadog, OpenTelemetry, S3 등으로 요청·응답·비용·지연 시간을 보낼 수 있습니다.
- Slack 알림은 멈춘 요청, 느린 응답, 예산 관련 이벤트를 알려 줍니다.
- 콜백에는 프롬프트와 응답 본문이 함께 전송될 수 있으므로, 민감한 데이터를 다룬다면 메시지 로깅을 끄거나 마스킹(redaction) 설정을 먼저 확인합니다.

### 5.9 그 밖의 게이트웨이 기능

| 기능 | 내용 |
|---|---|
| 캐싱 | Redis, 인메모리, S3, 시맨틱 캐시 등으로 같은 요청의 응답 재사용 |
| 가드레일 | 프롬프트 인젝션 탐지, PII 마스킹 같은 입출력 검사. 자체 기능과 외부 서비스 연동 |
| MCP Gateway | MCP 서버를 게이트웨이에 등록하고 키·팀별로 도구 접근 제어 |
| A2A Agent Gateway | A2A 프로토콜 에이전트를 게이트웨이 뒤에 두고 호출 |
| Auto Router | 프롬프트 복잡도를 보고 저렴한 모델과 고성능 모델 중 하나를 자동 선택 |
| Pass-through | Bedrock, Vertex AI 등의 네이티브 API를 게이트웨이 인증을 거쳐 그대로 중계 |
| 지표 | Prometheus 지표 노출 |

일부 기능은 Enterprise 플랜 전용이므로 문서의 표시를 확인합니다.

