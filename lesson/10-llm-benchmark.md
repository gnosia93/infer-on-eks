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


