### 부하를 걸어 확인하기 ###

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





## 레퍼런스 ##

* [KEDA 이벤트 기반 오토스케일링 도입](https://gnobaaaaar.tistory.com/150) 
