## LiteLLM 기반 가드 레일 아키텍처 ##

![](https://github.com/gnosia93/infer-on-eks/blob/main/images/vllm-guardrail.jpg)


1. 1단계 (초기 구축): LiteLLM에 LLM Guard를 연동해 주민번호·전화번호 같은 개인정보(PII) 유출 방지와 기본적인 프롬프트 인젝션 차단을 먼저 적용합니다.

2. 2단계 (고도화): GPU 자원에 여유가 있다면 Llama Guard 3-8B (또는 1B)를 vLLM으로 하나 더 띄운 뒤, LiteLLM의 pre_call / post_call 훅으로 연결해 문맥상 위험한 질의응답을 차단합니다.

3. 비동기 처리 팁: 출력(Output) 가드레일은 스트리밍(Streaming) 응답 시 청크(Chunk) 단위로 모아서 검사하거나, 지연 시간을 줄이기 위해 입력(Input) 가드레일만 동기(Sync)로 먼저 걸고 출력은 비동기 로깅 후 사후 차단하는 방식도 많이 쓰입니다.



### LiteLLM 설정 ###
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
