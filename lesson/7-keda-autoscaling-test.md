### 부하 생성하기 ###

vllm bench serve는 연결을 재사용하므로, 레플리카가 늘어도 이미 연결된 기존 파드로만 요청을 보냅니다. 그래서 여기서는 요청마다 새 연결을 여는 curl로 부하를 겁니다.

```
kubectl apply -f - <<'EOF'
apiVersion: v1
kind: Pod
metadata:
  name: vllm-load
  namespace: llm-serving
spec:
  restartPolicy: Never
  containers:
    - name: load
      image: curlimages/curl:8.23.0
      command: ["sh", "-c"]
      args:
        - |
          END=$(( $(date +%s) + DURATION ))
          for i in $(seq "$CONCURRENCY"); do
            while [ "$(date +%s)" -lt "$END" ]; do
              curl -sSf -o /dev/null --max-time 120 "$URL" \
                -H 'Content-Type: application/json' \
                -d "{\"model\":\"gemma-4-12b\",\"max_tokens\":256,\"ignore_eos\":true,\"messages\":[{\"role\":\"user\",\"content\":\"[$i-$RANDOM] Explain Kubernetes autoscaling in detail.\"}]}" \
                || sleep 1
            done &
          done
          wait
          echo "===== done ====="
      env:
        - name: URL
          value: http://gemma4-12b-vllm.llm-serving.svc.cluster.local:8000/v1/chat/completions
        - name: CONCURRENCY          # 동시에 유지할 요청 수 (12 → 레플리카 2, 24 → 4)
          value: "12"
        - name: DURATION             # 부하를 거는 시간 (초)
          value: "900"
      resources:
        requests:
          cpu: 200m
          memory: 64Mi
        limits:
          memory: 128Mi
EOF
```
이 파드는 요청 12개를 계속 동시에 보냅니다. 그래서 전체 동시 요청 수가 12 근처에 머물고 목표 레플리카는 ceil(12 ÷ 6) = 2가 됩니다. CONCURRENCY를 24로 바꾸면 4까지 늘어납니다.

### 오브젝트 확인하기 ###

```
# 터미널 1: HPA 지표와 레플리카
kubectl get hpa keda-hpa-gemma4-12b-vllm -n llm-serving -w

# 터미널 2: vLLM 파드
kubectl get pods -n llm-serving -l app.kubernetes.io/name=gemma4-12b-vllm -w

# 터미널 3: GPU 노드
kubectl get nodeclaims -w
```

![](https://github.com/gnosia93/infer-on-eks/blob/main/images/keda-autoscaling-timeline.jpg)


### Grafana로 보기 ###

```
kubectl get secret grafana-admin -n monitoring -o jsonpath='{.data.admin-password}' | base64 -d; echo
kubectl -n monitoring port-forward svc/kube-prometheus-stack-grafana 3000:80
```
브라우저에서 3000 포트로 접속해 admin 계정으로 로그인합니다. 원격 VS Code 서버에서 실행했다면 VS Code의 포트 포워딩으로 엽니다. Explore에서 아래 쿼리로 패널을 만듭니다.


| 패널 | PromQL |
| :--- | :--- |
| 파드별 처리 중 요청 | `sum by (pod) (vllm:num_requests_running{namespace="llm-serving"})` |
| 대기 요청 | `sum(vllm:num_requests_waiting{namespace="llm-serving"})` |
| 파드별 KV 캐시 사용률 | `vllm:kv_cache_usage_perc{namespace="llm-serving"}` |
| HPA 목표 레플리카 | `kube_horizontalpodautoscaler_status_desired_replicas{namespace="llm-serving"}` |
| HPA 현재 레플리카 | `kube_horizontalpodautoscaler_status_current_replicas{namespace="llm-serving"}` |
| TTFT p99 | `histogram_quantile(0.99, sum by (le) (rate(vllm:time_to_first_token_seconds_bucket{namespace="llm-serving"}[1m])))` |









## 레퍼런스 ##

* [KEDA 이벤트 기반 오토스케일링 도입](https://gnobaaaaar.tistory.com/150) 
