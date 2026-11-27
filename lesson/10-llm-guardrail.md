## LiteLLM 기반 가드 레일 아키텍처 ##

![](https://github.com/gnosia93/infer-on-eks/blob/main/images/vllm-guardrail.jpg)

```
model_list:
  # 1. 메인 추론 모델 (vLLM 서빙)
  - model_name: main-llm
    litellm_params:
      model: hosted_vllm/Qwen/Qwen2.5-72B-Instruct
      api_base: http://vllm-main:8000/v1
      api_key: "EMPTY"

  # 2. 가드레일 전용 경량 모델 (vLLM 서빙)
  - model_name: llama-guard
    litellm_params:
      model: hosted_vllm/meta-llama/Llama-Guard-3-8B
      api_base: http://vllm-guard:8001/v1
      api_key: "EMPTY"

# 가드레일 파이프라인 정의
guardrails:
  - guardrail_name: "in-house-llama-guard"
    litellm_params:
      guardrail: litellm_proxy/llama_guard  # 자체 호스팅 가드 모델 연동
      mode: ["pre_call", "post_call"]     # 입력(pre)과 출력(post) 모두 검사
      model_name: "llama-guard"           # 위 model_list에 등록한 가드레일 모델명
      default_on: true                    # 모든 요청에 기본 적용

litellm_settings:
  # 가드레일 차단 시 반환할 커스텀 메시지 설정 가능
  drop_params: true
  set_verbose: false
```
