### vLLM 기동 단계 ###





### 튜닝전 vLLM 기동 시간 - 193초 ###

```
2026-11-23T15:41:29.952313791Z (EngineCore pid=225) INFO 11-23 15:41:29 [model_runner.py:428] Model loading took 12.75 GiB memory and 12.762926 seconds
2026-11-23T15:43:08.549761612Z (EngineCore pid=225) INFO 11-23 15:43:08 [model_runner.py:1163] Graph capturing finished in 14 secs, took 0.52 GiB
2026-11-23T15:43:17.680269763Z (EngineCore pid=225) INFO 11-23 15:43:17 [model_runner.py:1163] Graph capturing finished in 7 secs, took 0.30 GiB
2026-11-23T15:43:18.971310602Z (EngineCore pid=225) INFO 11-23 15:43:18 [core.py:405] init engine (profile, create kv cache, warmup model) took 108.99 s (compilation: 54.72 s)
2026-11-23T15:43:22.393764308Z INFO:     Application startup complete.
```

### vLLM 최적화 ###

`1.1 CUDA 그래프 캡처 대상 줄이기 (21초 -> 3~5초 단축)`

기본적으로 vLLM은 다양한 동시 요청 수(배치 크기: 1, 2, 4, 8 ... 최대 512개)에 대해 그래프를 모두 미리 캡처합니다. 실제 서비스 트래픽에 맞춰 최대 캡처 크기를 낮추면 캡처 시간이 대폭 줄어듭니다.
```
vllm serve <모델명> --compilation-config '{"cudagraph_capture_sizes": [1, 2, 4, 8, 16, 32]}'
```

`1.2 torch.compile 시간 단축 하기 (55초 -> 5초)`
torch.compile은 현재 연결된 GPU 아키텍처(예: A100, L40S, H100 등)와 입력 형태에 맞춰 여러 개의 자잘한 GPU 연산(커널)을 하나로 합치고(Kernel Fusion) 최적화된 Triton/CUDA 코드를 즉석에서 빌드하는 작업으로, 작업결과는 수십 MB ~ 수백 MB (모델 크기와 무관하게 매우 작음) 이다. GPU에서 연산을 빠르게 돌리기 위한 컴파일된 커널 코드 (.so, .cubin 등) 이다.

최초 1회 빌드된 결과물을 디스크에 저장해 두면, 이후 서버를 껐다 켜거나 새 컨테이너를 띄울 때는 컴파일을 건너뛰고 바로 로드한다. VLLM_CACHE_ROOT와 TORCHINDUCTOR_CACHE_DIR 경로를 호스트 디스크나 EBS/EFS/S3 같은 영구 볼륨에 연결해 두면 된다. 첫 실행만 55초 걸리고, 두 번째 실행부터는 컴파일 시간이 수 초 수준으로 사라진다. S3 Express One Zone 같은 곳에 미리 캐시 폴더를 올려두고 컨테이너 시작 시 땡겨오는 방식도 많이 씁니다.


### 튜닝후 - 120초 ###
