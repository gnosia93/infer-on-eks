# LiteLLM으로 점진적 모델 마이그레이션 구성하기

> **요구사항**
> 점진적이고 원활한 마이그레이션을 위해 LLM Gateway(예: LiteLLM)는 가중치 기반 분배와 세션 고정(Session Affinity)을 조합해 A/B 테스트를 구성할 수 있어야 하고, 트래픽 미러링으로 후보 모델을 사용자에게 노출하지 않는 섀도 테스트도 할 수 있어야 한다. 또한 가중치는 게이트웨이를 재시작하지 않고 바꿔 적용할 수 있어야 한다.

이 문서는 위 요구사항을 LiteLLM 기능으로 구성하는 방법을 설명합니다. 예시 상황은 쿠버네티스에서 vLLM으로 서빙하는 기존 모델(`agent-v1`)을 후보 모델(`agent-v2`)로 바꾸는 경우입니다.

## 1. 한눈에 보기

| 요구사항 | LiteLLM 기능 | 설정하는 곳 |
|---|---|---|
| 가중치 기반 분배 | Weighted Deployments | 배포의 `litellm_params.weight` |
| 세션 고정 | Session Affinity | `router_settings`, 요청 헤더 `x-litellm-session-id` |
| A/B 테스트 | 가중치와 세션 고정의 조합 | 응답 헤더 `x-litellm-model-id`로 결과 집계 |
| 섀도 테스트 | Traffic Mirroring | 배포의 `litellm_params.silent_model` |
| 재시작 없는 가중치 변경 | DB 기반 모델 관리 | `STORE_MODEL_IN_DB=True`, `PATCH /model/{model_id}/update` |

## 2. 먼저 알아둘 개념: 모델 그룹과 배포

- **모델 그룹**: 클라이언트가 요청에 넣는 모델 이름입니다. 예를 들면 `insurance-agent`입니다.
- **배포(deployment)**: 같은 모델 이름 아래 등록한 실제 연결 대상 하나하나입니다. 배포마다 vLLM 주소와 실제 모델이 다를 수 있습니다.
- 요청이 오면 LiteLLM은 그룹 안에서 배포 하나를 골라 보냅니다. 클라이언트는 어느 배포로 갔는지 몰라도 됩니다.

```text
앱 ── model="insurance-agent" ──▶ LiteLLM
                                    ├─ 배포 A (기존): vLLM agent-v1   weight 9 → 90%
                                    └─ 배포 B (후보): vLLM agent-v2   weight 1 → 10%
```

그래서 모델을 바꿀 때 앱 코드는 그대로 두고 LiteLLM에서 배포와 가중치만 조정하면 됩니다.

## 3. 사전 준비

### 3.1 버전

LiteLLM v1.109.0 이상을 권장합니다. 스트리밍 요청 미러링은 v1.103.0부터 지원되고, 미러링 호출을 로그에서 구분하는 표시(`is_silent_experiment`)는 v1.109.0부터 지원됩니다.

### 3.2 환경 변수

환경 변수는 쿠버네티스 Secret으로 주입합니다. 값을 config.yaml이나 이미지에 직접 넣지 마세요.

```bash
DATABASE_URL=postgresql://litellm:<비밀번호>@postgres.llm.svc.cluster.local:5432/litellm
LITELLM_MASTER_KEY=sk-<관리자 키>
LITELLM_SALT_KEY=<DB에 저장하는 자격 증명의 암호화 키. 한 번 정하면 바꾸지 않음>
STORE_MODEL_IN_DB=True        # 모델 설정을 DB에 저장해야 재시작 없이 바꿀 수 있음
REDIS_HOST=redis.llm.svc.cluster.local
REDIS_PASSWORD=<비밀번호>
```

### 3.3 config.yaml

```yaml
general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY

router_settings:
  routing_strategy: simple-shuffle                 # weight가 적용되는 기본 전략
  optional_pre_call_checks: ["session_affinity"]   # 세션 고정 켜기
  deployment_affinity_ttl_seconds: 604800          # 7일 동안 요청이 없으면 고정 해제 (기본값 3600)
  redis_host: os.environ/REDIS_HOST                # 레플리카끼리 고정 정보를 공유
  redis_port: 6379
  redis_password: os.environ/REDIS_PASSWORD

# model_list에는 insurance-agent를 넣지 않습니다. (아래 주의 참고)
```

> **주의: 마이그레이션할 모델은 YAML에 넣지 않습니다.**
> config.yaml의 `model_list`에 있는 모델은 파일에서만 관리되므로, API나 UI로 바꾸거나 지울 수 없습니다. 같은 이름으로 DB에 모델을 등록해도 기존 항목을 덮어쓰지 않고 배포가 하나 더 생길 뿐입니다. 가중치를 재시작 없이 바꾸려면 그 모델 그룹의 배포를 모두 API로 등록해야 합니다.

## 4. 모델 등록

관리 작업은 관리자 키로 API를 호출해서 합니다. 앱에는 관리자 키 대신 `insurance-agent`만 호출할 수 있는 별도 가상 키를 줍니다.

```bash
export LITELLM_URL="http://litellm.llm.svc.cluster.local:4000"
export LITELLM_ADMIN_KEY="<관리자 키>"

# 앱 전용 가상 키 발급 (insurance-agent만 호출 가능)
curl -sS -X POST "$LITELLM_URL/key/generate" \
  -H "Authorization: Bearer $LITELLM_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"key_alias": "rag-app", "models": ["insurance-agent"]}' | jq -r '.key'
```

기존 모델을 `insurance-agent` 그룹의 배포로 등록합니다.

```bash
CURRENT_ID=$(curl -sS -X POST "$LITELLM_URL/model/new" \
  -H "Authorization: Bearer $LITELLM_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model_name": "insurance-agent",
    "litellm_params": {
      "model": "hosted_vllm/agent-v1",
      "api_base": "http://vllm-agent-v1.llm.svc.cluster.local:8000/v1",
      "weight": 1
    },
    "model_info": {"variant": "current"}
  }' | jq -r '.model_id')

echo "$CURRENT_ID"   # 가중치 변경과 삭제에 쓰므로 기록해 둡니다
```

- `model_name`은 클라이언트가 부르는 이름입니다.
- `hosted_vllm/` 뒤의 이름은 vLLM의 `--served-model-name` 값과 같아야 합니다.
- `model_info.variant`는 직접 붙이는 표시입니다. 결과를 집계할 때 배포 ID가 기존 모델인지 후보 모델인지 구분하는 데 씁니다.
- vLLM을 `--api-key` 옵션으로 띄웠다면 `"api_key": "os.environ/VLLM_API_KEY"`를 추가합니다.

## 5. 가중치 기반 분배

같은 그룹의 배포마다 `weight`를 주면 그 비율대로 요청이 나뉩니다. 비율은 전체 가중치 합에 대한 비율로 계산됩니다.

| 기존 weight | 후보 weight | 실제 비율 (기존 : 후보) |
|---|---|---|
| 19 | 1 | 95 : 5 |
| 9 | 1 | 90 : 10 |
| 1 | 1 | 50 : 50 |

후보 모델을 등록하기 전에 기존 배포의 가중치를 먼저 올려 두세요. 그러면 후보를 등록하는 순간에도 잠깐 50:50이 되는 일이 없습니다.

```bash
# 1) 기존 배포의 가중치를 먼저 19로 올림
curl -sS -X PATCH "$LITELLM_URL/model/$CURRENT_ID/update" \
  -H "Authorization: Bearer $LITELLM_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"litellm_params": {"weight": 19}}'

# 2) 후보 배포를 같은 그룹에 weight 1로 등록해서 95:5로 만듦
CANDIDATE_ID=$(curl -sS -X POST "$LITELLM_URL/model/new" \
  -H "Authorization: Bearer $LITELLM_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model_name": "insurance-agent",
    "litellm_params": {
      "model": "hosted_vllm/agent-v2",
      "api_base": "http://vllm-agent-v2.llm.svc.cluster.local:8000/v1",
      "weight": 1
    },
    "model_info": {"variant": "candidate"}
  }' | jq -r '.model_id')
```

## 6. 세션 고정 (Session Affinity)

가중치만 쓰면 요청마다 배포를 새로 고릅니다. 그래서 같은 사용자라도 질문할 때마다 기존 모델과 후보 모델을 오갈 수 있습니다. 세션 고정을 켜면 같은 세션 ID로 들어온 요청은 첫 요청이 배정된 배포로 계속 갑니다.

### 동작 방식

| 상황 | 동작 |
|---|---|
| 새 세션 ID의 첫 요청 | 가중치에 따라 배포를 고르고 그 배포에 고정합니다. |
| 같은 세션 ID의 이후 요청 | 가중치와 상관없이 고정된 배포로 보냅니다. |
| TTL 동안 요청이 없음 | 고정이 풀립니다. 다음 요청은 다시 가중치에 따라 배정됩니다. |
| 고정된 배포가 삭제됨 | 남은 배포로 보냅니다. |
| 고정된 배포가 쿨다운 상태(오류가 반복돼 잠시 제외된 상태)임 | 그동안 다른 배포로 보냈다가, 복구되면 원래 배포로 돌려보냅니다. |

### 앱에서 세션 ID 보내기

요청 헤더 `x-litellm-session-id`에 세션 ID를 넣습니다. A/B 테스트를 사용자 단위로 하려면 세션 ID를 사용자 ID에서 만듭니다. 세션 ID는 로그에 남으므로 고객 식별자 원문 대신 비밀 키를 섞은 해시값을 쓰세요.

```python
import hashlib
import hmac
import os

from openai import OpenAI

client = OpenAI(
    base_url="http://litellm.llm.svc.cluster.local:4000",
    api_key=os.environ["LITELLM_APP_KEY"],   # 4장에서 발급한 앱 전용 가상 키
)

def session_id_for(user_id: str) -> str:
    key = os.environ["SESSION_ID_KEY"].encode()
    return hmac.new(key, user_id.encode(), hashlib.sha256).hexdigest()

raw = client.chat.completions.with_raw_response.create(
    model="insurance-agent",
    messages=[{"role": "user", "content": "실손보험 청구 서류가 뭐예요?"}],
    extra_headers={"x-litellm-session-id": session_id_for("customer-12345")},
)
served_by = raw.headers.get("x-litellm-model-id")   # 응답한 배포의 ID
completion = raw.parse()
```

## 7. A/B 테스트 (가중치 + 세션 고정)

5장의 가중치로 사용자를 나누고, 6장의 세션 고정으로 각 사용자를 한 모델에 묶으면 A/B 테스트가 됩니다. 사용자는 실험 기간 동안 한 모델만 경험합니다.

LiteLLM은 어느 모델이 더 나은지 판정해 주지 않습니다. 결과는 다음 순서로 직접 모아서 비교합니다.

1. 앱 로그에 `x-litellm-model-id`(응답한 배포의 ID)를 함께 남깁니다.
2. 각 배포 ID가 기존 모델인지 후보 모델인지는 `GET /model/info` 결과의 `model_info.variant`로 확인합니다.
3. 배포별로 다음 지표를 비교합니다.
   - TTFT, 오류율
   - 사용자 피드백(좋아요/싫어요)
   - 답변 정확도(샘플을 뽑아 담당자나 LLM 평가로 검수)

```bash
# 배포 ID와 variant의 매핑 확인
curl -sS "$LITELLM_URL/model/info" -H "Authorization: Bearer $LITELLM_ADMIN_KEY" \
  | jq '.data[] | {name: .model_name, id: .model_info.id, variant: .model_info.variant}'
```

> 응답 구조는 버전에 따라 다를 수 있습니다. jq 필터가 결과를 내지 않으면 먼저 `jq .`로 원본 응답을 확인하세요.

## 8. 섀도 테스트 (트래픽 미러링)

섀도 테스트에서는 사용자에게 기존 모델의 응답만 돌려줍니다. 같은 요청을 뒤에서 후보 모델에도 보내지만, 후보 모델의 응답은 사용자에게 가지 않고 로그에만 남습니다. 후보 모델을 사용자에게 노출하기 전에 실제 질문으로 검증할 때 씁니다.

```bash
# 1) 후보 모델을 섀도 전용 이름으로 등록 (사용자 요청은 이 이름으로 오지 않음)
SHADOW_ID=$(curl -sS -X POST "$LITELLM_URL/model/new" \
  -H "Authorization: Bearer $LITELLM_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model_name": "insurance-agent-shadow",
    "litellm_params": {
      "model": "hosted_vllm/agent-v2",
      "api_base": "http://vllm-agent-v2.llm.svc.cluster.local:8000/v1"
    }
  }' | jq -r '.model_id')

# 2) 기존 배포에 미러링 대상 지정
curl -sS -X PATCH "$LITELLM_URL/model/$CURRENT_ID/update" \
  -H "Authorization: Bearer $LITELLM_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"litellm_params": {"silent_model": "insurance-agent-shadow"}}'
```

미러링된 호출은 로그에 `is_silent_experiment: true`로 표시됩니다. LiteLLM DB에서는 다음과 같이 찾습니다.

```sql
-- 섀도(복제) 호출
SELECT request_id, model, spend
FROM "LiteLLM_SpendLogs"
WHERE metadata->>'is_silent_experiment' = 'true';

-- 실제 사용자 호출
SELECT request_id, model, spend
FROM "LiteLLM_SpendLogs"
WHERE NOT metadata ? 'is_silent_experiment';
```

> **주의**
> - 기존 배포로 가는 요청이 모두 복제됩니다. 그래서 후보 모델의 vLLM 풀도 운영 트래픽 전체를 처리할 GPU가 필요합니다.
> - 섀도 호출이 실패해도 사용자 응답에는 영향이 없고, 프록시 로그에 `Silent experiment failed` 메시지가 남습니다. 섀도 데이터가 쌓이지 않으면 이 메시지부터 확인하세요.
> - 섀도 테스트를 끝낼 때는 기존 배포에서 `silent_model`을 지웁니다(`{"litellm_params": {"silent_model": null}}`). 그다음 `GET /model/info`로 실제로 지워졌는지 확인하세요. null 처리 방식은 버전마다 다를 수 있습니다.

## 9. 재시작 없이 가중치 바꾸기

DB에 저장된 배포는 `PATCH /model/{model_id}/update`로 바꿉니다. 프록시를 재시작하지 않아도 새 요청부터 바뀐 값이 적용됩니다. 레플리카가 여러 대면 각 레플리카가 DB에서 모델 목록을 다시 읽을 때까지 잠깐 차이가 날 수 있습니다.

```bash
# 기존 배포 weight를 1로 바꿔 50:50으로 변경
curl -sS -X PATCH "$LITELLM_URL/model/$CURRENT_ID/update" \
  -H "Authorization: Bearer $LITELLM_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"litellm_params": {"weight": 1}}'
```

배포를 지울 때는 `POST /model/delete`를 씁니다.

```bash
curl -sS -X POST "$LITELLM_URL/model/delete" \
  -H "Authorization: Bearer $LITELLM_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"id\": \"$CANDIDATE_ID\"}"
```

> **가중치를 바꿔도 이미 고정된 세션은 옮겨가지 않습니다.**
> 바뀐 가중치는 새 세션에만 적용됩니다. 문제가 생겨 후보 모델을 바로 빼야 한다면 가중치를 낮추지 말고 후보 배포를 삭제하세요. 그래야 후보 모델에 고정된 세션도 즉시 기존 모델로 돌아갑니다.

## 10. 마이그레이션 순서 예시

| 단계 | 하는 일 | 기존 : 후보 | 다음 단계로 가기 전에 확인할 것 |
|---|---|---|---|
| 1. 섀도 | 8장 설정 | 100 : 0 (모든 요청 복제) | 후보 모델의 오류율, TTFT, 답변 샘플 검수 |
| 2. 카나리 | `silent_model` 제거, 섀도 전용 모델(`$SHADOW_ID`) 삭제, 5장 설정 | 95 : 5 | 후보 모델 사용자의 오류율과 피드백 |
| 3. A/B | 가중치를 1 : 1로 변경 | 50 : 50 | 7장 지표 비교 |
| 4. 전환 | 기존 배포 삭제 | 0 : 100 | 기존 vLLM 풀 정리 |
| 롤백 | 후보 배포 삭제 | 100 : 0 | 원인 분석 |

## 11. 운영할 때 주의할 점

- **실제 비율은 설정한 비율보다 늦게 따라옵니다.** 이미 고정된 세션은 TTL이 끝날 때까지 원래 배포에 남기 때문입니다. TTL을 길게 잡을수록 사용자 경험은 일관되지만, 실제 비율이 설정 비율에 가까워지는 데 시간이 더 걸립니다.
- **레플리카가 여러 대면 Redis가 필요합니다.** Redis가 없으면 고정 정보가 레플리카마다 따로 저장됩니다. 그러면 같은 사용자가 어느 레플리카를 거치느냐에 따라 다른 모델로 갈 수 있습니다.
- **결과는 실제로 응답한 배포를 기준으로 집계합니다.** 쿨다운 중에는 고정된 세션도 잠시 다른 배포로 가기 때문입니다.
- **관리자 키와 앱 키를 분리합니다.** 가중치를 바꾸는 관리 API는 관리자 키로만 호출하고, 앱에는 추론용 가상 키만 줍니다.
- **공급망 보안을 챙깁니다.** LiteLLM은 2026년에 악성 릴리스가 두 번 배포됐습니다(1.82.7, 1.82.8, 1.107.0). 다음 조치를 하세요.
  - 이미지를 다이제스트로 고정하고 내부 레지스트리에 미러링합니다.
  - 서비스 어카운트 토큰 자동 마운트를 끕니다.
  - 불필요한 외부 송신(egress)을 막습니다.

## 참고 문서

- [Routing: Weighted Deployments, Session Affinity](https://docs.litellm.ai/docs/routing)
- [A/B Testing - Traffic Mirroring](https://docs.litellm.ai/docs/traffic_mirroring)
- [Management API](https://docs.litellm.ai/docs/proxy/configuration/api)
- [Model Management](https://github.com/BerriAI/litellm-docs/blob/main/docs/proxy/model_management.md)
- [vLLM provider](https://docs.litellm.ai/docs/providers/vllm)
