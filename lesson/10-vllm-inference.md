## vLLM 인퍼런스 ##

### vLLM 배포하기 ###
[Qwen2.5-72B](https://huggingface.co/Qwen/Qwen2.5-72B-Instruct) 모델을 g6e.12xlarge (L40S 48GB * 4EA, TP=4) 설정으로 2개의 파드로 구성한다.  [vllm-qwen.yaml](https://raw.githubusercontent.com/gnosia93/eks-agentic-ai/refs/heads/main/code/yaml/vllm-qwen.yaml) 파일을 다운로드 받은 후 디플로이먼트를 생성한다.

> [!NOTE]
> TP 의 경우 NVLINK 가 필요하나, GPU 를 구할수 없어서, 이 예제에서는 g6e.12xlarge 인스턴스를 사용하도록 한다.
>

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

vllm 로그를 확인한다.
```bash
kubectl logs -f vllm-qwen-849cb97c7c-fcfnh
```
[결과]
```
(APIServer pid=1) INFO 04-16 11:16:06 [utils.py:299] 
(APIServer pid=1) INFO 04-16 11:16:06 [utils.py:299]        █     █     █▄   ▄█
(APIServer pid=1) INFO 04-16 11:16:06 [utils.py:299]  ▄▄ ▄█ █     █     █ ▀▄▀ █  version 0.19.0
(APIServer pid=1) INFO 04-16 11:16:06 [utils.py:299]   █▄█▀ █     █     █     █  model   Qwen/Qwen2.5-72B-Instruct
(APIServer pid=1) INFO 04-16 11:16:06 [utils.py:299]    ▀▀  ▀▀▀▀▀ ▀▀▀▀▀ ▀     ▀
(APIServer pid=1) INFO 04-16 11:16:06 [utils.py:299] 
(APIServer pid=1) INFO 04-16 11:16:06 [utils.py:233] non-default args: {'model': 'Qwen/Qwen2.5-72B-Instruct', 'max_model_len': 8192, 'served_model_name': ['qwen'], 'tensor_parallel_size': 4}
(APIServer pid=1) WARNING 04-16 11:16:06 [envs.py:1744] Unknown vLLM environment variable detected: VLLM_QWEN_SVC_SERVICE_PORT
(APIServer pid=1) WARNING 04-16 11:16:06 [envs.py:1744] Unknown vLLM environment variable detected: VLLM_QWEN_SVC_PORT
(APIServer pid=1) WARNING 04-16 11:16:06 [envs.py:1744] Unknown vLLM environment variable detected: VLLM_QWEN_SVC_PORT_80_TCP
(APIServer pid=1) WARNING 04-16 11:16:06 [envs.py:1744] Unknown vLLM environment variable detected: VLLM_QWEN_SVC_PORT_80_TCP_PROTO
(APIServer pid=1) WARNING 04-16 11:16:06 [envs.py:1744] Unknown vLLM environment variable detected: VLLM_QWEN_SVC_PORT_80_TCP_PORT
(APIServer pid=1) WARNING 04-16 11:16:06 [envs.py:1744] Unknown vLLM environment variable detected: VLLM_QWEN_SVC_PORT_80_TCP_ADDR
(APIServer pid=1) WARNING 04-16 11:16:06 [envs.py:1744] Unknown vLLM environment variable detected: VLLM_QWEN_SVC_SERVICE_HOST
(APIServer pid=1) INFO 04-16 11:16:17 [model.py:549] Resolved architecture: Qwen2ForCausalLM
(APIServer pid=1) INFO 04-16 11:16:17 [model.py:1678] Using max model len 8192
(APIServer pid=1) INFO 04-16 11:16:17 [vllm.py:790] Asynchronous scheduling is enabled.
(EngineCore pid=271) INFO 04-16 11:16:23 [core.py:105] Initializing a V1 LLM engine (v0.19.0) with config: model='Qwen/Qwen2.5-72B-Instruct', speculative_config=None, tokenizer='Qwen/Qwen2.5-72B-Instruct', skip_tokenizer_init=False, tokenizer_mode=auto, revision=None, tokenizer_revision=None, trust_remote_code=False, dtype=torch.bfloat16, max_seq_len=8192, download_dir=None, load_format=auto, tensor_parallel_size=4, pipeline_parallel_size=1, data_parallel_size=1, decode_context_parallel_size=1, dcp_comm_backend=ag_rs, disable_custom_all_reduce=False, quantization=None, enforce_eager=False, enable_return_routed_experts=False, kv_cache_dtype=auto, device_config=cuda, structured_outputs_config=StructuredOutputsConfig(backend='auto', disable_any_whitespace=False, disable_additional_properties=False, reasoning_parser='', reasoning_parser_plugin='', enable_in_reasoning=False), observability_config=ObservabilityConfig(show_hidden_metrics_for_version=None, otlp_traces_endpoint=None, collect_detailed_traces=None, kv_cache_metrics=False, kv_cache_metrics_sample=0.01, cudagraph_metrics=False, enable_layerwise_nvtx_tracing=False, enable_mfu_metrics=False, enable_mm_processor_stats=False, enable_logging_iteration_details=False), seed=0, served_model_name=qwen, enable_prefix_caching=True, enable_chunked_prefill=True, pooler_config=None, compilation_config={'mode': <CompilationMode.VLLM_COMPILE: 3>, 'debug_dump_path': None, 'cache_dir': '', 'compile_cache_save_format': 'binary', 'backend': 'inductor', 'custom_ops': ['none'], 'splitting_ops': ['vllm::unified_attention', 'vllm::unified_attention_with_output', 'vllm::unified_mla_attention', 'vllm::unified_mla_attention_with_output', 'vllm::mamba_mixer2', 'vllm::mamba_mixer', 'vllm::short_conv', 'vllm::linear_attention', 'vllm::plamo2_mamba_mixer', 'vllm::gdn_attention_core', 'vllm::olmo_hybrid_gdn_full_forward', 'vllm::kda_attention', 'vllm::sparse_attn_indexer', 'vllm::rocm_aiter_sparse_attn_indexer', 'vllm::unified_kv_cache_update', 'vllm::unified_mla_kv_cache_update'], 'compile_mm_encoder': False, 'cudagraph_mm_encoder': False, 'encoder_cudagraph_token_budgets': [], 'encoder_cudagraph_max_images_per_batch': 0, 'compile_sizes': [], 'compile_ranges_endpoints': [2048], 'inductor_compile_config': {'enable_auto_functionalized_v2': False, 'size_asserts': False, 'alignment_asserts': False, 'scalar_asserts': False, 'combo_kernels': True, 'benchmark_combo_kernel': True}, 'inductor_passes': {}, 'cudagraph_mode': <CUDAGraphMode.FULL_AND_PIECEWISE: (2, 1)>, 'cudagraph_num_of_warmups': 1, 'cudagraph_capture_sizes': [1, 2, 4, 8, 16, 24, 32, 40, 48, 56, 64, 72, 80, 88, 96, 104, 112, 120, 128, 136, 144, 152, 160, 168, 176, 184, 192, 200, 208, 216, 224, 232, 240, 248, 256, 272, 288, 304, 320, 336, 352, 368, 384, 400, 416, 432, 448, 464, 480, 496, 512], 'cudagraph_copy_inputs': False, 'cudagraph_specialize_lora': True, 'use_inductor_graph_partition': False, 'pass_config': {'fuse_norm_quant': False, 'fuse_act_quant': False, 'fuse_attn_quant': False, 'enable_sp': False, 'fuse_gemm_comms': False, 'fuse_allreduce_rms': False}, 'max_cudagraph_capture_size': 512, 'dynamic_shapes_config': {'type': <DynamicShapesType.BACKED: 'backed'>, 'evaluate_guards': False, 'assume_32_bit_indexing': False}, 'local_cache_dir': None, 'fast_moe_cold_start': True, 'static_all_moe_layers': []}
(EngineCore pid=271) WARNING 04-16 11:16:23 [multiproc_executor.py:1014] Reducing Torch parallelism from 24 threads to 1 to avoid unnecessary CPU contention. Set OMP_NUM_THREADS in the external environment to tune this value as needed.
(EngineCore pid=271) INFO 04-16 11:16:23 [multiproc_executor.py:134] DP group leader: node_rank=0, node_rank_within_dp=0, master_addr=127.0.0.1, mq_connect_ip=10.0.10.64 (local), world_size=4, local_world_size=4
(Worker pid=374) INFO 04-16 11:16:30 [parallel_state.py:1400] world_size=4 rank=0 local_rank=0 distributed_init_method=tcp://127.0.0.1:35187 backend=nccl
(Worker pid=376) INFO 04-16 11:16:30 [parallel_state.py:1400] world_size=4 rank=2 local_rank=2 distributed_init_method=tcp://127.0.0.1:35187 backend=nccl
(Worker pid=377) INFO 04-16 11:16:30 [parallel_state.py:1400] world_size=4 rank=3 local_rank=3 distributed_init_method=tcp://127.0.0.1:35187 backend=nccl
(Worker pid=375) INFO 04-16 11:16:30 [parallel_state.py:1400] world_size=4 rank=1 local_rank=1 distributed_init_method=tcp://127.0.0.1:35187 backend=nccl
(Worker pid=376) <frozen importlib._bootstrap_external>:1301: FutureWarning: The cuda.cudart module is deprecated and will be removed in a future release, please switch to use the cuda.bindings.runtime module instead.
(Worker pid=377) <frozen importlib._bootstrap_external>:1301: FutureWarning: The cuda.cudart module is deprecated and will be removed in a future release, please switch to use the cuda.bindings.runtime module instead.
(Worker pid=375) <frozen importlib._bootstrap_external>:1301: FutureWarning: The cuda.cudart module is deprecated and will be removed in a future release, please switch to use the cuda.bindings.runtime module instead.
(Worker pid=374) <frozen importlib._bootstrap_external>:1301: FutureWarning: The cuda.cudart module is deprecated and will be removed in a future release, please switch to use the cuda.bindings.runtime module instead.
(Worker pid=376) <frozen importlib._bootstrap_external>:1301: FutureWarning: The cuda.nvrtc module is deprecated and will be removed in a future release, please switch to use the cuda.bindings.nvrtc module instead.
(Worker pid=375) <frozen importlib._bootstrap_external>:1301: FutureWarning: The cuda.nvrtc module is deprecated and will be removed in a future release, please switch to use the cuda.bindings.nvrtc module instead.
(Worker pid=377) <frozen importlib._bootstrap_external>:1301: FutureWarning: The cuda.nvrtc module is deprecated and will be removed in a future release, please switch to use the cuda.bindings.nvrtc module instead.
(Worker pid=374) <frozen importlib._bootstrap_external>:1301: FutureWarning: The cuda.nvrtc module is deprecated and will be removed in a future release, please switch to use the cuda.bindings.nvrtc module instead.
(Worker pid=374) INFO 04-16 11:16:31 [pynccl.py:111] vLLM is using nccl==2.27.5
(Worker pid=374) WARNING 04-16 11:16:31 [symm_mem.py:66] SymmMemCommunicator: Device capability 8.9 not supported, communicator is not available.
(Worker pid=376) WARNING 04-16 11:16:31 [symm_mem.py:66] SymmMemCommunicator: Device capability 8.9 not supported, communicator is not available.
(Worker pid=375) WARNING 04-16 11:16:31 [symm_mem.py:66] SymmMemCommunicator: Device capability 8.9 not supported, communicator is not available.
(Worker pid=377) WARNING 04-16 11:16:31 [symm_mem.py:66] SymmMemCommunicator: Device capability 8.9 not supported, communicator is not available.
(Worker pid=375) WARNING 04-16 11:16:31 [custom_all_reduce.py:154] Custom allreduce is disabled because it's not supported on more than two PCIe-only GPUs. To silence this warning, specify disable_custom_all_reduce=True explicitly.
(Worker pid=374) WARNING 04-16 11:16:31 [custom_all_reduce.py:154] Custom allreduce is disabled because it's not supported on more than two PCIe-only GPUs. To silence this warning, specify disable_custom_all_reduce=True explicitly.
(Worker pid=376) WARNING 04-16 11:16:31 [custom_all_reduce.py:154] Custom allreduce is disabled because it's not supported on more than two PCIe-only GPUs. To silence this warning, specify disable_custom_all_reduce=True explicitly.
(Worker pid=377) WARNING 04-16 11:16:31 [custom_all_reduce.py:154] Custom allreduce is disabled because it's not supported on more than two PCIe-only GPUs. To silence this warning, specify disable_custom_all_reduce=True explicitly.
(Worker pid=374) INFO 04-16 11:16:31 [parallel_state.py:1716] rank 0 in world size 4 is assigned as DP rank 0, PP rank 0, PCP rank 0, TP rank 0, EP rank N/A, EPLB rank N/A
(Worker_TP0 pid=374) INFO 04-16 11:16:32 [gpu_model_runner.py:4735] Starting to load model Qwen/Qwen2.5-72B-Instruct...
(Worker_TP0 pid=374) INFO 04-16 11:16:32 [cuda.py:334] Using FLASH_ATTN attention backend out of potential backends: ['FLASH_ATTN', 'FLASHINFER', 'TRITON_ATTN', 'FLEX_ATTENTION'].
(Worker_TP0 pid=374) INFO 04-16 11:16:32 [flash_attn.py:596] Using FlashAttention version 2
(Worker_TP0 pid=374) INFO 04-16 11:17:43 [weight_utils.py:581] Time spent downloading weights for Qwen/Qwen2.5-72B-Instruct: 69.520342 seconds
Loading safetensors checkpoint shards:   0% Completed | 0/37 [00:00<?, ?it/s]
Loading safetensors checkpoint shards:   5% Completed | 2/37 [00:00<00:07,  4.75it/s]
Loading safetensors checkpoint shards:   8% Completed | 3/37 [00:00<00:08,  4.24it/s]
Loading safetensors checkpoint shards:  11% Completed | 4/37 [00:00<00:08,  4.11it/s]
Loading safetensors checkpoint shards:  14% Completed | 5/37 [00:01<00:08,  3.98it/s]
Loading safetensors checkpoint shards:  16% Completed | 6/37 [00:01<00:08,  3.54it/s]
Loading safetensors checkpoint shards:  19% Completed | 7/37 [00:01<00:08,  3.48it/s]
Loading safetensors checkpoint shards:  22% Completed | 8/37 [00:02<00:08,  3.52it/s]
Loading safetensors checkpoint shards:  24% Completed | 9/37 [00:02<00:07,  3.54it/s]
Loading safetensors checkpoint shards:  27% Completed | 10/37 [00:02<00:08,  3.28it/s]
Loading safetensors checkpoint shards:  30% Completed | 11/37 [00:03<00:07,  3.33it/s]
Loading safetensors checkpoint shards:  32% Completed | 12/37 [00:03<00:07,  3.42it/s]
Loading safetensors checkpoint shards:  35% Completed | 13/37 [00:03<00:06,  3.49it/s]
Loading safetensors checkpoint shards:  38% Completed | 14/37 [00:03<00:07,  3.27it/s]
Loading safetensors checkpoint shards:  41% Completed | 15/37 [00:04<00:06,  3.32it/s]
Loading safetensors checkpoint shards:  43% Completed | 16/37 [00:04<00:06,  3.41it/s]
Loading safetensors checkpoint shards:  46% Completed | 17/37 [00:04<00:05,  3.48it/s]
Loading safetensors checkpoint shards:  49% Completed | 18/37 [00:05<00:05,  3.27it/s]
Loading safetensors checkpoint shards:  51% Completed | 19/37 [00:05<00:05,  3.30it/s]
Loading safetensors checkpoint shards:  54% Completed | 20/37 [00:05<00:05,  3.39it/s]
Loading safetensors checkpoint shards:  57% Completed | 21/37 [00:05<00:04,  3.46it/s]
Loading safetensors checkpoint shards:  59% Completed | 22/37 [00:06<00:04,  3.23it/s]
Loading safetensors checkpoint shards:  62% Completed | 23/37 [00:06<00:04,  3.27it/s]
Loading safetensors checkpoint shards:  65% Completed | 24/37 [00:06<00:03,  3.37it/s]
Loading safetensors checkpoint shards:  68% Completed | 25/37 [00:07<00:03,  3.44it/s]
Loading safetensors checkpoint shards:  70% Completed | 26/37 [00:07<00:03,  3.25it/s]
Loading safetensors checkpoint shards:  73% Completed | 27/37 [00:07<00:03,  3.32it/s]
Loading safetensors checkpoint shards:  76% Completed | 28/37 [00:08<00:02,  3.45it/s]
Loading safetensors checkpoint shards:  78% Completed | 29/37 [00:08<00:02,  3.58it/s]
Loading safetensors checkpoint shards:  81% Completed | 30/37 [00:08<00:02,  3.39it/s]
Loading safetensors checkpoint shards:  84% Completed | 31/37 [00:08<00:01,  3.45it/s]
Loading safetensors checkpoint shards:  86% Completed | 32/37 [00:09<00:01,  3.56it/s]
Loading safetensors checkpoint shards:  89% Completed | 33/37 [00:09<00:01,  3.64it/s]
Loading safetensors checkpoint shards:  92% Completed | 34/37 [00:09<00:00,  3.42it/s]
Loading safetensors checkpoint shards:  95% Completed | 35/37 [00:10<00:00,  3.50it/s]
Loading safetensors checkpoint shards:  97% Completed | 36/37 [00:10<00:00,  3.61it/s]
Loading safetensors checkpoint shards: 100% Completed | 37/37 [00:10<00:00,  4.24it/s]
Loading safetensors checkpoint shards: 100% Completed | 37/37 [00:10<00:00,  3.53it/s]
(Worker_TP0 pid=374) 
(Worker_TP0 pid=374) INFO 04-16 11:17:54 [default_loader.py:384] Loading weights took 10.48 seconds
(Worker_TP0 pid=374) INFO 04-16 11:17:54 [gpu_model_runner.py:4820] Model loading took 33.98 GiB memory and 81.566250 seconds
(Worker_TP0 pid=374) INFO 04-16 11:18:12 [backends.py:1051] Using cache directory: /root/.cache/vllm/torch_compile_cache/439360e93b/rank_0_0/backbone for vLLM's torch.compile
(Worker_TP0 pid=374) INFO 04-16 11:18:12 [backends.py:1111] Dynamo bytecode transform time: 11.95 s
(Worker_TP0 pid=374) INFO 04-16 11:18:18 [backends.py:372] Cache the graph of compile range (1, 2048) for later use
(Worker_TP0 pid=374) INFO 04-16 11:18:24 [backends.py:390] Compiling a graph for compile range (1, 2048) takes 11.12 s
(Worker_TP0 pid=374) INFO 04-16 11:18:27 [decorators.py:640] saved AOT compiled function to /root/.cache/vllm/torch_compile_cache/torch_aot_compile/2b4bfa0090ed5f30588d2813601a92bfe08351e1490a0ccdefb0da8eed6b78fe/rank_0_0/model
(Worker_TP0 pid=374) INFO 04-16 11:18:27 [monitor.py:48] torch.compile took 27.66 s in total
(Worker_TP0 pid=374) INFO 04-16 11:18:31 [monitor.py:76] Initial profiling/warmup run took 3.28 s
(Worker_TP3 pid=377) INFO 04-16 11:18:37 [kv_cache_utils.py:829] Overriding num_gpu_blocks=0 with num_gpu_blocks_override=512
(Worker_TP3 pid=377) INFO 04-16 11:18:37 [gpu_model_runner.py:5876] Profiling CUDA graph memory: PIECEWISE=51 (largest=512), FULL=35 (largest=256)
(Worker_TP1 pid=375) INFO 04-16 11:18:37 [kv_cache_utils.py:829] Overriding num_gpu_blocks=0 with num_gpu_blocks_override=512
(Worker_TP1 pid=375) INFO 04-16 11:18:37 [gpu_model_runner.py:5876] Profiling CUDA graph memory: PIECEWISE=51 (largest=512), FULL=35 (largest=256)
(Worker_TP0 pid=374) INFO 04-16 11:18:37 [kv_cache_utils.py:829] Overriding num_gpu_blocks=0 with num_gpu_blocks_override=512
(Worker_TP0 pid=374) INFO 04-16 11:18:37 [gpu_model_runner.py:5876] Profiling CUDA graph memory: PIECEWISE=51 (largest=512), FULL=35 (largest=256)
(Worker_TP2 pid=376) INFO 04-16 11:18:38 [kv_cache_utils.py:829] Overriding num_gpu_blocks=0 with num_gpu_blocks_override=512
(Worker_TP2 pid=376) INFO 04-16 11:18:38 [gpu_model_runner.py:5876] Profiling CUDA graph memory: PIECEWISE=51 (largest=512), FULL=35 (largest=256)
(Worker_TP3 pid=377) INFO 04-16 11:18:41 [gpu_model_runner.py:5955] Estimated CUDA graph memory: 2.73 GiB total
(Worker_TP0 pid=374) INFO 04-16 11:18:41 [gpu_model_runner.py:5955] Estimated CUDA graph memory: 2.73 GiB total
(Worker_TP1 pid=375) INFO 04-16 11:18:41 [gpu_model_runner.py:5955] Estimated CUDA graph memory: 2.73 GiB total
(Worker_TP2 pid=376) INFO 04-16 11:18:41 [gpu_model_runner.py:5955] Estimated CUDA graph memory: 2.73 GiB total
(Worker_TP3 pid=377) INFO 04-16 11:18:41 [gpu_worker.py:470] In v0.19, CUDA graph memory profiling will be enabled by default (VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS=1), which more accurately accounts for CUDA graph memory during KV cache allocation. To try it now, set VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS=1 and increase --gpu-memory-utilization from 0.9000 to 0.9616 to maintain the same effective KV cache size.
(Worker_TP0 pid=374) INFO 04-16 11:18:41 [gpu_worker.py:436] Available KV cache memory: 5.11 GiB
(Worker_TP0 pid=374) INFO 04-16 11:18:41 [gpu_worker.py:470] In v0.19, CUDA graph memory profiling will be enabled by default (VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS=1), which more accurately accounts for CUDA graph memory during KV cache allocation. To try it now, set VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS=1 and increase --gpu-memory-utilization from 0.9000 to 0.9616 to maintain the same effective KV cache size.
(Worker_TP1 pid=375) INFO 04-16 11:18:41 [gpu_worker.py:470] In v0.19, CUDA graph memory profiling will be enabled by default (VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS=1), which more accurately accounts for CUDA graph memory during KV cache allocation. To try it now, set VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS=1 and increase --gpu-memory-utilization from 0.9000 to 0.9616 to maintain the same effective KV cache size.
(Worker_TP2 pid=376) INFO 04-16 11:18:41 [gpu_worker.py:470] In v0.19, CUDA graph memory profiling will be enabled by default (VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS=1), which more accurately accounts for CUDA graph memory during KV cache allocation. To try it now, set VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS=1 and increase --gpu-memory-utilization from 0.9000 to 0.9616 to maintain the same effective KV cache size.
(EngineCore pid=271) INFO 04-16 11:18:41 [kv_cache_utils.py:1319] GPU KV cache size: 67,024 tokens
(EngineCore pid=271) INFO 04-16 11:18:41 [kv_cache_utils.py:1324] Maximum concurrency for 8,192 tokens per request: 8.18x
Capturing CUDA graphs (mixed prefill-decode, PIECEWISE): 100%|██████████| 51/51 [00:15<00:00,  3.27it/s]
Capturing CUDA graphs (decode, FULL): 100%|██████████| 35/35 [00:07<00:00,  4.58it/s]
(Worker_TP1 pid=375) INFO 04-16 11:19:05 [gpu_worker.py:597] CUDA graph pool memory: 2.62 GiB (actual), 2.73 GiB (estimated), difference: 0.11 GiB (4.3%).
(Worker_TP0 pid=374) INFO 04-16 11:19:05 [gpu_model_runner.py:6046] Graph capturing finished in 24 secs, took 2.62 GiB
(Worker_TP0 pid=374) INFO 04-16 11:19:05 [gpu_worker.py:597] CUDA graph pool memory: 2.62 GiB (actual), 2.73 GiB (estimated), difference: 0.11 GiB (4.3%).
(Worker_TP3 pid=377) INFO 04-16 11:19:05 [gpu_worker.py:597] CUDA graph pool memory: 2.62 GiB (actual), 2.73 GiB (estimated), difference: 0.11 GiB (4.3%).
(Worker_TP2 pid=376) INFO 04-16 11:19:05 [gpu_worker.py:597] CUDA graph pool memory: 2.62 GiB (actual), 2.73 GiB (estimated), difference: 0.11 GiB (4.3%).
(EngineCore pid=271) INFO 04-16 11:19:05 [core.py:283] init engine (profile, create kv cache, warmup model) took 66.12 seconds
(EngineCore pid=271) INFO 04-16 11:19:08 [vllm.py:790] Asynchronous scheduling is enabled.
(APIServer pid=1) INFO 04-16 11:19:08 [api_server.py:590] Supported tasks: ['generate']
(APIServer pid=1) WARNING 04-16 11:19:10 [model.py:1435] Default vLLM sampling parameters have been overridden by the model's `generation_config.json`: `{'repetition_penalty': 1.05, 'temperature': 0.7, 'top_k': 20, 'top_p': 0.8}`. If this is not intended, please relaunch vLLM instance with `--generation-config vllm`.
(APIServer pid=1) INFO 04-16 11:19:13 [hf.py:314] Detected the chat template content format to be 'string'. You can set `--chat-template-content-format` to override this.
(APIServer pid=1) INFO 04-16 11:19:13 [api_server.py:594] Starting vLLM server on http://0.0.0.0:8000
(APIServer pid=1) INFO 04-16 11:19:13 [launcher.py:37] Available routes are:
(APIServer pid=1) INFO 04-16 11:19:13 [launcher.py:46] Route: /openapi.json, Methods: HEAD, GET
(APIServer pid=1) INFO 04-16 11:19:13 [launcher.py:46] Route: /docs, Methods: HEAD, GET
(APIServer pid=1) INFO 04-16 11:19:13 [launcher.py:46] Route: /docs/oauth2-redirect, Methods: HEAD, GET
(APIServer pid=1) INFO 04-16 11:19:13 [launcher.py:46] Route: /redoc, Methods: HEAD, GET
(APIServer pid=1) INFO 04-16 11:19:13 [launcher.py:46] Route: /tokenize, Methods: POST
(APIServer pid=1) INFO 04-16 11:19:13 [launcher.py:46] Route: /detokenize, Methods: POST
(APIServer pid=1) INFO 04-16 11:19:13 [launcher.py:46] Route: /load, Methods: GET
(APIServer pid=1) INFO 04-16 11:19:13 [launcher.py:46] Route: /version, Methods: GET
(APIServer pid=1) INFO 04-16 11:19:13 [launcher.py:46] Route: /health, Methods: GET
(APIServer pid=1) INFO 04-16 11:19:13 [launcher.py:46] Route: /metrics, Methods: GET
(APIServer pid=1) INFO 04-16 11:19:13 [launcher.py:46] Route: /v1/models, Methods: GET
(APIServer pid=1) INFO 04-16 11:19:13 [launcher.py:46] Route: /ping, Methods: GET
(APIServer pid=1) INFO 04-16 11:19:13 [launcher.py:46] Route: /ping, Methods: POST
(APIServer pid=1) INFO 04-16 11:19:13 [launcher.py:46] Route: /invocations, Methods: POST
(APIServer pid=1) INFO 04-16 11:19:13 [launcher.py:46] Route: /v1/chat/completions, Methods: POST
(APIServer pid=1) INFO 04-16 11:19:13 [launcher.py:46] Route: /v1/chat/completions/batch, Methods: POST
(APIServer pid=1) INFO 04-16 11:19:13 [launcher.py:46] Route: /v1/responses, Methods: POST
(APIServer pid=1) INFO 04-16 11:19:13 [launcher.py:46] Route: /v1/responses/{response_id}, Methods: GET
(APIServer pid=1) INFO 04-16 11:19:13 [launcher.py:46] Route: /v1/responses/{response_id}/cancel, Methods: POST
(APIServer pid=1) INFO 04-16 11:19:13 [launcher.py:46] Route: /v1/completions, Methods: POST
(APIServer pid=1) INFO 04-16 11:19:13 [launcher.py:46] Route: /v1/messages, Methods: POST
(APIServer pid=1) INFO 04-16 11:19:13 [launcher.py:46] Route: /v1/messages/count_tokens, Methods: POST
(APIServer pid=1) INFO 04-16 11:19:13 [launcher.py:46] Route: /inference/v1/generate, Methods: POST
(APIServer pid=1) INFO 04-16 11:19:13 [launcher.py:46] Route: /scale_elastic_ep, Methods: POST
(APIServer pid=1) INFO 04-16 11:19:13 [launcher.py:46] Route: /is_scaling_elastic_ep, Methods: POST
(APIServer pid=1) INFO 04-16 11:19:13 [launcher.py:46] Route: /v1/chat/completions/render, Methods: POST
(APIServer pid=1) INFO 04-16 11:19:13 [launcher.py:46] Route: /v1/completions/render, Methods: POST
(APIServer pid=1) INFO:     Started server process [1]
(APIServer pid=1) INFO:     Waiting for application startup.
(APIServer pid=1) INFO:     Application startup complete.
```
* Time spent downloading weights: 69.52 seconds — 모델 다운로드 약 70초
* Model loading took 33.98 GiB memory and 81.57 seconds — GPU당 약 34GB 사용, 로딩 81초
* Available KV cache memory: 5.11 GiB — GPU당 KV cache로 약 5GB 남음
* GPU KV cache size: 67,024 tokens — KV cache에 약 67K 토큰 저장 가능
* Maximum concurrency for 8,192 tokens per request: 8.18x — max-model-len 8192 기준 동시 약 8개 요청 처리 가능


### vLLM 컨테이너 스팩 ###
```
...
containers:
  - name: vllm
    image: vllm/vllm-openai:latest
    command: ["python3", "-m", "vllm.entrypoints.openai.api_server"]
    args:
      - --model=Qwen/Qwen2.5-72B-Instruct           # fp16 사용시 144GB Weight 메모리 필요
      - --tensor-parallel-size=4                    # g6e.12xlarge 는 GPU 48GB 4장 -> 총 192GB
      - --max-model-len=8192
      - --gpu-memory-utilization=0.90
      - --port=8000
      - --served-model-name=qwen
    ports:
      - containerPort: 8000
    resources:
      limits:
        nvidia.com/gpu: "4"
      requests:
        nvidia.com/gpu: "4"
    volumeMounts:
      - name: shm
        mountPath: /dev/shm
      - name: model-cache
        mountPath: /root/.cache/huggingface
```
* --model                     사용모델
* --tensor-parallel-size      GPU 갯수
* --max-model-len             최대 시퀀스 길이
* --gpu-memory-utilization    GPU 메모리 상용률(90% 권장) - vLLM이 각 GPU 메모리의 90%까지 사용하겠다는 설정
   - CUDA 커널 실행 오버헤드, Activation 임시 버퍼, Tensor 연산 중간 결과물, NCCL 통신 버퍼 (TP 사용시)


### 테스트 ###
```
kubectl port-forward svc/vllm-qwen-svc 8080:80 --address=0.0.0.0 &

curl -s http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen","messages":[{"role":"user","content":"안녕!"}],"max_tokens":50}'
```
[결과]
```
Handling connection for 8080
{"id":"chatcmpl-9d34d7a96464f38f","object":"chat.completion","created":1776338760,"model":"qwen","choices":[{"index":0,"message":{"role":"assistant","content":"안녕하세요! 어떻게 도와드릴까요?","refusal":null,"annotations":null,"audio":null,"function_call":null,"tool_calls":[],"reasoning":null},"logprobs":null,"finish_reason":"stop","stop_reason":null,"token_ids":null}],"service_tier":null,"system_fingerprint":null,"usage":{"prompt_tokens":32,"total_tokens":44,"completion_tokens":12,"prompt_tokens_details":null},"prompt_logprobs":null,"prompt_token_ids":null,"kv_transfer_params":null}
```

## vLLM 추론 최적화 ##
vLLM은 아래 세 가지 최적화를 기본 내장하고 있어 별도 설정 없이 자동 적용된다.

#### 1. KV Cache 최적화 (PagedAttention) ####
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

#### 2. Continuous Batching ####
기존 Static Batching은 배치 안의 모든 요청이 완료될 때까지 기다린 후 다음 배치를 처리한다. 짧은 요청이 먼저 끝나도 긴 요청이 끝날 때까지 GPU가 유휴 상태가 된다.
vLLM은 매 토큰 생성 스텝마다 배치를 재구성하여 완료된 요청을 빼고 대기 중인 요청을 즉시 투입한다. 이를 통해 GPU 활용률과 전체 처리량(throughput)이 크게 향상된다.

#### 3. Prefix Caching ####
LLM API 호출 시 시스템 프롬프트나 few-shot 예시처럼 여러 요청에서 반복되는 앞부분(prefix)이 있다. 이 prefix에 대한 KV Cache를 한 번 계산해두고 재사용하면, 매 요청마다 같은 계산을 반복하지 않아도 된다.
vLLM 0.19.0부터 기본으로 활성화(enable_prefix_caching=True)되어 있다. 해당 설정을 끄기 위해서는 --enable-prefix-caching=False 파라미터를 사용한다.
이 설정은 다음과 같은 경우에 유리하다.
* 긴 시스템 프롬프트를 공유하는 API 서비스
* Few-shot 예시가 동일한 반복 요청
* RAG에서 동일 문서 컨텍스트를 여러 질문에 사용하는 경우
* 멀티턴 대화에서 이전 대화 히스토리가 공통인 경우

## vLLM 튜닝 ##
### 1. KV Cache 튜닝 ###
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

### 2. Continuous Batching 튜닝 ###
```
vllm serve model \
  --max-num-seqs 256              # 동시에 배치에 넣을 최대 요청 수
  --max-num-batched-tokens 4096   # 한 iteration에 처리할 최대 토큰 수
  --enable-chunked-prefill        # 긴 prefill을 쪼개서 decode와 인터리빙
```







