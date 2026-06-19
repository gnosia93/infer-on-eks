### LWS 설치 ###
```
# 최신 릴리스 버전 확인 후 사용 (예: v0.7.0)
VERSION=v0.7.0
kubectl apply --server-side -f \
  https://github.com/kubernetes-sigs/lws/releases/download/${VERSION}/manifests.yaml

kubectl -n lws-system rollout status deploy/lws-controller-manager
```

### 1. HF 토큰 시크릿 (게이트 모델용) ###
```
kubectl create namespace llm
kubectl -n llm create secret generic hf-token \
  --from-literal=token="<YOUR_HF_TOKEN>"
```

### 2. LeaderWorkerSet 매니페스트 (현재: 1B / Graviton CPU) ###
```
cat <<EOF > lws-vllm-cpu.yaml
apiVersion: leaderworkerset.x-k8s.io/v1
kind: LeaderWorkerSet
metadata:
  name: vllm-1b
  namespace: llm
spec:
  replicas: 1                          # 모델 서버 그룹 수
  leaderWorkerTemplate:
    size: 2                            # 그룹당 파드 수 = 리더1 + 워커1 (요청하신 2파드)
    restartPolicy: RecreateGroupOnPodRestart
    leaderTemplate:
      metadata:
        labels:
          role: leader
      spec:
        nodeSelector:
          kubernetes.io/arch: arm64    # Graviton 노드
          workload: llm-inference
        containers:
          - name: vllm-leader
            image: <ACCOUNT>.dkr.ecr.ap-northeast-2.amazonaws.com/vllm-cpu-arm64:latest
            env:
              - name: HUGGING_FACE_HUB_TOKEN
                valueFrom:
                  secretKeyRef: { name: hf-token, key: token }
              - name: MODEL_ID
                value: "meta-llama/Llama-3.2-1B-Instruct"
              - name: RAY_PORT
                value: "6379"
            command: ["/bin/bash", "-c"]
            args:
              - |
                set -e
                # 1) Ray 헤드 기동
                ray start --head --port=${RAY_PORT} --disable-usage-stats
                # 2) 그룹 내 전체 파드(=size)가 붙을 때까지 대기
                until [ "$(ray status 2>/dev/null | grep -c node_)" -ge "${LWS_GROUP_SIZE}" ]; do
                  echo "waiting for ray workers..."; sleep 5
                done
                # 3) vLLM 서빙 (CPU, 2파드에 파이프라인 분할)
                vllm serve "${MODEL_ID}" \
                  --host 0.0.0.0 --port 8080 \
                  --device cpu \
                  --dtype bfloat16 \
                  --pipeline-parallel-size 2 \
                  --tensor-parallel-size 1 \
                  --max-model-len 4096
            ports:
              - containerPort: 8080
            resources:
              requests: { cpu: "6", memory: "12Gi" }
              limits:   { cpu: "7", memory: "16Gi" }
            readinessProbe:
              httpGet: { path: /health, port: 8080 }
              initialDelaySeconds: 60
              periodSeconds: 10
            volumeMounts:
              - { name: dshm, mountPath: /dev/shm }
        volumes:
          - name: dshm
            emptyDir: { medium: Memory, sizeLimit: 4Gi }
    workerTemplate:
      spec:
        nodeSelector:
          kubernetes.io/arch: arm64
          workload: llm-inference
        containers:
          - name: vllm-worker
            image: <ACCOUNT>.dkr.ecr.ap-northeast-2.amazonaws.com/vllm-cpu-arm64:latest
            env:
              - name: HUGGING_FACE_HUB_TOKEN
                valueFrom:
                  secretKeyRef: { name: hf-token, key: token }
              - name: RAY_PORT
                value: "6379"
            command: ["/bin/bash", "-c"]
            args:
              - |
                set -e
                # 리더 주소는 LWS가 주입 (LWS_LEADER_ADDRESS)
                ray start --address="${LWS_LEADER_ADDRESS}:${RAY_PORT}" --block
            resources:
              requests: { cpu: "6", memory: "12Gi" }
              limits:   { cpu: "7", memory: "16Gi" }
            volumeMounts:
              - { name: dshm, mountPath: /dev/shm }
        volumes:
          - name: dshm
            emptyDir: { medium: Memory, sizeLimit: 4Gi }
---
apiVersion: v1
kind: Service
metadata:
  name: vllm-1b-svc
  namespace: llm
spec:
  type: ClusterIP                      # 내부 전용 (보안 기본값)
  selector:
    leaderworkerset.sigs.k8s.io/name: vllm-1b
    role: leader                       # 리더 파드(엔드포인트)만 노출
  ports:
    - port: 80
      targetPort: 8080
EOF
```


## 레퍼런스 ##

* https://aws.github.io/graviton/machinelearning/vllm.html 
