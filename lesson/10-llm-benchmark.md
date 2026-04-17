## 추론 성능 비교 (versus vLLM) ##

포트 포워딩 설정한 후, tritonserver 도커 이미지를 설치한다.
```
kubectl port-forward svc/trtllm-qwen-svc 8000:80 & 
curl http://localhost:8000/health

docker run -it --rm --net=host \
  nvcr.io/nvidia/tritonserver:26.02-py3-sdk \
  bash
```
[결과]
```
...
8b091788f25a: Pull complete 
1185ca7269e2: Pull complete 
Digest: sha256:43b50a162ed5c8be4c0c6ba948869d9b4a2ce12bec73710c12f0dd0e55ec0fde
Status: Downloaded newer image for nvcr.io/nvidia/tritonserver:26.02-py3-sdk
=================================
== Triton Inference Server SDK ==
=================================

NVIDIA Release 26.02 (build 267903555)

Copyright (c) 2018-2025, NVIDIA CORPORATION & AFFILIATES.  All rights reserved.

Various files include modifications (c) NVIDIA CORPORATION & AFFILIATES.  All rights reserved.

GOVERNING TERMS: The software and materials are governed by the NVIDIA Software License Agreement
(found at https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-software-license-agreement/)
and the Product-Specific Terms for NVIDIA AI Products
(found at https://www.nvidia.com/en-us/agreements/enterprise-software/product-specific-terms-for-ai-products/).

WARNING: The NVIDIA Driver was not detected.  GPU functionality will not be available.
   Use the NVIDIA Container Toolkit to start this container with GPU support; see
   https://docs.nvidia.com/datacenter/cloud-native/ .
```

테스트를 실행한다.
```
genai-perf profile \
  --model Qwen/Qwen2.5-72B-Instruct \
  --endpoint-type chat \
  --url http://localhost:8000 \
  --num-prompts 100 \
  --concurrency 10 \
  --tokenizer Qwen/Qwen2.5-72B-Instruct
```
[결과]
```
[2026-04-17 09:57:37] INFO     Parsing total 20 requests.                                                                     llm_profile_data_parser.py:124
Progress: 100%|██████████████████████████████████████████████████████████████████████████████████████████████████████| 20/20 [00:00<00:00, 443.30requests/s]
                                        NVIDIA GenAI-Perf | LLM Metrics                                         
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━┓
┃                            Statistic ┃       avg ┃       min ┃       max ┃       p99 ┃       p90 ┃       p75 ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━┩
│                 Request Latency (ms) │ 37,719.87 │ 11,690.65 │ 58,601.16 │ 58,194.75 │ 50,017.27 │ 45,109.17 │
│      Output Sequence Length (tokens) │    460.20 │     97.00 │    718.00 │    715.53 │    683.40 │    588.00 │
│       Input Sequence Length (tokens) │    550.00 │    550.00 │    550.00 │    550.00 │    550.00 │    550.00 │
│ Output Token Throughput (tokens/sec) │     91.19 │       N/A │       N/A │       N/A │       N/A │       N/A │
│         Request Throughput (per sec) │      0.20 │       N/A │       N/A │       N/A │       N/A │       N/A │
│                Request Count (count) │     20.00 │       N/A │       N/A │       N/A │       N/A │       N/A │
└──────────────────────────────────────┴───────────┴───────────┴───────────┴───────────┴───────────┴───────────┘
[2026-04-17 09:57:38] INFO     Generating artifacts/Qwen_Qwen2.5-72B-Instruct-openai-chat-concurrency10/profile_export_genai_perf.json   json_exporter.py:64
[2026-04-17 09:57:38] INFO     Generating artifacts/Qwen_Qwen2.5-72B-Instruct-openai-chat-concurrency10/profile_export_genai_perf.csv     csv_exporter.py:75
```

## 테스트 하기 ##
concurrency 와 num-prompts 값을 동시에 증가시키면서 테스트 한다.
```
concurrency 1 → num-prompts 10
concurrency 10 → num-prompts 30
concurrency 50 → num-prompts 100
concurrency 100 → num-prompts 200
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


