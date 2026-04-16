## vLLM 인퍼런스 ##

### vLLM 배포하기 ###
[Qwen2.5-72B](https://huggingface.co/Qwen/Qwen2.5-72B-Instruct) 모델을 g6e.12xlarge (L40S 48GB * 4EA, TP=4) 설정으로 2개의 파드로 구성한다.  [vllm-qwen.yaml](https://raw.githubusercontent.com/gnosia93/eks-agentic-ai/refs/heads/main/code/yaml/vllm-qwen.yaml) 파일을 다운로드 받은 후 디플로이먼트를 생성한다.

```bash
mkdir vllm && cd vllm
curl -o vllm-qwen.yaml https://raw.githubusercontent.com/gnosia93/eks-agentic-ai/refs/heads/main/code/yaml/vllm-qwen.yaml

kubectl apply -f vllm-qwen.yaml
```
vLLM은 시작 시 먼저 모델 가중치를 GPU 메모리에 로드하고, gpu-memory-utilization 설정값에 따라 사용 가능한 전체 메모리 범위를 결정한다. 그런 다음 모델 가중치와 내부 버퍼를 제외한 나머지 메모리를 KV Cache로 자동 할당하며, 이 KV Cache 크기와 max-model-len을 기반으로 동시에 처리할 수 있는 최대 요청 수를 자동으로 결정한다.
모델 가중치 로드 → 남은 메모리 계산 (gpu-memory-utilization 기준) → 남은 메모리를 KV Cache로 자동 할당 → KV Cache 크기 + max-model-len 기반으로 동시 처리 가능 수 자동 결정
```
kubectl get pods
```
[결과]
```
vllm-qwen-788d98bbfd-r2tjg   0/1     ContainerCreating   0               21m
vllm-qwen-849cb97c7c-fcfnh   0/1     Running             0               7m54s
```
![](https://github.com/gnosia93/eks-agentic-ai/blob/main/lesson/images/qwen-72B-node-viewer.png)
```bash
kubectl logs -f vllm-qwen-849cb97c7c-fcfnh
```
[결과]
```
(APIServer pid=1) INFO 04-16 11:02:11 [utils.py:299] 
(APIServer pid=1) INFO 04-16 11:02:11 [utils.py:299]        █     █     █▄   ▄█
(APIServer pid=1) INFO 04-16 11:02:11 [utils.py:299]  ▄▄ ▄█ █     █     █ ▀▄▀ █  version 0.19.0
(APIServer pid=1) INFO 04-16 11:02:11 [utils.py:299]   █▄█▀ █     █     █     █  model   Qwen/Qwen2.5-72B-Instruct
(APIServer pid=1) INFO 04-16 11:02:11 [utils.py:299]    ▀▀  ▀▀▀▀▀ ▀▀▀▀▀ ▀     ▀
(APIServer pid=1) INFO 04-16 11:02:11 [utils.py:299] 
(APIServer pid=1) INFO 04-16 11:02:11 [utils.py:233] non-default args: {'model': 'Qwen/Qwen2.5-72B-Instruct', 'max_model_len': 8192, 'served_model_name': ['qwen'], 'tensor_parallel_size': 4}
(APIServer pid=1) WARNING 04-16 11:02:11 [envs.py:1744] Unknown vLLM environment variable detected: VLLM_QWEN_SVC_PORT_80_TCP_PORT
(APIServer pid=1) WARNING 04-16 11:02:11 [envs.py:1744] Unknown vLLM environment variable detected: VLLM_QWEN_SVC_SERVICE_HOST
(APIServer pid=1) WARNING 04-16 11:02:11 [envs.py:1744] Unknown vLLM environment variable detected: VLLM_QWEN_SVC_SERVICE_PORT
(APIServer pid=1) WARNING 04-16 11:02:11 [envs.py:1744] Unknown vLLM environment variable detected: VLLM_QWEN_SVC_PORT_80_TCP_PROTO
(APIServer pid=1) WARNING 04-16 11:02:11 [envs.py:1744] Unknown vLLM environment variable detected: VLLM_QWEN_SVC_PORT_80_TCP
(APIServer pid=1) WARNING 04-16 11:02:11 [envs.py:1744] Unknown vLLM environment variable detected: VLLM_QWEN_SVC_PORT_80_TCP_ADDR
(APIServer pid=1) WARNING 04-16 11:02:11 [envs.py:1744] Unknown vLLM environment variable detected: VLLM_QWEN_SVC_PORT
(APIServer pid=1) INFO 04-16 11:02:24 [model.py:549] Resolved architecture: Qwen2ForCausalLM
(APIServer pid=1) INFO 04-16 11:02:24 [model.py:1678] Using max model len 8192
(APIServer pid=1) INFO 04-16 11:02:24 [vllm.py:790] Asynchronous scheduling is enabled.
(EngineCore pid=272) INFO 04-16 11:02:32 [core.py:105] Initializing a V1 LLM engine (v0.19.0) with config: model='Qwen/Qwen2.5-72B-Instruct', speculative_config=None, tokenizer='Qwen/Qwen2.5-72B-Instruct', skip_tokenizer_init=False, tokenizer_mode=auto, revision=None, tokenizer_revision=None, trust_remote_code=False, dtype=torch.bfloat16, max_seq_len=8192, download_dir=None, load_format=auto, tensor_parallel_size=4, pipeline_parallel_size=1, data_parallel_size=1, decode_context_parallel_size=1, dcp_comm_backend=ag_rs, disable_custom_all_reduce=False, quantization=None, enforce_eager=False, enable_return_routed_experts=False, kv_cache_dtype=auto, device_config=cuda, structured_outputs_config=StructuredOutputsConfig(backend='auto', disable_any_whitespace=False, disable_additional_properties=False, reasoning_parser='', reasoning_parser_plugin='', enable_in_reasoning=False), observability_config=ObservabilityConfig(show_hidden_metrics_for_version=None, otlp_traces_endpoint=None, collect_detailed_traces=None, kv_cache_metrics=False, kv_cache_metrics_sample=0.01, cudagraph_metrics=False, enable_layerwise_nvtx_tracing=False, enable_mfu_metrics=False, enable_mm_processor_stats=False, enable_logging_iteration_details=False), seed=0, served_model_name=qwen, enable_prefix_caching=True, enable_chunked_prefill=True, pooler_config=None, compilation_config={'mode': <CompilationMode.VLLM_COMPILE: 3>, 'debug_dump_path': None, 'cache_dir': '', 'compile_cache_save_format': 'binary', 'backend': 'inductor', 'custom_ops': ['none'], 'splitting_ops': ['vllm::unified_attention', 'vllm::unified_attention_with_output', 'vllm::unified_mla_attention', 'vllm::unified_mla_attention_with_output', 'vllm::mamba_mixer2', 'vllm::mamba_mixer', 'vllm::short_conv', 'vllm::linear_attention', 'vllm::plamo2_mamba_mixer', 'vllm::gdn_attention_core', 'vllm::olmo_hybrid_gdn_full_forward', 'vllm::kda_attention', 'vllm::sparse_attn_indexer', 'vllm::rocm_aiter_sparse_attn_indexer', 'vllm::unified_kv_cache_update', 'vllm::unified_mla_kv_cache_update'], 'compile_mm_encoder': False, 'cudagraph_mm_encoder': False, 'encoder_cudagraph_token_budgets': [], 'encoder_cudagraph_max_images_per_batch': 0, 'compile_sizes': [], 'compile_ranges_endpoints': [2048], 'inductor_compile_config': {'enable_auto_functionalized_v2': False, 'size_asserts': False, 'alignment_asserts': False, 'scalar_asserts': False, 'combo_kernels': True, 'benchmark_combo_kernel': True}, 'inductor_passes': {}, 'cudagraph_mode': <CUDAGraphMode.FULL_AND_PIECEWISE: (2, 1)>, 'cudagraph_num_of_warmups': 1, 'cudagraph_capture_sizes': [1, 2, 4, 8, 16, 24, 32, 40, 48, 56, 64, 72, 80, 88, 96, 104, 112, 120, 128, 136, 144, 152, 160, 168, 176, 184, 192, 200, 208, 216, 224, 232, 240, 248, 256, 272, 288, 304, 320, 336, 352, 368, 384, 400, 416, 432, 448, 464, 480, 496, 512], 'cudagraph_copy_inputs': False, 'cudagraph_specialize_lora': True, 'use_inductor_graph_partition': False, 'pass_config': {'fuse_norm_quant': False, 'fuse_act_quant': False, 'fuse_attn_quant': False, 'enable_sp': False, 'fuse_gemm_comms': False, 'fuse_allreduce_rms': False}, 'max_cudagraph_capture_size': 512, 'dynamic_shapes_config': {'type': <DynamicShapesType.BACKED: 'backed'>, 'evaluate_guards': False, 'assume_32_bit_indexing': False}, 'local_cache_dir': None, 'fast_moe_cold_start': True, 'static_all_moe_layers': []}
(EngineCore pid=272) WARNING 04-16 11:02:32 [multiproc_executor.py:1014] Reducing Torch parallelism from 24 threads to 1 to avoid unnecessary CPU contention. Set OMP_NUM_THREADS in the external environment to tune this value as needed.
(EngineCore pid=272) INFO 04-16 11:02:32 [multiproc_executor.py:134] DP group leader: node_rank=0, node_rank_within_dp=0, master_addr=127.0.0.1, mq_connect_ip=10.0.10.64 (local), world_size=4, local_world_size=4
(Worker pid=375) INFO 04-16 11:02:40 [parallel_state.py:1400] world_size=4 rank=0 local_rank=0 distributed_init_method=tcp://127.0.0.1:58269 backend=nccl
(Worker pid=377) INFO 04-16 11:02:41 [parallel_state.py:1400] world_size=4 rank=2 local_rank=2 distributed_init_method=tcp://127.0.0.1:58269 backend=nccl
(Worker pid=378) INFO 04-16 11:02:41 [parallel_state.py:1400] world_size=4 rank=3 local_rank=3 distributed_init_method=tcp://127.0.0.1:58269 backend=nccl
(Worker pid=376) INFO 04-16 11:02:41 [parallel_state.py:1400] world_size=4 rank=1 local_rank=1 distributed_init_method=tcp://127.0.0.1:58269 backend=nccl
(Worker pid=378) <frozen importlib._bootstrap_external>:1301: FutureWarning: The cuda.cudart module is deprecated and will be removed in a future release, please switch to use the cuda.bindings.runtime module instead.
(Worker pid=378) <frozen importlib._bootstrap_external>:1301: FutureWarning: The cuda.nvrtc module is deprecated and will be removed in a future release, please switch to use the cuda.bindings.nvrtc module instead.
(Worker pid=377) <frozen importlib._bootstrap_external>:1301: FutureWarning: The cuda.cudart module is deprecated and will be removed in a future release, please switch to use the cuda.bindings.runtime module instead.
(Worker pid=376) <frozen importlib._bootstrap_external>:1301: FutureWarning: The cuda.cudart module is deprecated and will be removed in a future release, please switch to use the cuda.bindings.runtime module instead.
(Worker pid=375) <frozen importlib._bootstrap_external>:1301: FutureWarning: The cuda.cudart module is deprecated and will be removed in a future release, please switch to use the cuda.bindings.runtime module instead.
(Worker pid=377) <frozen importlib._bootstrap_external>:1301: FutureWarning: The cuda.nvrtc module is deprecated and will be removed in a future release, please switch to use the cuda.bindings.nvrtc module instead.
(Worker pid=376) <frozen importlib._bootstrap_external>:1301: FutureWarning: The cuda.nvrtc module is deprecated and will be removed in a future release, please switch to use the cuda.bindings.nvrtc module instead.
(Worker pid=375) <frozen importlib._bootstrap_external>:1301: FutureWarning: The cuda.nvrtc module is deprecated and will be removed in a future release, please switch to use the cuda.bindings.nvrtc module instead.
(Worker pid=375) INFO 04-16 11:02:41 [pynccl.py:111] vLLM is using nccl==2.27.5
(Worker pid=375) WARNING 04-16 11:02:42 [symm_mem.py:66] SymmMemCommunicator: Device capability 8.9 not supported, communicator is not available.
(Worker pid=376) WARNING 04-16 11:02:42 [symm_mem.py:66] SymmMemCommunicator: Device capability 8.9 not supported, communicator is not available.
(Worker pid=378) WARNING 04-16 11:02:42 [symm_mem.py:66] SymmMemCommunicator: Device capability 8.9 not supported, communicator is not available.
(Worker pid=377) WARNING 04-16 11:02:42 [symm_mem.py:66] SymmMemCommunicator: Device capability 8.9 not supported, communicator is not available.
(Worker pid=378) WARNING 04-16 11:02:42 [custom_all_reduce.py:154] Custom allreduce is disabled because it's not supported on more than two PCIe-only GPUs. To silence this warning, specify disable_custom_all_reduce=True explicitly.
(Worker pid=376) WARNING 04-16 11:02:42 [custom_all_reduce.py:154] Custom allreduce is disabled because it's not supported on more than two PCIe-only GPUs. To silence this warning, specify disable_custom_all_reduce=True explicitly.
(Worker pid=377) WARNING 04-16 11:02:42 [custom_all_reduce.py:154] Custom allreduce is disabled because it's not supported on more than two PCIe-only GPUs. To silence this warning, specify disable_custom_all_reduce=True explicitly.
(Worker pid=375) WARNING 04-16 11:02:42 [custom_all_reduce.py:154] Custom allreduce is disabled because it's not supported on more than two PCIe-only GPUs. To silence this warning, specify disable_custom_all_reduce=True explicitly.
(Worker pid=375) INFO 04-16 11:02:42 [parallel_state.py:1716] rank 0 in world size 4 is assigned as DP rank 0, PP rank 0, PCP rank 0, TP rank 0, EP rank N/A, EPLB rank N/A
(Worker_TP0 pid=375) INFO 04-16 11:02:43 [gpu_model_runner.py:4735] Starting to load model Qwen/Qwen2.5-72B-Instruct...
(Worker_TP0 pid=375) INFO 04-16 11:02:43 [cuda.py:334] Using FLASH_ATTN attention backend out of potential backends: ['FLASH_ATTN', 'FLASHINFER', 'TRITON_ATTN', 'FLEX_ATTENTION'].
(Worker_TP0 pid=375) INFO 04-16 11:02:43 [flash_attn.py:596] Using FlashAttention version 2
```

### vLLM 파라미터 ###
* --model                     사용모델
* --tensor-parallel-size      GPU 갯수
* --max-model-len             최대 시퀀스 길이
* --gpu-memory-utilization    GPU 메모리 상용률(90% 권장)
   - CUDA 커널 실행 오버헤드, Activation 임시 버퍼, Tensor 연산 중간 결과물, NCCL 통신 버퍼 (TP 사용시)

### vLLM 추론 최적화 ###
vLLM은 아래 세 가지 최적화를 기본 내장하고 있어 별도 설정 없이 자동 적용된다.

#### KV Cache 최적화 (PagedAttention) ####
Transformer는 토큰을 생성할 때마다 이전 토큰들의 Key/Value 텐서를 참조해야 한다. 이를 KV Cache라 하며, 시퀀스가 길어질수록 GPU 메모리를 많이 차지한다.
기존 방식은 요청마다 max-model-len 크기의 연속 메모리를 미리 할당했다. 실제로 10토큰만 생성해도 4096토큰분의 메모리를 점유하므로 낭비가 심하다.
vLLM의 PagedAttention은 OS의 가상 메모리 페이징에서 착안한 방식으로, KV Cache를 고정 크기 블록(페이지) 단위로 나누어 필요할 때만 할당한다.
```
기존 방식:
요청 A: [████████████████████░░░░░░░░░░░░] ←  max-model-len 토큰 할당, 실제 1200 토큰 사용
요청 B: [██████░░░░░░░░░░░░░░░░░░░░░░░░░░] ←  max-model-len 토큰 할당, 실제 400 토큰 사용
→ 메모리 낭비 심함

PagedAttention:
요청 A: [블록1][블록2][블록3] ← 필요한 만큼만 블록 할당
요청 B: [블록4] ← 필요한 만큼만 블록 할당
→ 남은 블록은 다른 요청이 사용 가능
```
이를 통해 동일 GPU 메모리에서 더 많은 요청을 동시에 처리할 수 있다. --gpu-memory-utilization과 --max-model-len 파라미터가 전체 KV Cache 풀 크기를 결정한다.

#### Continuous Batching ####
기존 Static Batching은 배치 안의 모든 요청이 완료될 때까지 기다린 후 다음 배치를 처리한다. 짧은 요청이 먼저 끝나도 긴 요청이 끝날 때까지 GPU가 유휴 상태가 된다.
vLLM은 매 토큰 생성 스텝마다 배치를 재구성하여 완료된 요청을 빼고 대기 중인 요청을 즉시 투입한다. 이를 통해 GPU 활용률과 전체 처리량(throughput)이 크게 향상된다.

#### Prefill/Decode 분리 ####
LLM 추론은 두 단계로 나뉜다.
* Prefill: 입력 프롬프트의 모든 토큰을 한 번에 처리하여 KV Cache를 생성하는 단계. 행렬 연산이 크고 GPU 연산(compute)이 병목이다.
* Decode: KV Cache를 참조하며 토큰을 하나씩 생성하는 단계. 연산량은 적지만 매 스텝마다 GPU 메모리를 읽어야 하므로 메모리 대역폭(memory bandwidth)이 병목이다.
두 단계의 리소스 특성이 다르기 때문에, 같은 GPU에서 Prefill과 Decode가 섞이면 서로 간섭이 발생한다. 긴 프롬프트의 Prefill이 실행되면 Decode 중인 요청의 TPOT(Time per Output Token)이 튀는 현상이 생긴다. vLLM은 내부 스케줄러에서 Prefill과 Decode의 우선순위를 조절하여 이 간섭을 최소화한다.

### 테스트 하기 ###
```bash
# 클러스터 내부에서 테스트 (임시 파드)
kubectl run test --rm -it --image=curlimages/curl -- \
  curl http://vllm-qwen-svc/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 50
  }'
```
또는
```bash
# 터미널 1: 포트 포워딩
kubectl port-forward svc/vllm-qwen-svc 8080:80

# 터미널 2: 테스트
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 50
  }'
```

### 성능 밴치마크 ###
```bash
kubectl get pods

# vLLM 벤치마크 (파드 안에서 실행)
kubectl exec -it <vllm-pod-name> -- python -m vllm.entrypoints.openai.api_server &

python -m vllm.entrypoints.openai.bench_serving \
  --backend openai \
  --base-url http://localhost:8000 \
  --model qwen \
  --num-prompts 100 \
  --request-rate 10
```

### Speculative Decoding 적용 ###
Speculative Decoding은 작은 모델(draft)이 먼저 여러 토큰을 추측 생성하고, 큰 모델(target)이 한 번에 검증하는 방식으로 추론 속도를 높이는 방식이다.

* Target 모델: Qwen2.5-27B (기존 배포 모델)
* Draft 모델: Qwen2.5-3B (같은 계열의 작은 모델, 추측 적중률이 높음)
기존 vllm-qwen.yaml 에서 args 부분만 수정한다.
```
args:
  - "--model=Qwen/Qwen2.5-Coder-27B-Instruct"
  - "--tensor-parallel-size=4"
  - "--max-model-len=4096"
  - "--gpu-memory-utilization=0.90"
  - "--speculative-model=Qwen/Qwen2.5-Coder-3B-Instruct"
  - "--num-speculative-tokens=5"
```

* 파라미터	설명
 * --speculative-model	추측 생성에 사용할 draft 모델
 * --num-speculative-tokens	draft 모델이 한 번에 추측할 토큰 수 (5가 일반적)
draft 모델(3B)은 target 모델(27B)과 같은 GPU 메모리에 함께 로드된다. 3B 모델은 약 6GB 정도 차지하므로 L40S 48GB × 4 구성에서 메모리 여유가 충분하다.

#### 성능 비교 벤치마크 ####
Speculative Decoding 적용 후 동일한 벤치마크를 실행하여 베이스라인과 비교한다.

```
kubectl exec -it <vllm-pod-name> -- \
  python -m vllm.entrypoints.openai.bench_serving \
    --backend openai \
    --base-url http://localhost:8000 \
    --model qwen \
    --num-prompts 100 \
    --request-rate 10
```
TTFT (Time to First Token), TPOT (Time per Output Token), Throughput (tokens/sec), Request Latency (p50/p99) 을 baseline 과 비교한다.
TPOT와 Throughput에서 가장 큰 차이가 나타난다. 일반적으로 1.5~2.5배 속도 향상을 기대할 수 있으며, 코드 생성처럼 정형화된 출력에서 효과가 더 크다.
num-speculative-tokens는 너무 높이면 draft 모델의 추측이 틀릴 확률이 올라가서 오히려 느려질수 있다. 5가 무난한 시작점이고, 벤치마크 결과 보면서 3~7 사이에서 조절한다.



## KV Cache / PagedAttention 튜닝 ##
#### KV Cache 튜닝 ####
```
vllm serve model \
  --gpu-memory-utilization 0.9    # GPU 메모리 중 KV cache에 할당할 비율 (기본 0.9)
  --max-model-len 4096            # 최대 시퀀스 길이 제한 → KV cache 크기 제한
  --block-size 16                 # PagedAttention 페이지 크기 (기본 16)
  --enable-prefix-caching         # 공통 프롬프트의 KV cache 재사용

gpu-memory-utilization 높이면 → 동시 요청 더 많이 수용, 대신 OOM 위험
max-model-len 줄이면 → KV cache 메모리 절약, 대신 긴 컨텍스트 불가
prefix-caching 켜면 → 시스템 프롬프트 등 공통 부분 재계산 안 함
```

#### Continuous Batching 튜닝 ####
```
vllm serve model \
  --max-num-seqs 256              # 동시에 배치에 넣을 최대 요청 수
  --max-num-batched-tokens 4096   # 한 iteration에 처리할 최대 토큰 수
  --enable-chunked-prefill        # 긴 prefill을 쪼개서 decode와 인터리빙
```
