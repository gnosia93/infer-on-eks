## TensorRT-LLM ##
TensorRT-LLM은 NVIDIA의 범용 딥러닝 추론 엔진인 TensorRT를 LLM에 특화시킨 인퍼런스 프레임워크로, 기존 TensorRT의 커널 퓨전, 메모리 레이아웃 최적화, 패딩 최적화에 더해, LLM 서빙에 필수적인 KV Cache 관리(Paged Attention), Inflight Batching(동적 배칭), Tensor/Pipeline Parallel(멀티 GPU/노드 분산), FP8/INT4 양자화, Speculative Decoding 등을 추가한 것이다. PyTorch 모델을 TensorRT 엔진으로 컴파일해서 GPU 아키텍처별 최적 CUDA 커널을 생성하기 때문에, vLLM 대비 10~30% 높은 성능을 낼 수 있지만 빌드 과정이 복잡하고 NVIDIA GPU에서만 동작한다.

### 연산 최적화 기술 ###
TensorRT은 커널 퓨전, 메모리 레이아웃 최적화, 패딩 최적화를 통해서 레지스터, L2 캐시에 비해 느린 ___HBM 메모리 접근 횟수를 줄여___ GPU 의 연산을 최적화 한다. 참고로 GPU 는 128 bytes 단위로 메모리 어드레싱 작업을 수행한다. 

![](https://github.com/gnosia93/eks-agentic-ai/blob/main/lesson/images/tensorrt-optimization.png)


### Triton Server vs TensorRT-LLM ###
Triton Server는 서빙 인프라로 HTTP/gRPC 엔드포인트를 제공하고, 요청 큐잉과 배칭을 처리하며, 여러 모델을 하나의 서버에서 동시에 서빙할 수 있다. 모델 버전 관리(v1 → v2 전환), 헬스체크, Prometheus 메트릭 수집, 모델 로드/언로드 기능을 제공한다.

TensorRT-LLM은 추론 엔진으로 모델을 TensorRT 엔진으로 컴파일(빌드)하고, GPU에서 최적화된 커널로 추론을 실행한다. KV Cache 관리, Tensor Parallel 처리, 그리고 vLLM의 Continuous Batching과 유사한 In-flight Batching을 지원한다.

## Qwnen 72B 모델 TensorRT-LLM 로 최적화 하기 ##

> [!IMPORTANT]
> 본 튜토리얼에서는 GPU 수급 불균형으로 인해 NVLink 지원 인스턴스(p4d, p5) 확보가 어려워 g6e.12xlarge(L40S × 4, PCIe)를 사용하였다. TensorRT 엔진은 빌드 시 해당 GPU에서 커널 프로파일링을 수행하여 최적 커널을 선택하므로, 서빙할 GPU와 동일한 GPU에서 빌드해야 한다. 실제 운영 환경에서는 NVLink가 지원되는 p4d.24xlarge(A100 × 8) 또는 p5.48xlarge(H100 × 8)에서 빌드 및 서빙을 권장한다. NVLink는 PCIe 대비 약 7~14배 높은 GPU 간 대역폭을 제공하여, 멀티 GPU 추론 시 통신 병목을 크게 줄여준다.

S3 버킷을 생성하고 테라폼에서 생성한 eks-agentic-ai-s3-access 을 쿠버네티스의 서비스 어카운트에 할당한다
```bash
export CLUSTER_NAME=eks-agentic-ai
export ENGINE_BUCKET=${CLUSTER_NAME}-tensorrt-llm-$(date +%Y%m%d%H%M)
export ACCOUNT_ID=$(aws sts get-caller-identity --query "Account" --output text)

aws s3 mb s3://${ENGINE_BUCKET} --region ap-northeast-2

kubectl create serviceaccount s3-access-sa -n default
kubectl annotate serviceaccount s3-access-sa -n default \
  eks.amazonaws.com/role-arn=arn:aws:iam::${ACCOUNT_ID}:role/eks-agentic-ai-s3-access
```

### 모델 최적화 하기 ###

TensorRT-LLM을 이용하여 HuggingFace 모델을 NVIDIA GPU에 맞게 최적화한다.  
* 체크포인트 변환: HuggingFace 가중치를 TensorRT-LLM 포맷으로 변환하고, TP(텐서 병렬) 분할 수행
* 엔진 빌드: 모델 그래프를 GPU에서 실행 가능한 TensorRT 엔진으로 컴파일하며, 레이어 퓨전·커널 선택·메모리 레이아웃 최적화 적용

>[!NOTE]
> 레이어 퓨전 이란 ?  
> 레이어 퓨전은 여러 개의 연산을 하나로 합치는 것이다. 예를들어 MatMul → Add → ReLU 이 세 단계를 따로 실행하면 GPU 메모리를 세 번 읽고 쓰게되는데 이를 하나의 커널로 합치면 메모리 접근이 줄어서 빨라진다.  
>
> 커널 선택 이란 ?  
> GPU에서 같은 연산(예: 행렬 곱셈)을 수행하는 CUDA 커널이 여러 개 있는데 입력 크기, 데이터 타입, GPU 아키텍처에 따라 성능이 모두 다르다.
> TensorRT가 엔진 빌드할 때 각 레이어마다 여러 커널을 실제로 돌려보고(프로파일링), 가장 빠른 걸 골라서 엔진에 넣는다. 그래서 빌드 시간이 오래 걸리는 것이다.
> 쉽게 말하면 "이 GPU에서 이 연산을 가장 빠르게 실행하는 방법을 자동으로 찾아주는 것" 이다.
>

[trtllm-engine-build.yaml](https://github.com/gnosia93/eks-agentic-ai/blob/main/code/yaml/trtllm-engine-build.yaml) 으로 Qwen 모델을 최적화 한다.

ENGINE_BUCKET 환경변수가 설정되어 있는지 확인한다.
```bash
mkdir triton && cd triton
export | grep ENGINE_BUCKET
```
모델 최적화 JOB 을 실행한다. 대략 1시간 정도의 시간이 소요된다.
```bash
curl -o trtllm-engine-build.yaml \
  https://raw.githubusercontent.com/gnosia93/eks-agentic-ai/refs/heads/main/code/yaml/trtllm-engine-build.yaml

envsubst < trtllm-engine-build.yaml | kubectl apply -f -

kubectl logs job/trtllm-engine-build -f
```
[결과]
```
Requirement already satisfied: huggingface_hub<1.0 in /usr/local/lib/python3.12/dist-packages (0.36.2)
Collecting awscli
  Downloading awscli-1.44.80-py3-none-any.whl.metadata (11 kB)
Requirement already satisfied: filelock in /usr/local/lib/python3.12/dist-packages (from huggingface_hub<1.0) (3.21.2)
Requirement already satisfied: fsspec>=2023.5.0 in /usr/local/lib/python3.12/dist-packages (from huggingface_hub<1.0) (2024.9.0)
Requirement already satisfied: hf-xet<2.0.0,>=1.1.3 in /usr/local/lib/python3.12/dist-packages (from huggingface_hub<1.0) (1.2.0)
Requirement already satisfied: packaging>=20.9 in /usr/local/lib/python3.12/dist-packages (from huggingface_hub<1.0) (25.0)
Requirement already satisfied: pyyaml>=5.1 in /usr/local/lib/python3.12/dist-packages (from huggingface_hub<1.0) (6.0.3)
Requirement already satisfied: requests in /usr/local/lib/python3.12/dist-packages (from huggingface_hub<1.0) (2.32.5)
Requirement already satisfied: tqdm>=4.42.1 in /usr/local/lib/python3.12/dist-packages (from huggingface_hub<1.0) (4.67.3)
Requirement already satisfied: typing-extensions>=3.7.4.3 in /usr/local/lib/python3.12/dist-packages (from huggingface_hub<1.0) (4.15.0)
Collecting botocore==1.42.90 (from awscli)
  Downloading botocore-1.42.90-py3-none-any.whl.metadata (5.9 kB)
Collecting docutils<=0.19,>=0.18.1 (from awscli)
  Downloading docutils-0.19-py3-none-any.whl.metadata (2.7 kB)
Collecting s3transfer<0.17.0,>=0.16.0 (from awscli)
  Downloading s3transfer-0.16.0-py3-none-any.whl.metadata (1.7 kB)
Collecting colorama<0.4.7,>=0.2.5 (from awscli)
  Downloading colorama-0.4.6-py2.py3-none-any.whl.metadata (17 kB)
Collecting rsa<4.8,>=3.1.2 (from awscli)
  Downloading rsa-4.7.2-py3-none-any.whl.metadata (3.6 kB)
Collecting jmespath<2.0.0,>=0.7.1 (from botocore==1.42.90->awscli)
  Downloading jmespath-1.1.0-py3-none-any.whl.metadata (7.6 kB)
Requirement already satisfied: python-dateutil<3.0.0,>=2.1 in /usr/local/lib/python3.12/dist-packages (from botocore==1.42.90->awscli) (2.9.0.post0)
Requirement already satisfied: urllib3!=2.2.0,<3,>=1.25.4 in /usr/local/lib/python3.12/dist-packages (from botocore==1.42.90->awscli) (2.6.3)
Collecting pyasn1>=0.1.3 (from rsa<4.8,>=3.1.2->awscli)
  Downloading pyasn1-0.6.3-py3-none-any.whl.metadata (8.4 kB)
Requirement already satisfied: charset_normalizer<4,>=2 in /usr/local/lib/python3.12/dist-packages (from requests->huggingface_hub<1.0) (3.4.4)
Requirement already satisfied: idna<4,>=2.5 in /usr/local/lib/python3.12/dist-packages (from requests->huggingface_hub<1.0) (3.11)
Requirement already satisfied: certifi>=2017.4.17 in /usr/local/lib/python3.12/dist-packages (from requests->huggingface_hub<1.0) (2026.1.4)
Requirement already satisfied: six>=1.5 in /usr/local/lib/python3.12/dist-packages (from python-dateutil<3.0.0,>=2.1->botocore==1.42.90->awscli) (1.17.0)
Downloading awscli-1.44.80-py3-none-any.whl (4.6 MB)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 4.6/4.6 MB 12.0 MB/s eta 0:00:00
Downloading botocore-1.42.90-py3-none-any.whl (14.9 MB)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 14.9/14.9 MB 18.9 MB/s eta 0:00:00
Downloading colorama-0.4.6-py2.py3-none-any.whl (25 kB)
Downloading docutils-0.19-py3-none-any.whl (570 kB)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 570.5/570.5 kB 2.1 MB/s eta 0:00:00
Downloading rsa-4.7.2-py3-none-any.whl (34 kB)
Downloading s3transfer-0.16.0-py3-none-any.whl (86 kB)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 86.8/86.8 kB 284.4 kB/s eta 0:00:00
Downloading jmespath-1.1.0-py3-none-any.whl (20 kB)
Downloading pyasn1-0.6.3-py3-none-any.whl (83 kB)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 84.0/84.0 kB 350.1 kB/s eta 0:00:00
Installing collected packages: pyasn1, jmespath, docutils, colorama, rsa, botocore, s3transfer, awscli
Successfully installed awscli-1.44.80 botocore-1.42.90 colorama-0.4.6 docutils-0.19 jmespath-1.1.0 pyasn1-0.6.3 rsa-4.7.2 s3transfer-0.16.0
WARNING: Running pip as the 'root' user can result in broken permissions and conflicting behaviour with the system package manager. It is recommended to use a virtual environment instead: https://pip.pypa.io/warnings/venv
=== Downloading model ===
⚠️  Warning: 'huggingface-cli download' is deprecated. Use 'hf download' instead.
Fetching 47 files:   0%|          | 0/47 [00:00<?, ?it/s]Still waiting to acquire lock on /workspace/qwen-hf/.cache/huggingface/.gitignore.lock (elapsed: 0.1 seconds)
Downloading 'model-00001-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/zUKkfv3KRpkX5tprZwrHEyRUpxE=.18d5d2b73010054d1c9fc4a1ba777d575e871b10f1155f3ae22481b7752bc425.incomplete'
Downloading 'merges.txt' to '/workspace/qwen-hf/.cache/huggingface/download/PtHk0z_I45atnj23IIRhTExwT3w=.20024bfe7c83998e9aeaf98a0cd6a2ce6306c2f0.incomplete'
Downloading 'generation_config.json' to '/workspace/qwen-hf/.cache/huggingface/download/3EVKVggOldJcKSsGjSdoUCN1AyQ=.bf077f03dc569cfb8a90b3ec1ad20365a620bad6.incomplete'
Downloading 'model-00002-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/c8-5E8k7f3ZCUmBBdwh8BSO0UHM=.802a3abf41ccdeb01931c5e40eb177ea114a1c47f68cb251d75c2de0fe196677.incomplete'
Download complete. Moving file to /workspace/qwen-hf/generation_config.json
Downloading 'config.json' to '/workspace/qwen-hf/.cache/huggingface/download/8_PA_wEVGiVa2goH2H4KQOQpvVY=.ec6ea340e52a5c8a0cf264a7fc5efa0a5765f5ab.incomplete'
Download complete. Moving file to /workspace/qwen-hf/config.json
Download complete. Moving file to /workspace/qwen-hf/merges.txt
Downloading 'LICENSE' to '/workspace/qwen-hf/.cache/huggingface/download/DhCjcNQuMpl4FL346qr3tvNUCgY=.5dda3230b4cb5a86e8b120cce004d6e34b195ee4.incomplete'
Downloading '.gitattributes' to '/workspace/qwen-hf/.cache/huggingface/download/wPaCkH-WbT7GsmxMKKrNZTV4nSM=.a6344aac8c09253b3b630fb776ae94478aa0275b.incomplete'
Download complete. Moving file to /workspace/qwen-hf/LICENSE
Download complete. Moving file to /workspace/qwen-hf/.gitattributes
Fetching 47 files:   2%|▏         | 1/47 [00:00<00:19,  2.35it/s]Downloading 'README.md' to '/workspace/qwen-hf/.cache/huggingface/download/Xn7B-BWUGOee2Y6hCZtEhtFu4BE=.cbd59303c6fda0281d7e40d6b37a0139c2327c76.incomplete'
Download complete. Moving file to /workspace/qwen-hf/README.md
Downloading 'model-00004-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/toyYwfogk_j0C5l8L_jxBjCzLq0=.5f35d5475cc4730ca9a38f958f74b5322d28acbd4aec30560987ed12e2748d8f.incomplete'
Downloading 'model-00005-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/EtwYRo8De0Vkv6I9LO47MEPYb20=.b7f066aef57e0fe29b516ef743fec7a90518151bd5a9df19263dfdee214dfe4d.incomplete'
Downloading 'model-00006-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/7XGM88vqY97F4SJwm-640SmNXdo=.a1473de38b80322dae16603f76cf706509c0cf6bc4ef020b11f89272df89734c.incomplete'
Downloading 'model-00007-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/SmiT0SemvbIf2ku91uIKuWftyOo=.e5ea29c1b8319f85b89aaa3ae801a6d291da8361dab5c6413a9d64b5970c960d.incomplete'
Downloading 'model-00008-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/amyvjss0w_incvbKg_V9xGbiiyM=.06550d13ac2049282536a364765f6f81855aa8b7d1cc9a0b1561675ddbbf1abc.incomplete'
Downloading 'model-00003-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/PWNPM_wWNnp6nIs8gj6oOrrg2ew=.c3a2ab093723d4981dcc6b20c7f48c444ccd9d8572b59f0bf7caa632715b7d36.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00001-of-00037.safetensors
Fetching 47 files:  15%|█▍        | 7/47 [00:09<00:54,  1.35s/it]Downloading 'model-00009-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/cCsaOb1KJeVmio0kneb5BwOX7LY=.e0a1998eb4c0d62c40858b96eaa9046c3af469cc8a7bd971a419a079b8ee67af.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00002-of-00037.safetensors
Fetching 47 files:  17%|█▋        | 8/47 [00:10<00:49,  1.27s/it]Downloading 'model-00010-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/8t1xN90Zjv58gGtuVRHtTRz4G2E=.7efe4ecbd1f4368e3af4d0a1e02a731084948c928c1708b74e5ff62edd8e51b9.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00006-of-00037.safetensors
Download complete. Moving file to /workspace/qwen-hf/model-00005-of-00037.safetensors
Downloading 'model-00011-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/_sKyy-epc6OVFYXddtdKuZerSb8=.cf12aa8e041c69bc8edfb94e811582e9080342f3b7ef438005d95a6d2148f97f.incomplete'
Downloading 'model-00012-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/zR5wMyW3bwn8AgOS8r9i8BPGll4=.896275467b140f9a3447f5c7e7661d53b875287a46e434f98035d95215a18e1a.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00004-of-00037.safetensors
Downloading 'model-00013-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/PWuBP-Hof8RRqr17zbm-lsSqkWg=.091e0a428c3786c0fe75fb9f3445ea7173f0f6af35133a898bf817890d16bec3.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00009-of-00037.safetensors
Downloading 'model-00014-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/thvUQ1D_SSAk7X9laonYIrmn2cY=.cdb3585244781534f601d22fbba8e2583fe0fc08d46846df86788bb08a4f9b9b.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00003-of-00037.safetensors
Fetching 47 files:  19%|█▉        | 9/47 [00:22<02:17,  3.61s/it]Downloading 'model-00015-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/5165UonhYHQraDFi8a6AzeYNDDA=.8f6d40610c1470d4097c298a3ad6951ae06bf60458d743fb77be4b52753e0b9c.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00008-of-00037.safetensors
Download complete. Moving file to /workspace/qwen-hf/model-00007-of-00037.safetensors
Fetching 47 files:  28%|██▊       | 13/47 [00:23<00:59,  1.75s/it]Downloading 'model-00016-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/Pqpxba7EhM6HCzYC2Kg8oCdwqeA=.32b0cb30dcde0bd0a00c2191cd0ced6786aed1126b424e2827987d53cb412eb7.incomplete'
Downloading 'model-00017-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/AQNmR-1e4bk1MxjWIPrc4w1IWwo=.9116ecb031259f72c2085de9c71591a592fb4c9590bedad42ef6dd0c6ca02de0.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00010-of-00037.safetensors
Fetching 47 files:  34%|███▍      | 16/47 [00:31<01:04,  2.08s/it]Downloading 'model-00018-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/TqmnkGgkYOh9oc1C4BkLgoIXUlA=.50c3e64805aefc412a2e3c24c9684e60cdfad5042a5879e237ed28c00a4323cd.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00011-of-00037.safetensors
Fetching 47 files:  36%|███▌      | 17/47 [00:32<00:55,  1.86s/it]Downloading 'model-00019-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/a2SvMG7FKVksm1A2v3jrekT3qiI=.9275ea7913f9f70c62ba13245318a196f04f8494336bc24f93f315a0a3a3d5b5.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00012-of-00037.safetensors
Fetching 47 files:  38%|███▊      | 18/47 [00:33<00:49,  1.71s/it]Downloading 'model-00020-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/1kjP73ObEPQQM877s7QqDKXBL28=.087dd3463d133700f2da7e9d8eb6a752cb4c3a9fcf968b2031f7c0a578e632f2.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00013-of-00037.safetensors
Fetching 47 files:  40%|████      | 19/47 [00:54<02:38,  5.66s/it]Downloading 'model-00021-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/29h4zHmYr8E8AuK7X2e-QUtIZBQ=.cd59943f5e87c0ceb76cd5935d6ac5d37546a56ba922c6a0f32aef6ca69c2551.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00014-of-00037.safetensors
Fetching 47 files:  43%|████▎     | 20/47 [01:46<07:07, 15.82s/it]Downloading 'model-00022-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/RakmARBvW4EsjQrnXzyvMcrKi0c=.0e873a7920f6dc3cb7d77ea3461b5347f3cd4fd7d959d7031fd887cee774125d.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00015-of-00037.safetensors
Fetching 47 files:  45%|████▍     | 21/47 [02:04<07:05, 16.36s/it]Downloading 'model-00023-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/J1oMpKdqLPy_kDuyhVBDyxjt37Q=.6893234eee631eba0f2369a3662b06abbd6a3ffb3a071df270764b01cdece9d6.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00016-of-00037.safetensors
Fetching 47 files:  47%|████▋     | 22/47 [02:21<06:57, 16.68s/it]Downloading 'model-00024-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/xzjc0uSa3ivbx-Q3rq86-wwa9YE=.be18adbce7138854a03ce67c6d24b4b0335569469d75674d89a7c35bf1b1a94b.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00017-of-00037.safetensors
Fetching 47 files:  49%|████▉     | 23/47 [02:34<06:13, 15.57s/it]Downloading 'model-00025-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/VOLbaK9jDIzRuVtFgpwoddxh2bw=.b49167af857270e82644d70b5cb15bcc16fff110cecdc002019b086881653795.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00019-of-00037.safetensors
Downloading 'model-00026-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/LhE6ZZLQusxKmEMsmZjiv-sGpNU=.5c31de1f4370b1f5f151e6f1a0bbc3916fbc1efbaed4086ed503e9c85876762f.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00018-of-00037.safetensors
Fetching 47 files:  51%|█████     | 24/47 [03:38<11:09, 29.11s/it]Downloading 'model-00027-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/5fgfBW59qVtg2TAriqL_R3GeOGU=.9007ad8b748efd183aac5da812827af95ed06fb885aa986ed8d539d3f46c71b4.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00020-of-00037.safetensors
Fetching 47 files:  55%|█████▌    | 26/47 [03:51<06:38, 18.99s/it]Downloading 'model-00028-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/R0uaEycUZSiqEBHfikPKnFSCzSM=.b66cf1a6d0017bb135f39062ff833f2e24fdf376ed4298e5cb866a1dc72803a0.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00021-of-00037.safetensors
Fetching 47 files:  57%|█████▋    | 27/47 [05:07<10:56, 32.82s/it]Downloading 'model-00029-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/JTE5g9SG-gdFYoGpgm6XZQASG7E=.9302f5f8a35c25dffe27e0a34ba50c41dd98f79c612e5012f321e4ca906fab0f.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00022-of-00037.safetensors
Fetching 47 files:  60%|█████▉    | 28/47 [06:12<12:56, 40.88s/it]Downloading 'model-00030-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/rTylzpwFDUxY9L2SPUxodzJQBG8=.7b73b03e07b9d452b4728ae2ded5ad71f7f4c135fcb8d266286275852c68f3d4.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00023-of-00037.safetensors
Fetching 47 files:  62%|██████▏   | 29/47 [06:18<09:28, 31.61s/it]Downloading 'model-00031-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/1hRhBOtgsZ1Z_5BCVcTRwqKxFdQ=.c62718790b43c5f780502ea421adb5e70f9192a972713ca7e628eb5c4f1e759b.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00024-of-00037.safetensors
Fetching 47 files:  64%|██████▍   | 30/47 [06:36<07:52, 27.81s/it]Downloading 'model-00032-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/ORxeoQ-HepJsvaViP2YLW_Kh5GE=.8b3e9f57b1e1a437ec54d9ef88ebd2b256b323f968f0de526fe4815a39e813f8.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00025-of-00037.safetensors
Fetching 47 files:  66%|██████▌   | 31/47 [06:48<06:14, 23.43s/it]Downloading 'model-00033-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/BtFBv4OsI8JcLHKLMoE3xkqrTN0=.8972bac3d98c35003329d695b1867a2e87a7938918773eef7cd62bfe21331eeb.incomplete'
(base) ubuntu@ip-10-0-0-195:~/triton$ kubectl logs job/trtllm-engine-build -f
Requirement already satisfied: huggingface_hub<1.0 in /usr/local/lib/python3.12/dist-packages (0.36.2)
Collecting awscli
  Downloading awscli-1.44.80-py3-none-any.whl.metadata (11 kB)
Requirement already satisfied: filelock in /usr/local/lib/python3.12/dist-packages (from huggingface_hub<1.0) (3.21.2)
Requirement already satisfied: fsspec>=2023.5.0 in /usr/local/lib/python3.12/dist-packages (from huggingface_hub<1.0) (2024.9.0)
Requirement already satisfied: hf-xet<2.0.0,>=1.1.3 in /usr/local/lib/python3.12/dist-packages (from huggingface_hub<1.0) (1.2.0)
Requirement already satisfied: packaging>=20.9 in /usr/local/lib/python3.12/dist-packages (from huggingface_hub<1.0) (25.0)
Requirement already satisfied: pyyaml>=5.1 in /usr/local/lib/python3.12/dist-packages (from huggingface_hub<1.0) (6.0.3)
Requirement already satisfied: requests in /usr/local/lib/python3.12/dist-packages (from huggingface_hub<1.0) (2.32.5)
Requirement already satisfied: tqdm>=4.42.1 in /usr/local/lib/python3.12/dist-packages (from huggingface_hub<1.0) (4.67.3)
Requirement already satisfied: typing-extensions>=3.7.4.3 in /usr/local/lib/python3.12/dist-packages (from huggingface_hub<1.0) (4.15.0)
Collecting botocore==1.42.90 (from awscli)
  Downloading botocore-1.42.90-py3-none-any.whl.metadata (5.9 kB)
Collecting docutils<=0.19,>=0.18.1 (from awscli)
  Downloading docutils-0.19-py3-none-any.whl.metadata (2.7 kB)
Collecting s3transfer<0.17.0,>=0.16.0 (from awscli)
  Downloading s3transfer-0.16.0-py3-none-any.whl.metadata (1.7 kB)
Collecting colorama<0.4.7,>=0.2.5 (from awscli)
  Downloading colorama-0.4.6-py2.py3-none-any.whl.metadata (17 kB)
Collecting rsa<4.8,>=3.1.2 (from awscli)
  Downloading rsa-4.7.2-py3-none-any.whl.metadata (3.6 kB)
Collecting jmespath<2.0.0,>=0.7.1 (from botocore==1.42.90->awscli)
  Downloading jmespath-1.1.0-py3-none-any.whl.metadata (7.6 kB)
Requirement already satisfied: python-dateutil<3.0.0,>=2.1 in /usr/local/lib/python3.12/dist-packages (from botocore==1.42.90->awscli) (2.9.0.post0)
Requirement already satisfied: urllib3!=2.2.0,<3,>=1.25.4 in /usr/local/lib/python3.12/dist-packages (from botocore==1.42.90->awscli) (2.6.3)
Collecting pyasn1>=0.1.3 (from rsa<4.8,>=3.1.2->awscli)
  Downloading pyasn1-0.6.3-py3-none-any.whl.metadata (8.4 kB)
Requirement already satisfied: charset_normalizer<4,>=2 in /usr/local/lib/python3.12/dist-packages (from requests->huggingface_hub<1.0) (3.4.4)
Requirement already satisfied: idna<4,>=2.5 in /usr/local/lib/python3.12/dist-packages (from requests->huggingface_hub<1.0) (3.11)
Requirement already satisfied: certifi>=2017.4.17 in /usr/local/lib/python3.12/dist-packages (from requests->huggingface_hub<1.0) (2026.1.4)
Requirement already satisfied: six>=1.5 in /usr/local/lib/python3.12/dist-packages (from python-dateutil<3.0.0,>=2.1->botocore==1.42.90->awscli) (1.17.0)
Downloading awscli-1.44.80-py3-none-any.whl (4.6 MB)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 4.6/4.6 MB 12.0 MB/s eta 0:00:00
Downloading botocore-1.42.90-py3-none-any.whl (14.9 MB)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 14.9/14.9 MB 18.9 MB/s eta 0:00:00
Downloading colorama-0.4.6-py2.py3-none-any.whl (25 kB)
Downloading docutils-0.19-py3-none-any.whl (570 kB)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 570.5/570.5 kB 2.1 MB/s eta 0:00:00
Downloading rsa-4.7.2-py3-none-any.whl (34 kB)
Downloading s3transfer-0.16.0-py3-none-any.whl (86 kB)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 86.8/86.8 kB 284.4 kB/s eta 0:00:00
Downloading jmespath-1.1.0-py3-none-any.whl (20 kB)
Downloading pyasn1-0.6.3-py3-none-any.whl (83 kB)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 84.0/84.0 kB 350.1 kB/s eta 0:00:00
Installing collected packages: pyasn1, jmespath, docutils, colorama, rsa, botocore, s3transfer, awscli
Successfully installed awscli-1.44.80 botocore-1.42.90 colorama-0.4.6 docutils-0.19 jmespath-1.1.0 pyasn1-0.6.3 rsa-4.7.2 s3transfer-0.16.0
WARNING: Running pip as the 'root' user can result in broken permissions and conflicting behaviour with the system package manager. It is recommended to use a virtual environment instead: https://pip.pypa.io/warnings/venv
=== Downloading model ===
⚠️  Warning: 'huggingface-cli download' is deprecated. Use 'hf download' instead.
Fetching 47 files:   0%|          | 0/47 [00:00<?, ?it/s]Still waiting to acquire lock on /workspace/qwen-hf/.cache/huggingface/.gitignore.lock (elapsed: 0.1 seconds)
Downloading 'model-00001-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/zUKkfv3KRpkX5tprZwrHEyRUpxE=.18d5d2b73010054d1c9fc4a1ba777d575e871b10f1155f3ae22481b7752bc425.incomplete'
Downloading 'merges.txt' to '/workspace/qwen-hf/.cache/huggingface/download/PtHk0z_I45atnj23IIRhTExwT3w=.20024bfe7c83998e9aeaf98a0cd6a2ce6306c2f0.incomplete'
Downloading 'generation_config.json' to '/workspace/qwen-hf/.cache/huggingface/download/3EVKVggOldJcKSsGjSdoUCN1AyQ=.bf077f03dc569cfb8a90b3ec1ad20365a620bad6.incomplete'
Downloading 'model-00002-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/c8-5E8k7f3ZCUmBBdwh8BSO0UHM=.802a3abf41ccdeb01931c5e40eb177ea114a1c47f68cb251d75c2de0fe196677.incomplete'
Download complete. Moving file to /workspace/qwen-hf/generation_config.json
Downloading 'config.json' to '/workspace/qwen-hf/.cache/huggingface/download/8_PA_wEVGiVa2goH2H4KQOQpvVY=.ec6ea340e52a5c8a0cf264a7fc5efa0a5765f5ab.incomplete'
Download complete. Moving file to /workspace/qwen-hf/config.json
Download complete. Moving file to /workspace/qwen-hf/merges.txt
Downloading 'LICENSE' to '/workspace/qwen-hf/.cache/huggingface/download/DhCjcNQuMpl4FL346qr3tvNUCgY=.5dda3230b4cb5a86e8b120cce004d6e34b195ee4.incomplete'
Downloading '.gitattributes' to '/workspace/qwen-hf/.cache/huggingface/download/wPaCkH-WbT7GsmxMKKrNZTV4nSM=.a6344aac8c09253b3b630fb776ae94478aa0275b.incomplete'
Download complete. Moving file to /workspace/qwen-hf/LICENSE
Download complete. Moving file to /workspace/qwen-hf/.gitattributes
Fetching 47 files:   2%|▏         | 1/47 [00:00<00:19,  2.35it/s]Downloading 'README.md' to '/workspace/qwen-hf/.cache/huggingface/download/Xn7B-BWUGOee2Y6hCZtEhtFu4BE=.cbd59303c6fda0281d7e40d6b37a0139c2327c76.incomplete'
Download complete. Moving file to /workspace/qwen-hf/README.md
Downloading 'model-00004-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/toyYwfogk_j0C5l8L_jxBjCzLq0=.5f35d5475cc4730ca9a38f958f74b5322d28acbd4aec30560987ed12e2748d8f.incomplete'
Downloading 'model-00005-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/EtwYRo8De0Vkv6I9LO47MEPYb20=.b7f066aef57e0fe29b516ef743fec7a90518151bd5a9df19263dfdee214dfe4d.incomplete'
Downloading 'model-00006-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/7XGM88vqY97F4SJwm-640SmNXdo=.a1473de38b80322dae16603f76cf706509c0cf6bc4ef020b11f89272df89734c.incomplete'
Downloading 'model-00007-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/SmiT0SemvbIf2ku91uIKuWftyOo=.e5ea29c1b8319f85b89aaa3ae801a6d291da8361dab5c6413a9d64b5970c960d.incomplete'
Downloading 'model-00008-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/amyvjss0w_incvbKg_V9xGbiiyM=.06550d13ac2049282536a364765f6f81855aa8b7d1cc9a0b1561675ddbbf1abc.incomplete'
Downloading 'model-00003-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/PWNPM_wWNnp6nIs8gj6oOrrg2ew=.c3a2ab093723d4981dcc6b20c7f48c444ccd9d8572b59f0bf7caa632715b7d36.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00001-of-00037.safetensors
Fetching 47 files:  15%|█▍        | 7/47 [00:09<00:54,  1.35s/it]Downloading 'model-00009-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/cCsaOb1KJeVmio0kneb5BwOX7LY=.e0a1998eb4c0d62c40858b96eaa9046c3af469cc8a7bd971a419a079b8ee67af.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00002-of-00037.safetensors
Fetching 47 files:  17%|█▋        | 8/47 [00:10<00:49,  1.27s/it]Downloading 'model-00010-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/8t1xN90Zjv58gGtuVRHtTRz4G2E=.7efe4ecbd1f4368e3af4d0a1e02a731084948c928c1708b74e5ff62edd8e51b9.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00006-of-00037.safetensors
Download complete. Moving file to /workspace/qwen-hf/model-00005-of-00037.safetensors
Downloading 'model-00011-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/_sKyy-epc6OVFYXddtdKuZerSb8=.cf12aa8e041c69bc8edfb94e811582e9080342f3b7ef438005d95a6d2148f97f.incomplete'
Downloading 'model-00012-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/zR5wMyW3bwn8AgOS8r9i8BPGll4=.896275467b140f9a3447f5c7e7661d53b875287a46e434f98035d95215a18e1a.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00004-of-00037.safetensors
Downloading 'model-00013-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/PWuBP-Hof8RRqr17zbm-lsSqkWg=.091e0a428c3786c0fe75fb9f3445ea7173f0f6af35133a898bf817890d16bec3.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00009-of-00037.safetensors
Downloading 'model-00014-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/thvUQ1D_SSAk7X9laonYIrmn2cY=.cdb3585244781534f601d22fbba8e2583fe0fc08d46846df86788bb08a4f9b9b.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00003-of-00037.safetensors
Fetching 47 files:  19%|█▉        | 9/47 [00:22<02:17,  3.61s/it]Downloading 'model-00015-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/5165UonhYHQraDFi8a6AzeYNDDA=.8f6d40610c1470d4097c298a3ad6951ae06bf60458d743fb77be4b52753e0b9c.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00008-of-00037.safetensors
Download complete. Moving file to /workspace/qwen-hf/model-00007-of-00037.safetensors
Fetching 47 files:  28%|██▊       | 13/47 [00:23<00:59,  1.75s/it]Downloading 'model-00016-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/Pqpxba7EhM6HCzYC2Kg8oCdwqeA=.32b0cb30dcde0bd0a00c2191cd0ced6786aed1126b424e2827987d53cb412eb7.incomplete'
Downloading 'model-00017-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/AQNmR-1e4bk1MxjWIPrc4w1IWwo=.9116ecb031259f72c2085de9c71591a592fb4c9590bedad42ef6dd0c6ca02de0.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00010-of-00037.safetensors
Fetching 47 files:  34%|███▍      | 16/47 [00:31<01:04,  2.08s/it]Downloading 'model-00018-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/TqmnkGgkYOh9oc1C4BkLgoIXUlA=.50c3e64805aefc412a2e3c24c9684e60cdfad5042a5879e237ed28c00a4323cd.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00011-of-00037.safetensors
Fetching 47 files:  36%|███▌      | 17/47 [00:32<00:55,  1.86s/it]Downloading 'model-00019-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/a2SvMG7FKVksm1A2v3jrekT3qiI=.9275ea7913f9f70c62ba13245318a196f04f8494336bc24f93f315a0a3a3d5b5.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00012-of-00037.safetensors
Fetching 47 files:  38%|███▊      | 18/47 [00:33<00:49,  1.71s/it]Downloading 'model-00020-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/1kjP73ObEPQQM877s7QqDKXBL28=.087dd3463d133700f2da7e9d8eb6a752cb4c3a9fcf968b2031f7c0a578e632f2.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00013-of-00037.safetensors
Fetching 47 files:  40%|████      | 19/47 [00:54<02:38,  5.66s/it]Downloading 'model-00021-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/29h4zHmYr8E8AuK7X2e-QUtIZBQ=.cd59943f5e87c0ceb76cd5935d6ac5d37546a56ba922c6a0f32aef6ca69c2551.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00014-of-00037.safetensors
Fetching 47 files:  43%|████▎     | 20/47 [01:46<07:07, 15.82s/it]Downloading 'model-00022-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/RakmARBvW4EsjQrnXzyvMcrKi0c=.0e873a7920f6dc3cb7d77ea3461b5347f3cd4fd7d959d7031fd887cee774125d.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00015-of-00037.safetensors
Fetching 47 files:  45%|████▍     | 21/47 [02:04<07:05, 16.36s/it]Downloading 'model-00023-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/J1oMpKdqLPy_kDuyhVBDyxjt37Q=.6893234eee631eba0f2369a3662b06abbd6a3ffb3a071df270764b01cdece9d6.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00016-of-00037.safetensors
Fetching 47 files:  47%|████▋     | 22/47 [02:21<06:57, 16.68s/it]Downloading 'model-00024-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/xzjc0uSa3ivbx-Q3rq86-wwa9YE=.be18adbce7138854a03ce67c6d24b4b0335569469d75674d89a7c35bf1b1a94b.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00017-of-00037.safetensors
Fetching 47 files:  49%|████▉     | 23/47 [02:34<06:13, 15.57s/it]Downloading 'model-00025-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/VOLbaK9jDIzRuVtFgpwoddxh2bw=.b49167af857270e82644d70b5cb15bcc16fff110cecdc002019b086881653795.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00019-of-00037.safetensors
Downloading 'model-00026-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/LhE6ZZLQusxKmEMsmZjiv-sGpNU=.5c31de1f4370b1f5f151e6f1a0bbc3916fbc1efbaed4086ed503e9c85876762f.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00018-of-00037.safetensors
Fetching 47 files:  51%|█████     | 24/47 [03:38<11:09, 29.11s/it]Downloading 'model-00027-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/5fgfBW59qVtg2TAriqL_R3GeOGU=.9007ad8b748efd183aac5da812827af95ed06fb885aa986ed8d539d3f46c71b4.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00020-of-00037.safetensors
Fetching 47 files:  55%|█████▌    | 26/47 [03:51<06:38, 18.99s/it]Downloading 'model-00028-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/R0uaEycUZSiqEBHfikPKnFSCzSM=.b66cf1a6d0017bb135f39062ff833f2e24fdf376ed4298e5cb866a1dc72803a0.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00021-of-00037.safetensors
Fetching 47 files:  57%|█████▋    | 27/47 [05:07<10:56, 32.82s/it]Downloading 'model-00029-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/JTE5g9SG-gdFYoGpgm6XZQASG7E=.9302f5f8a35c25dffe27e0a34ba50c41dd98f79c612e5012f321e4ca906fab0f.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00022-of-00037.safetensors
Fetching 47 files:  60%|█████▉    | 28/47 [06:12<12:56, 40.88s/it]Downloading 'model-00030-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/rTylzpwFDUxY9L2SPUxodzJQBG8=.7b73b03e07b9d452b4728ae2ded5ad71f7f4c135fcb8d266286275852c68f3d4.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00023-of-00037.safetensors
Fetching 47 files:  62%|██████▏   | 29/47 [06:18<09:28, 31.61s/it]Downloading 'model-00031-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/1hRhBOtgsZ1Z_5BCVcTRwqKxFdQ=.c62718790b43c5f780502ea421adb5e70f9192a972713ca7e628eb5c4f1e759b.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00024-of-00037.safetensors
Fetching 47 files:  64%|██████▍   | 30/47 [06:36<07:52, 27.81s/it]Downloading 'model-00032-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/ORxeoQ-HepJsvaViP2YLW_Kh5GE=.8b3e9f57b1e1a437ec54d9ef88ebd2b256b323f968f0de526fe4815a39e813f8.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00025-of-00037.safetensors
Fetching 47 files:  66%|██████▌   | 31/47 [06:48<06:14, 23.43s/it]Downloading 'model-00033-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/BtFBv4OsI8JcLHKLMoE3xkqrTN0=.8972bac3d98c35003329d695b1867a2e87a7938918773eef7cd62bfe21331eeb.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00026-of-00037.safetensors
Fetching 47 files:  68%|██████▊   | 32/47 [07:54<08:56, 35.75s/it]Downloading 'model-00034-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/pF_eEVXVGljfscQSuvm1bYFxgFI=.0762d964ad4abe025edfd986db3798c88c1199b1e8105fb027f765909dbb07b3.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00027-of-00037.safetensors
Fetching 47 files:  70%|███████   | 33/47 [07:56<06:02, 25.93s/it]Downloading 'model-00035-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/hVC2w-UuAWXt5GD6lk8ruJPiito=.84b7078fc68cdb4992a6de10bfb666117a32a8f6e7aef7a132b7033d83ec1d05.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00028-of-00037.safetensors
Fetching 47 files:  72%|███████▏  | 34/47 [08:16<05:13, 24.09s/it]Downloading 'model-00036-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/GmPoewfbYVtDIyeBjXvpsLuFpnc=.ecfb653ff282bbde48fc27ec9680e82b4b4c51a9d5227a8a4c2c6797855110e8.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00029-of-00037.safetensors
Fetching 47 files:  74%|███████▍  | 35/47 [09:45<08:39, 43.31s/it]Downloading 'model-00037-of-00037.safetensors' to '/workspace/qwen-hf/.cache/huggingface/download/JpBsDZFuG_PaLqs8Kw_g7II-DWQ=.d9e727663a5f18259d0cba4efaad8145732ea9f9c6794d5ef63a3ef1687768a1.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model-00031-of-00037.safetensors
Downloading 'model.safetensors.index.json' to '/workspace/qwen-hf/.cache/huggingface/download/yVzAsSxRSINSz-tQbpx-TLpfkLU=.d742031f47c4b58cad3928882c5ab8afad16b695.incomplete'
Download complete. Moving file to /workspace/qwen-hf/model.safetensors.index.json
Downloading 'tokenizer.json' to '/workspace/qwen-hf/.cache/huggingface/download/HgM_lKo9sdSCfRtVg7MMFS7EKqo=.443909a61d429dff23010e5bddd28ff530edda00.incomplete'
Download complete. Moving file to /workspace/qwen-hf/tokenizer.json
Downloading 'tokenizer_config.json' to '/workspace/qwen-hf/.cache/huggingface/download/vzaExXFZNBay89bvlQv-ZcI6BTg=.07bfe0640cb5a0037f9322287fbfc682806cf672.incomplete'
Download complete. Moving file to /workspace/qwen-hf/tokenizer_config.json
Download complete. Moving file to /workspace/qwen-hf/model-00030-of-00037.safetensors
Fetching 47 files:  77%|███████▋  | 36/47 [10:56<09:26, 51.47s/it]Downloading 'vocab.json' to '/workspace/qwen-hf/.cache/huggingface/download/j3m-Hy6QvBddw8RXA1uSWl1AJ0c=.4783fe10ac3adce15ac8f358ef5462739852c569.incomplete'
Download complete. Moving file to /workspace/qwen-hf/vocab.json
Download complete. Moving file to /workspace/qwen-hf/model-00032-of-00037.safetensors
Fetching 47 files:  81%|████████  | 38/47 [11:08<04:35, 30.63s/it]Download complete. Moving file to /workspace/qwen-hf/model-00033-of-00037.safetensors
Fetching 47 files:  83%|████████▎ | 39/47 [11:16<03:20, 25.05s/it]Download complete. Moving file to /workspace/qwen-hf/model-00035-of-00037.safetensors
Download complete. Moving file to /workspace/qwen-hf/model-00034-of-00037.safetensors
Fetching 47 files:  85%|████████▌ | 40/47 [12:05<03:38, 31.16s/it]Download complete. Moving file to /workspace/qwen-hf/model-00036-of-00037.safetensors
Fetching 47 files:  89%|████████▉ | 42/47 [12:19<01:45, 21.01s/it]Download complete. Moving file to /workspace/qwen-hf/model-00037-of-00037.safetensors
Fetching 47 files: 100%|██████████| 47/47 [12:26<00:00, 15.89s/it]
/workspace/qwen-hf
=== Converting checkpoint ===
/usr/local/lib/python3.12/dist-packages/torch/cuda/__init__.py:63: FutureWarning: The pynvml package is deprecated. Please install nvidia-ml-py instead. If you did not install pynvml directly, please report this to the maintainers of the package that installed pynvml for you.
  import pynvml  # type: ignore[import]
W0417 00:46:37.981000 195 torch/utils/cpp_extension.py:2422] TORCH_CUDA_ARCH_LIST is not set, all archs for visible cards are included for compilation. 
W0417 00:46:37.981000 195 torch/utils/cpp_extension.py:2422] If this is not desired, please set os.environ['TORCH_CUDA_ARCH_LIST'] to specific architectures.
[TensorRT-LLM] TensorRT LLM version: 1.1.0
`torch_dtype` is deprecated! Use `dtype` instead!
1.1.0
646it [00:00, 888.04it/s]
...
```

> [!TIP]
> 설치된 파이썬 패키지 조회하기    
> kubectl exec -it [pod name] -- bash  
> pip show transformers torch tensorrt_llm  

> [!IMPORTANT]
>
> HuggingFace 모델과 TensorRT-LLM 엔진은 가중치 포맷이 다르다.  
> * HuggingFace: PyTorch 텐서 형태 (safetensors/bin)  
> * TensorRT-LLM: 자체 포맷으로 레이어 이름, 구조, 양자화 정보 등이 재배치  
> 
> convert_checkpoint.py가 하는 일은 HF 가중치를 TRT-LLM이 이해할 수 있는 포맷으로 변환하는 것이다. TP(텐서 병렬) 분할도 이 단계에서 처리되고, 4개 GPU에 나눠 올리려면 가중치를 미리 4등분된다. 그 다음 trtllm-build가 변환된 체크포인트를 받아서 TensorRT 엔진(최적화된 실행 계획)으로 컴파일한다.   
> 
> 상세 코드는 아래와 같다.
> 
> huggingface-cli download Qwen/Qwen2.5-72B-Instruct --local-dir /workspace/qwen-hf
> 
> python3 /app/examples/models/core/qwen/convert_checkpoint.py \
>   --model_dir /workspace/qwen-hf \
>   --output_dir /workspace/qwen-trtllm-ckpt \
>   --dtype bfloat16 \
>   --tp_size 4
>
> trtllm-build --checkpoint_dir /workspace/qwen-trtllm-ckpt \
>   --output_dir /workspace/engines/qwen \
>   --max_input_len 4096 \
>   --max_seq_len 8192 \
>   --max_batch_size 64 \
>   --gemm_plugin auto \
>   --gpt_attention_plugin auto
>

### 모델 서빙하기 ###
[trtllm-qwen.yaml](https://github.com/gnosia93/eks-agentic-ai/blob/main/code/yaml/trtllm-qwen.yaml) 로 TensorRT-LLM 서버를 배포한다.
```
curl -o trtllm-qwen.yaml \
  https://raw.githubusercontent.com/gnosia93/eks-agentic-ai/refs/heads/main/code/yaml/trtllm-qwen.yaml
kubectl apply -f trtllm-qwen.yaml
```

## 추론 성능 비교 (versus vLLM) ##
```
pip install genai-perf

genai-perf profile \
    --model qwen \
    --endpoint-type chat \
    --url http://<서비스주소>:8000 \
    --num-prompts 100 \
    --concurrency 10
```
#### 측정 항목: ####
* TTFT (Time To First Token): 첫 토큰까지 걸리는 시간
* ITL (Inter-Token Latency): 토큰 간 지연
* Throughput: 초당 생성 토큰 수
* Request Latency: 요청당 전체 응답 시간

### 측정 결과 ###
* vLLM
  
* TensorRT-LLM


## 보강 ##
* 전체 소요 시간 (다운로드, 변환, 빌드 각각) / 필요 디스크 용량.



## 레퍼런스 ##
* NGC 이미지 태그 목록: https://catalog.ngc.nvidia.com/orgs/nvidia/containers/tritonserver/tags
* 버전별 호환성 매트릭스: https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/introduction/compatibility.html
* TRT-LLM GitHub 릴리즈: https://github.com/NVIDIA/TensorRT-LLM/releases
* trtllm-serve: https://nvidia.github.io/TensorRT-LLM/1.1.0/commands/trtllm-serve/trtllm-serve.html
* https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/index.html

