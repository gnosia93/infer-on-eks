
### Ray Architecture: 공유 메모리(Shared Memory)와 분산 객체 저장소(Distributed Object Store) ###
Ray는 서로 다른 물리적 컴퓨터(노드)의 메모리를 진짜로 물리적으로 합치는 것은 아닙니다. 대신, **"분산 객체 저장소(Distributed Object Store)"**라는 영리한 가상화 레이어와 **"초고속 네트워크(RPC/NCCL)"**를 통해, 개발자가 느끼기에는 마치 하나의 거대한 메모리 공간(Single Shared Memory Space)을 쓰는 것처럼 착각하게 만드는 기술입니다.

#### 1. 노드 안의 초고속 통신: 묵찌빠 없는 플라즈마(Plasma) 저장소 ####
Ray가 설치된 모든 쿠버네티스 파드(Pod) 내부에는 Plasma라는 대용량 공유 메모리(Shared Memory) 엔진이 백그라운드에서 돌아갑니다.
* CPU/GPU 메모리 직통: 한 파드 안에서 여러 개의 워커(Worker) 프로세스가 같은 대형 AI 모델 데이터나 텐서(Tensor)를 읽어야 할 때, 데이터를 복사(Copy)하지 않고 메모리 주소만 공유하는 Zero-copy 방식을 씁니다.
* 덕분에 같은 노드 내에서는 프로세스가 달라도 메모리 병목이 전혀 없이 빛의 속도로 데이터를 주고받습니다.

#### 2. 서로 다른 노드 간의 연결: 분산 객체 저장소 (Distributed Object Store) ####
진짜 마법은 서로 다른 쿠버네티스 노드(예: 노드 A의 파드 1과 노드 B의 파드 2) 사이에서 일어납니다. Ray는 모든 노드의 Plasma 저장소를 하나로 묶어 **전역 지도(Global Control Store, GCS)**를 관리합니다.
* 메모리 주소의 추상화 (ObjectRef): Ray에서는 메모리에 데이터를 올리면 실제 물리 주소 대신 고유한 ID인 ObjectRef를 발급합니다.
* 데이터가 어디 있든 상관없다: 노드 A에 있는 워커가 ObjectRef_XYZ라는 데이터가 필요해서 ray.get(ObjectRef_XYZ)을 호출하면, Ray 엔진이 전역 지도를 확인합니다.
* "어, 그 데이터 노드 B의 GPU 메모리에 있네?" 라고 판단하면, 노드 B에게 요청해 데이터를 가져옵니다. 개발자 코드 상에서는 그냥 옆방 메모리에서 꺼내 쓰는 것처럼 한 줄로 끝납니다.

### 3. 대규모 AI용 GPU 메모리 섀링: NCCL(고속 도로) 통신 ###
특히 질문 주신 GPU 메모리 연결은 LLM 분산 서빙/학습에서 가장 중요한데요, 이때는 CPU를 거치지 않고 GPU끼리 직접 데이터를 주고받는 기술이 핵심입니다.
* Ray는 내부적으로 NVIDIA가 만든 **NCCL(Nvidia Collective Communications Library)**을 적극 활용합니다.
( GPU 간에 대형 모델 파라미터를 주고받을 때, GPU (노드 A) ➡️ CPU ➡️ 네트워크 카드 ➡️ CPU ➡️ GPU (노드 B) 같은 복잡한 단계를 거치면 너무 느리겠죠?
* Ray 인프라 상의 NCCL은 GPUDirect RDMA 기술 등을 사용해, 노드 A의 GPU 메모리에 있는 데이터를 네트워크 카드를 통해 노드 B의 GPU 메모리로 직접(Direct) 꼽아줘서 메모리 전송 지연 시간(Latency)을 극한으로 줄입니다.

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
