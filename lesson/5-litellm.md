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
