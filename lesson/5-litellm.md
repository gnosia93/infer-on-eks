## LiteLLM 배포 (Deployment, Service) ##

LiteLLM 파드 2개를 vLLM과 같은 llm-serving 네임스페이스에 띄우고 ClusterIP Service로 묶는다. ALB IP 모드에서는 ALB가 Service 뒤의 파드 IP를 타깃으로 직접 등록하므로 Service는 ClusterIP면 된다.

```
클라이언트 (session_id 헤더)
  → ALB (IP 모드, 다음 단계에서 Ingress로 연결)
  → LiteLLM 파드 2개 (session_id를 읽어 x-session-id 헤더로 넘김)
  → vLLM Service (다음 단계에서 Envoy/Istio가 x-session-id로 파드를 고름)
```

### session_id 처리 방식 ###
LiteLLM은 기본으로 클라이언트 헤더를 백엔드에 넘기지 않는다. forward_client_headers_to_llm_api를 켜도 x-로 시작하는 헤더만 넘긴다. 그래서 session_id는 그대로는 vLLM에 가지 않는다. 대신 LiteLLM의 pre-call 훅(파이썬 파일 하나)을 ConfigMap으로 넣는다.

* 읽는 헤더: 훅은 요청 헤더에서 session_id를 읽는다. x-session-id도 받으며, 둘 다 있으면 session_id가 우선이다.
* 값 검사: 영문, 숫자, . _ : -로 된 1~128자만 받는다. 형식이 틀리면 400으로 거부한다. 헤더가 없으면 그대로 통과시킨다.
* 넘기는 헤더: vLLM으로 가는 요청에 x-session-id 헤더로 붙인다. 백엔드 쪽 이름에 밑줄을 쓰지 않는 것은 nginx처럼 밑줄 헤더를 기본으로 버리는 프록시가 있기 때문이다. 나중에 Envoy/Istio도 이 헤더로 해시하면 된다.

#### 클라이언트 쪽도 가능하면 x-session-id를 쓰는 편이 안전하다. ####

* ALB는 헤더 이름에 영문, 숫자, 하이픈만 허용하는 것으로 본다. routing.http.drop_invalid_header_fields.enabled를 켜면 session_id 같은 밑줄 헤더를 지운다.
* 기본값(false)에서는 전달되지만, Security Hub 점검(ELB.4)이 이 값을 켜라고 권고한다.
* 훅이 두 이름을 모두 받으므로 클라이언트가 헤더를 바꿔도 LiteLLM 설정은 그대로 둔다.
* LiteLLM도 8자 이상의 x-session-id는 자체 로그의 세션 ID로 인식한다.


## 설정하기 ##

### 1. 마스터 키 ###
 
마스터 키가 없으면 LiteLLM은 인증 없이 모든 요청을 받으므로 ALB로 열기 전에 반드시 켠다. 키는 sk-로 시작해야 한다.

```
kubectl create secret generic litellm-secrets -n llm-serving \
  --from-literal=LITELLM_MASTER_KEY="sk-$(openssl rand -hex 24)"
```
클라이언트는 Authorization: Bearer <키> 헤더로 이 키를 보낸다. 마스터 키는 관리자 키다. 앱마다 다른 키(virtual key)를 나눠 주려면 Postgres를 붙여야 한다.


### 2. 설정 파일 (ConfigMap) ###

```
kubectl apply -f - <<'EOF'
apiVersion: v1
kind: ConfigMap
metadata:
  name: litellm-config
  namespace: llm-serving
data:
  config.yaml: |
    model_list:
      - model_name: gemma-4-12b                     # 클라이언트가 요청의 model에 쓰는 이름
        litellm_params:
          model: hosted_vllm/gemma-4-12b            # hosted_vllm/ 뒤는 vLLM의 --served-model-name
          api_base: http://gemma4-12b-vllm.llm-serving.svc.cluster.local:8000/v1
          timeout: 600                              # 요청 하나의 최대 시간(초)

    litellm_settings:
      callbacks: session_hook.session_id_forwarder  # 같은 디렉터리 session_hook.py의 session_id_forwarder

    general_settings:
      master_key: os.environ/LITELLM_MASTER_KEY

  session_hook.py: |
    import re

    from fastapi import HTTPException
    from litellm.integrations.custom_logger import CustomLogger

    # 클라이언트가 보내는 헤더. 둘 다 오면 앞의 것을 쓴다
    INCOMING_HEADERS = ("session_id", "x-session-id")
    # vLLM(나중에는 Envoy/Istio 라우터)으로 넘길 헤더 이름
    OUTGOING_HEADER = "x-session-id"
    # 영문, 숫자, . _ : - 로 된 1~128자
    VALID_SESSION_ID = re.compile(r"[A-Za-z0-9._:-]{1,128}")

    class SessionIdForwarder(CustomLogger):
        async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
            # LiteLLM이 받은 요청 헤더 (이름은 소문자)
            headers = (data.get("proxy_server_request") or {}).get("headers") or {}
            session_id = next((headers[h] for h in INCOMING_HEADERS if headers.get(h)), None)
            if session_id is None:
                return data

            if not VALID_SESSION_ID.fullmatch(session_id):
                raise HTTPException(status_code=400, detail="invalid session_id header")

            # vLLM으로 보내는 HTTP 요청에 붙는 헤더
            extra_headers = dict(data.get("extra_headers") or {})
            extra_headers[OUTGOING_HEADER] = session_id
            data["extra_headers"] = extra_headers
            return data

    session_id_forwarder = SessionIdForwarder()
EOF
```
