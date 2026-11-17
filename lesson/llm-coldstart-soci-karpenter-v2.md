# 수십 GB LLM 서빙 이미지, 7분 걸리던 Cold Start를 1분대로 줄인 비결 (Karpenter + Balloon Pod + SOCI)

> **요약:** LLM 추론 환경에서 오토스케일링이 느린 두 가지 핵심 병목인 **① GPU 노드 프로비저닝 지연**과 **② 수십 GB에 달하는 Deep Learning Container(DLC) 이미지 다운로드 지연**을 **Karpenter Over-provisioning(Balloon Pod)**과 **Seekable OCI(SOCI) Lazy Loading** 조합으로 해결하는 실전 아키텍처를 소개합니다.

---

## 1. 들어가며: LLM 서빙에서 Auto-scaling이 느린 이유

트래픽이 급증할 때 파드(Pod)를 늘리는 일반적인 마이크로서비스와 달리, LLM 서빙 환경에서는 오토스케일링이 작동해도 실제 서비스에 투입되기까지 **최소 6~8분 이상의 긴 Cold Start**가 발생합니다.

전체 스케일아웃 파이프라인을 쪼개보면 병목은 크게 세 구간에서 발생합니다.

1. **[1단계] GPU 노드 프로비저닝 (2~3분):** Karpenter가 트래픽을 감지해 신규 GPU EC2 인스턴스를 생성하고, NVIDIA 드라이버 및 CUDA 런타임을 초기화하는 시간
2. **[2단계] DLC 컨테이너 이미지 Pull & 압축 해제 (3~4분):** PyTorch, CUDA, vLLM 등이 포함된 15~30GB 크기의 거대한 Deep Learning Container(DLC) 이미지를 레지스트리에서 받아 압축을 푸는 시간
3. **[3단계] 모델 가중치(Weights) 로드 (1분 내외):** S3나 EFS 등에서 수십 GB의 LLM 모델 파라미터를 GPU VRAM으로 적재하는 시간

이 글에서는 **1단계(노드 확보)**와 **2단계(이미지 다운로드)**의 병목을 각각 제거하여 전체 Cold Start 시간을 극적으로 단축하는 방법을 다룹니다.

---

## 2. 1단계 병목 해결: Karpenter + Balloon Pod로 GPU 노드 사전 확보

GPU 인스턴스(`g5`, `p4d`, `p5` 등)는 일반 CPU 인스턴스보다 물리적 하드웨어 초기화 및 NVIDIA 커널 모듈 로딩 시간이 훨씬 오래 걸립니다. 노드 생성 자체를 0초로 만들 수 없다면, **트래픽이 오기 전에 미리 노드를 띄워두는 전략(Over-provisioning)**이 필요합니다.

### 작동 원리: PriorityClass와 더미 파드(Balloon Pod)
1. **사전 확보 (Pre-warming):** 아무 작업도 하지 않고 GPU 리소스만 점유하는 **낮은 우선순위의 더미 파드(Balloon Pod)**를 미리 배포해 Karpenter가 예비 GPU 노드를 생성하도록 유도합니다. (드라이버 초기화 완료 상태 대기)
2. **선점 (Preemption):** 실제 LLM 서빙 트래픽이 증가해 **높은 우선순위의 서빙 파드**가 생성되면, 쿠버네티스 스케줄러가 더미 파드를 즉시 쫓아내고(Evict) 그 자리에 실제 파드를 배치합니다.
3. **연쇄 확장 (Chain Reaction):** 쫓겨나 `Pending` 상태가 된 더미 파드는 Karpenter를 트리거하여 **다음 예비용 GPU 노드를 백그라운드에서 다시 확보**합니다.

### 구현 예시 (YAML)

#### ① PriorityClass 정의 (우선순위 분리)
```yaml
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: low-priority-placeholder
value: -10 # 기본값(0)보다 낮게 설정
globalDefault: false
description: "GPU 노드 사전 확보용 더미 파드 우선순위"
---
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: high-priority-llm-serving
value: 1000 # 실제 LLM 서빙 파드용 높은 우선순위
globalDefault: false
description: "실제 LLM 서빙 워크로드 우선순위"
```

#### ② Balloon Pod Deployment
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: gpu-node-placeholder
spec:
  replicas: 1 # 항상 유지할 예비 GPU 노드 수
  selector:
    matchLabels:
      app: gpu-placeholder
  template:
    metadata:
      labels:
        app: gpu-placeholder
      annotations:
        # Karpenter가 유휴 노드로 오해해 회수(Consolidation)하지 않도록 보호
        karpenter.sh/do-not-disrupt: "true"
    spec:
      priorityClassName: low-priority-placeholder
      terminationGracePeriodSeconds: 0 # 선점 시 0초 만에 즉시 종료 (매우 중요)
      containers:
        - name: pause
          image: registry.k8s.io/pause:3.9 # 초경량 이미지 사용
          resources:
            requests:
              nvidia.com/gpu: 1 # GPU 1장 점유하여 Karpenter 트리거
            limits:
              nvidia.com/gpu: 1
```

> **실무 팁:**
> * **Consolidation 충돌 방지:** `karpenter.sh/do-not-disrupt: "true"` 설정이 없으면 Karpenter가 CPU/메모리 사용률이 낮은 더미 파드 노드를 유휴 상태로 판단해 종료시킬 수 있습니다.
> * **비용 최적화:** 예비 노드는 유휴 비용이 발생하므로, 트래픽이 몰리는 피크 시간대에만 `CronHPA` 등으로 더미 파드의 `replicas`를 조절하는 것이 효율적입니다.

---

## 3. 2단계 병목 해결: SOCI (Seekable OCI)로 DLC 이미지 지연 로딩

사전에 확보된 깨끗한(신규) GPU 노드에는 아직 20GB짜리 LLM 서빙 이미지가 캐싱되어 있지 않습니다. 이때 **SOCI(Seekable OCI)**를 적용하면 이미지 전체를 다운로드하지 않고도 컨테이너를 즉시 실행할 수 있습니다.

### SOCI의 핵심 원리 (Lazy Loading)
* 기존 OCI 이미지는 수십 GB 전체를 다운로드하고 압축을 푼 뒤에야 `entrypoint`가 실행됩니다.
* **SOCI**는 원본 컨테이너 이미지를 수정하지 않고, 내부 파일들의 오프셋 정보를 담은 별도의 **SOCI Index**를 생성합니다.
* 컨테이너 시작 시 수 MB 크기의 인덱스만 먼저 받은 뒤, **실제 부팅에 당장 필요한 파일(전체 용량의 약 10~20%)만 `HTTP Range Request`로 쏙쏙 뽑아서(Seek) 실행**합니다.

### 실전 적용 가이드

#### Step 1: SOCI 인덱스 생성 및 레지스트리 푸시
CI/CD 파이프라인에서 DLC 이미지 빌드 후 `soci` CLI를 이용해 인덱스를 생성합니다.

```bash
# 1. 로컬 containerd에 이미지 로드 후 SOCI 인덱스 생성
# DLC처럼 파일이 많고 큰 경우 min-layer-size 등을 튜닝하여 인덱스 크기 최적화
soci create --min-layer-size 10485760 <REGISTRY_URL>/llm-serving:v1

# 2. 생성된 SOCI 인덱스를 레지스트리에 푸시 (OCI Referrers API 활용)
soci push <REGISTRY_URL>/llm-serving:v1
```

#### Step 2: 워커 노드(AMI) 런타임 구성
Karpenter가 프로비저닝하는 GPU 노드의 커스텀 AMI(또는 UserData)에 `soci-snapshotter`가 설치되고 `containerd`와 연동되어 있어야 합니다.

```toml
# /etc/containerd/config.toml 핵심 설정 예시
[proxy_plugins]
  [proxy_plugins.soci]
    type = "snapshot"
    address = "/run/soci-snapshotter-grpc/soci-snapshotter-grpc.sock"

[plugins."io.containerd.grpc.v1.cri".containerd]
  snapshotter = "soci"
  disable_snapshot_annotations = false
```

---

## 4. 전체 파이프라인 변화 및 벤치마크 결과

Karpenter Balloon Pod와 SOCI를 결합하면 전체 Cold Start 타임라인이 다음과 같이 압축됩니다.

* **기존 파이프라인 (총 6~8분 소요):**
  `[GPU 노드 생성: 2~3분]` ➔ `[DLC 이미지 Pull & 압축해제: 3~4분]` ➔ `[모델 가중치 로드: 1분]`
* **최적화 후 (총 1분 20초 내외):**
  `[사전 확보된 노드 즉시 할당: 0초]` ➔ `[SOCI 지연 로딩: 20초]` ➔ `[모델 가중치 로드: 1분]`

| 측정 단계 / 항목 | 기존 방식 (OCI + On-demand) | 개선 방식 (SOCI + Balloon Pod) | 개선 효과 |
| :--- | :--- | :--- | :--- |
| **컨테이너 이미지 크기** | 18.5 GB | 18.5 GB (SOCI Index: 12 MB) | 원본 무결성 유지 |
| **GPU 노드 확보 대기 시간** | 2분 30초 | **0초** (사전 확보 노드 선점) | **100% 제거** |
| **이미지 Pull ~ Container Running** | 3분 40초 | **22초** | **약 90% 단축** |
| **첫 추론 응답(TTFT 포함)까지 총 시간** | **7분 10초** | **1분 25초** | **약 80% 단축** |

---

## 5. 도입 시 주의사항 (트레이드오프)

1. **런타임 초기 I/O 지연 (Warm-up 필요):**
   컨테이너는 20초 만에 뜨지만, 첫 번째 추론 요청이 들어올 때 아직 다운로드되지 않은 파이썬 라이브러리나 CUDA 커널을 읽으면서 미세한 네트워크 지연이 발생할 수 있습니다. Readiness Probe에 가벼운 더미 추론(Warm-up) 요청을 포함해 해결하는 것을 권장합니다.
2. **인스턴스 스토어(NVMe) 활용 권장:**
   `soci-snapshotter`는 FUSE 파일시스템 기반으로 동작하며 로컬 디스크에 캐싱합니다. `g5`나 `p4d` 인스턴스에 기본 제공되는 고속 로컬 NVMe SSD에 `/var/lib/soci-snapshotter-grpc` 경로를 마운트하면 I/O 성능을 극대화할 수 있습니다.
3. **레지스트리 호환성 확인:**
   Amazon ECR은 SOCI 인덱스를 네이티브로 지원하지만, 온프레미스나 사설 레지스트리를 사용하는 경우 **OCI 1.1(Referrers API) 및 HTTP Range Request**를 지원하는지(예: Harbor v2.8+, Zot 등) 사전 확인이 필요합니다.
