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
LWS_LEADER_ADDRESS, LWS_GROUP_SIZE는 LWS 컨트롤러가 파드에 자동 주입하는 환경변수예요. 그래서 리더/워커가 서로를 자동으로 찾습니다.


### 3. vLLM CPU(arm64) 이미지 ###
vLLM은 CPU 휠을 PyPI에 안 올려서, ARM64는 직접 빌드가 가장 확실해요.
```
git clone https://github.com/vllm-project/vllm.git && cd vllm
docker buildx build --platform linux/arm64 \
  -f docker/Dockerfile.cpu \
  -t <ACCOUNT>.dkr.ecr.ap-northeast-2.amazonaws.com/vllm-cpu-arm64:latest \
  --push .
```

### 4. 배포 & 테스트 ###
```
kubectl apply -f lws-vllm-cpu.yaml
kubectl -n llm get pods -o wide          # 리더1 + 워커1
kubectl -n llm port-forward svc/vllm-1b-svc 8080:80 &

curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"meta-llama/Llama-3.2-1B-Instruct",
       "messages":[{"role":"user","content":"안녕"}],"max_tokens":128}'
```

### 5. GPU 10B/100B 전환 시 바꿀 것 (구조는 그대로) ###
리더/워커 양쪽 컨테이너에 동일 적용:

```
# 1) 이미지: CPU 빌드 → 공식 GPU 이미지
image: vllm/vllm-openai:latest

# 2) 노드셀렉터: Graviton CPU → GPU 노드
nodeSelector:
  kubernetes.io/arch: amd64           # 또는 GPU 노드 라벨
  # node.kubernetes.io/instance-type: p5.48xlarge 등

# 3) 리소스: GPU 요청
resources:
  limits:
    nvidia.com/gpu: "8"               # 파드(노드)당 GPU 수

# 4) vLLM serve 인자 (--device cpu 제거)
#    총 GPU = tensor_parallel_size × pipeline_parallel_size
#    예) 100B를 2노드×8GPU로:
--tensor-parallel-size 8              # 노드 내 GPU
--pipeline-parallel-size 2            # 노드 수 = LWS size
```
즉 100B로 갈 땐 size(=파이프라인 단계 수)와 tensor-parallel-size(노드당 GPU)만 키우면 됩니다. LWS·Ray·Service 구조는 동일해요.


### 짚어둘 점 (중요) ###
```
CPU 분산의 현실: 1B는 사실 한 파드에 충분히 들어갑니다. pipeline-parallel-size=2로 2파드에 굳이 걸치면 노드 간 통신 오버헤드로 오히려 느려질 수 있어요. vLLM의 CPU 멀티노드 분산은 GPU만큼 성숙하지 않습니다. 두 가지 선택지가 있어요.

패턴 검증이 목적이다(지금 LWS 구조를 그대로 굳히고 싶다) → 위 매니페스트대로 size: 2 + PP=2 유지
1B 단계는 성능 우선이다 → size: 1, replicas: 2로 두고(각 파드가 독립 서빙) GPU 전환 시 size: 2+병렬도로 변경
목적이 "LWS 파이프라인을 미리 깔아두기"라면 1번이 맞고, 그 의도로 위 매니페스트를 짰어요.

보안: Service를 ClusterIP로 막아놨어요. 외부 노출 시 추론 엔드포인트에 인증이 없으니 ALB+인증이나 게이트웨이를 반드시 앞단에 두세요.

모델 라이선스: Llama 3.2는 Meta 라이선스 동의·HF 게이트 승인이 필요합니다. MODEL_ID만 바꾸면 다른 모델로 교체돼요.

모델 로딩 시간: 100B급은 컨테이너+가중치가 수백 GB라 다운로드만 1시간 이상 걸릴 수 있어요. 그 단계에선 EFS/FSx PVC나 S3+Mountpoint로 가중치를 캐싱하는 걸 권합니다.
```


## 레퍼런스 ##

* https://aws.github.io/graviton/machinelearning/vllm.html 
