## vLLM NetworkPolicy ##

vLLM 파드의 8000 포트로 들어오는 트래픽을 아래 출발지에서만 받도록 막는다. 대상은 vLLM 파드뿐이고 나가는 트래픽(S3, STS)은 막지 않는다. LiteLLM 파드에는 정책을 걸지 않으므로 ALB → LiteLLM 경로도 그대로다.


| 허용하는 출발지 | 용도 |
| :--- | :--- |
| LiteLLM 파드 (`llm-serving`, `app.kubernetes.io/name=litellm`) | 추론 요청 |
| Prometheus 파드 (`monitoring`, `app.kubernetes.io/name=prometheus`) | `/metrics` 수집 (KEDA가 쓰는 지표) |
| `vllm-client=true` 레이블을 붙인 파드 (`llm-serving`) | 벤치마크, 부하 테스트 |


