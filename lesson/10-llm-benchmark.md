## 추론 성능 비교 (versus vLLM) ##

테스트 한다.
```
kubectl port-forward svc/trtllm-qwen-svc 8000:80 & 

genai-perf profile \
  --model Qwen/Qwen2.5-72B-Instruct \
  --endpoint-type chat \
  --url http://localhost:8000 \
  --num-prompts 100 \
  --concurrency 10 \
  --tokenizer Qwen/Qwen2.5-72B-Instruct
```
실행을 완료하면 port-foward 프로세스를 죽인다.
```
kill %1
```

#### 측정 항목: ####
* TTFT (Time To First Token): 첫 토큰까지 걸리는 시간
* ITL (Inter-Token Latency): 토큰 간 지연
* Throughput: 초당 생성 토큰 수
* Request Latency: 요청당 전체 응답 시간

### 측정 결과 ###
* vLLM
  
* TensorRT-LLM


