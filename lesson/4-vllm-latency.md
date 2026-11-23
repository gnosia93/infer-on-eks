## 모델 레이턴시 측정 ##

vLLM 서비스는 ClusterIP 타입이라 클러스터 외부에서는 접속할 수 없다. 그래서 클러스터 안에 벤치마크 파드를 띄우고, 그 파드에서 서비스 DNS(`gemma4-12b-vllm.llm-serving.svc.cluster.local:8000`)로 직접 요청을 보낸다. 도구는 vLLM에 들어 있는 `vllm bench serve`를 쓴다. 서버와 같은 이미지에 포함돼 있어 따로 설치할 것이 없고, TTFT·TPOT·ITL·E2E 지연을 백분위수로 보여 준다.

`kubectl port-forward`로도 접속은 된다. 하지만 요청이 API 서버와 kubelet을 거치는 터널로 전달되므로 지연이 더해지고, 동시 요청이 많아지면 터널이 먼저 병목이 된다. 응답이 오는지 확인하는 용도로만 쓰는 게 좋다.

### 1. 벤치마크 파드 실행 ###

동시 요청 수를 1에서 64까지 늘려 가며 차례로 측정하는 파드를 만든다. 측정이 끝나도 결과 파일을 꺼낼 수 있게 파드는 계속 떠 있다. 스크립트 안의 `${...}`가 로컬 셸에서 치환되지 않도록 heredoc을 `<<'EOF'`로 감쌌다.

```
kubectl apply -f - <<'EOF'
apiVersion: v1
kind: Pod
metadata:
  name: vllm-bench
  namespace: llm-serving
spec:
  restartPolicy: Never
  containers:
    - name: bench
      image: vllm/vllm-openai:v0.33.0            # 서버와 같은 이미지 (vllm bench serve 포함)
      command: ["bash", "-c"]
      args:
        - |
          mkdir -p /tmp/results
          for C in ${CONCURRENCY}; do
            N=$(( C * 10 > 50 ? C * 10 : 50 ))     # 요청 수: 동시성 x 10, 최소 50
            echo "===== concurrency=${C} prompts=${N} ====="
            vllm bench serve \
              --backend openai-chat \
              --endpoint /v1/chat/completions \
              --base-url "${TARGET_URL}" \
              --model gemma-4-12b \
              --tokenizer RedHatAI/gemma-4-12B-it-FP8-Dynamic \
              --dataset-name random \
              --random-input-len "${ISL}" \
              --random-output-len "${OSL}" \
              --ignore-eos \
              --max-concurrency "${C}" \
              --num-prompts "${N}" \
              --num-warmups 3 \
              --seed "$(date +%s)" \
              --percentile-metrics ttft,tpot,itl,e2el \
              --metric-percentiles 50,90,99 \
              --disable-tqdm \
              --save-result --result-dir /tmp/results --result-filename "c${C}.json"
          done
          echo "===== done ====="
          sleep infinity                             # kubectl cp로 결과를 꺼낼 때까지 유지
      env:
        - name: TARGET_URL
          value: http://gemma4-12b-vllm.llm-serving.svc.cluster.local:8000
        - name: ISL                                  # 요청당 입력 토큰 수
          value: "1024"
        - name: OSL                                  # 요청당 출력 토큰 수
          value: "256"
        - name: CONCURRENCY                          # 측정할 동시 요청 수
          value: "1 2 4 8 16 32 64"
        - name: HF_HOME                              # 토크나이저 캐시 위치
          value: /tmp/hf
        - name: PYTHONUNBUFFERED                     # kubectl logs에 결과가 바로 보이게
          value: "1"
      resources:
        requests:
          cpu: "2"
          memory: 4Gi
        limits:
          memory: 4Gi
EOF
```

- **프롬프트:** 랜덤 토큰으로 만든다. `--ignore-eos`로 출력 길이를 `OSL`에 고정해야 실행끼리 비교할 수 있다. Hugging Face에서는 토크나이저 파일만 받는다.
- **seed:** seed가 같으면 같은 프롬프트가 만들어진다. 기본값(0)을 그대로 쓰면 앞에서 보낸 프롬프트가 다시 나갈 수 있다. 서버에 `--enable-prefix-caching`이 켜져 있어서 이런 요청은 캐시에 적중하고, TTFT가 실제보다 낮게 나온다. 그래서 단계마다 `$(date +%s)`로 seed를 바꾼다.

### 2. 진행 확인과 결과 정리 ###

```
kubectl wait -n llm-serving --for=condition=Ready pod/vllm-bench --timeout=10m
kubectl logs -n llm-serving -f vllm-bench
```

동시성마다 `Serving Benchmark Result` 표가 출력된다. `===== done =====`이 보이면 결과 JSON을 꺼내서 한 표로 모은다. 시간 단위는 ms다.

```
kubectl cp llm-serving/vllm-bench:/tmp/results ./bench-results

jq -rs '
  sort_by(.max_concurrency)
  | (["conc","fail","req/s","out_tok/s","TTFT_p50","TTFT_p99","TPOT_p50","TPOT_p99","ITL_p99","E2E_p50","E2E_p99"] | @tsv),
    (.[] | [.max_concurrency, .failed,
            (.request_throughput * 100 | round / 100),
            (.output_throughput | round),
            (.median_ttft_ms | round), (.p99_ttft_ms | round),
            (.median_tpot_ms * 10 | round / 10), (.p99_tpot_ms * 10 | round / 10),
            (.p99_itl_ms * 10 | round / 10),
            (.median_e2el_ms | round), (.p99_e2el_ms | round)] | @tsv)
' bench-results/c*.json | column -t
```

`fail`이 0이 아니면 vLLM 서버 로그(`kubectl logs -n llm-serving deploy/gemma4-12b-vllm`)를 확인한다. 요청별 에러 메시지가 필요하면 `--save-detailed`를 추가해 다시 돌린다. 에러 메시지는 결과 JSON의 `errors` 필드에 남는다.

### 3. 결과 읽는 법 ###

| 지표 | 의미 | 해석 |
|---|---|---|
| TTFT (Time To First Token) | 요청을 보낸 뒤 첫 토큰을 받을 때까지의 시간 | 큐 대기와 프롬프트 처리(prefill) 시간이 합쳐진 값이다. 입력이 길수록, 동시 요청이 많을수록 커진다. |
| TPOT (Time Per Output Token) | 첫 토큰 이후 토큰 하나당 평균 시간 | 사용자가 체감하는 스트리밍 속도다. 1000 / TPOT(ms)가 초당 토큰 수다. |
| ITL (Inter-Token Latency) | 연속한 두 토큰 사이의 간격 | p99가 TPOT보다 크게 튀면 다른 요청의 prefill이 같은 스텝에 끼어들어 토큰 간격이 잠깐씩 벌어진다는 뜻이다. |
| E2EL (End-to-End Latency) | 요청 하나가 끝날 때까지 걸린 전체 시간 | 대략 TTFT + TPOT x (출력 토큰 수 - 1)이다. |

동시성 1의 결과가 이 GPU에서 낼 수 있는 최저 지연이다. 디코딩은 토큰을 하나 만들 때마다 모델 가중치 전체를 GPU 메모리에서 읽는다. 가중치는 12.75GiB(기동 로그의 `Model loading took` 값)이고 L40S의 메모리 대역폭은 864GB/s이므로, TPOT의 이론 하한은 약 16ms다. 실제로는 스펙 대역폭을 다 쓰지 못하고 KV 캐시도 함께 읽으므로 측정값은 이보다 크게 나온다.

동시성을 올리면 여러 요청이 한 스텝에 묶여 처리되고, 가중치는 그 스텝에서 한 번만 읽는다. 그래서 처음에는 TPOT가 조금만 늘고 처리량(`out_tok/s`)은 크게 늘어난다. 어느 지점을 넘으면 TTFT와 TPOT가 가파르게 커진다.

목표 SLO(예: TTFT p99 1초, TPOT p99 50ms)를 지키는 가장 큰 동시성이 파드 하나가 감당할 수 있는 양이고, 나중에 오토스케일링 기준으로 쓰면 된다. 스크립트에 `--goodput ttft:1000 tpot:50`을 추가하면 SLO를 지킨 요청만 센 처리량(`Request goodput (req/s)`)도 함께 출력된다.

### 4. 조건을 바꿔 다시 측정할 때 ###

- **길이 바꾸기:** 파드 스펙은 만든 뒤에 수정할 수 없다. 결과를 `kubectl cp`로 꺼낸 다음 `kubectl delete pod vllm-bench -n llm-serving`으로 지우고, `ISL`, `OSL`, `CONCURRENCY` 값을 바꿔 다시 apply 한다. 결과는 조건마다 다른 디렉터리로 꺼낸다(예: `./bench-results-4096-512`). TTFT는 입력 길이에 따라 크게 달라지므로 실제 트래픽의 길이에 맞춰 측정해야 한다(예: 채팅 1024/256, RAG 4096/512).
- **도착 방식:** 위 측정은 동시 요청 수를 고정하는 방식이다. 초당 요청 수 기준으로 보려면 `--max-concurrency` 대신 `--request-rate`(예: `--request-rate 2`)를 준다. 그러면 요청이 포아송 분포로 도착한다. 이때 결과 JSON의 `max_concurrency`는 null이 되므로 요약 jq는 `.request_rate` 기준으로 바꾼다.
- **프록시 추가 후:** 나중에 LiteLLM이나 ALB를 앞에 붙이면 `TARGET_URL`을 바꿔서 같은 측정을 한다. 프록시에 API 키를 걸었다면 파드 env에 `OPENAI_API_KEY`를 넣는다. `vllm bench serve`가 이 값을 `Authorization: Bearer` 헤더로 보낸다. 프록시에 등록한 모델 이름이 다르면 `--model`도 바꾼다. 이번 결과와의 차이가 프록시 계층이 더한 지연이다.
- **정리:** 측정이 끝나면 `kubectl delete pod vllm-bench -n llm-serving`으로 파드를 지운다.

### 5. 주의할 점 ###
여기서 Ready는 벤치마크가 끝났다는 뜻이 아닙니다. 컨테이너가 시작됐다는 뜻이다.

* vllm-bench 파드에는 readinessProbe가 없다. 그래서 컨테이너가 실행되자마자 Ready가 된다.
* vLLM 서버 파드는 다르다. readinessProbe로 /health를 확인하므로 모델 로딩이 끝나야 Ready가 된다.
벤치마크가 끝났는지는 로그에 ===== done =====이 찍혔는지로 확인한다.

타임아웃이 나면 kubectl describe pod vllm-bench -n llm-serving을 실행해 Events에서 원인을 찾는다.

* 아직 Pulling 중일 때: 이미지를 받는 중이니 같은 kubectl wait 명령을 다시 실행한다.
* ErrImagePull, ImagePullBackOff, FailedScheduling일 때: 기다려도 해결되지 않는다. 이미지 받기 실패나 노드 자원 부족 같은 원인을 먼저 고쳐야 한다.

## 벤치 마크 결과 ##
![](https://github.com/gnosia93/infer-on-eks/blob/main/images/streaming-latency.png)

## 참고자료 ##

* [vLLM, vllm bench serve CLI](https://docs.vllm.ai/en/stable/cli/bench/serve/)
* [vLLM v0.33.0, vllm/benchmarks/serve.py](https://github.com/vllm-project/vllm/blob/v0.33.0/vllm/benchmarks/serve.py)
* [NVIDIA L40S 사양](https://www.nvidia.com/en-us/data-center/l40s/)

