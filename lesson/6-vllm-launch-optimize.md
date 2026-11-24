### 튜닝전 vLLM 기동 시간 - 193초 ###

```
2026-11-23T15:41:29.952313791Z (EngineCore pid=225) INFO 11-23 15:41:29 [model_runner.py:428] Model loading took 12.75 GiB memory and 12.762926 seconds
2026-11-23T15:43:08.549761612Z (EngineCore pid=225) INFO 11-23 15:43:08 [model_runner.py:1163] Graph capturing finished in 14 secs, took 0.52 GiB
2026-11-23T15:43:17.680269763Z (EngineCore pid=225) INFO 11-23 15:43:17 [model_runner.py:1163] Graph capturing finished in 7 secs, took 0.30 GiB
2026-11-23T15:43:18.971310602Z (EngineCore pid=225) INFO 11-23 15:43:18 [core.py:405] init engine (profile, create kv cache, warmup model) took 108.99 s (compilation: 54.72 s)
2026-11-23T15:43:22.393764308Z INFO:     Application startup complete.
```


### 튜닝후 ###
