# 수십 GB LLM 서빙 이미지, 5분 걸리던 Cold Start를 30초로 줄인 비결 (feat. SOCI)

> **부제:** Deep Learning Container(DLC)의 지연 로딩: Seekable OCI(SOCI)로 LLM 추론 스케일아웃 최적화하기

---

## 1. 들어가며: LLM 서빙에서 Auto-scaling이 느린 이유

트래픽이 급증할 때 LLM 추론 파드(Pod)를 빠르게 확장(Scale-out)하는 것은 서비스 안정성의 핵심입니다. 하지만 GPU 노드를 프로비저닝하더라도 실제 추론 요청을 처리할 수 있을 때까지 상당한 시간이 걸리는 **Cold Start** 문제가 발목을 잡습니다.

Cold Start 시간을 세부 단계별로 분석해 보면 다음과 같습니다.
1. GPU 워커 노드 프로비저닝
2. **컨테이너 이미지 Pull 및 압축 해제**
3. 모델 가중치(Weights) 다운로드 및 GPU 메모리 적재

이 중 2번 단계에서 큰 병목이 발생합니다. PyTorch, CUDA, vLLM 등이 포함된 **Deep Learning Container(DLC)** 이미지는 용량이 보통 **15GB~30GB**에 달하기 때문에, 이미지를 내려받고 압축을 푸는 데만 수 분이 소요됩니다.

여기서 한 가지 근본적인 질문을 던져볼 수 있습니다.
> *"컨테이너가 시작될 때 저 20GB에 달하는 파일을 정말 전부 다 읽어야만 부팅이 가능할까?"*

---

## 2. 해결책: SOCI (Seekable OCI)란 무엇인가?

**SOCI(Seekable OCI)**는 AWS에서 개발하여 오픈소스로 공개한 기술로, 표준 OCI 컨테이너 이미지를 수정하지 않고도 필요한 파일만 즉시 찾아서(**Seek**) 실행할 수 있게 해주는 지연 로딩(**Lazy Loading**) 솔루션입니다.

### 왜 LLM(DLC) 환경에 특히 효과적인가?
* **실제 필요한 파일은 일부:** 거대한 CUDA 라이브러리나 수많은 파이썬 패키지 중, 컨테이너 부팅(`entrypoint`) 시점에 즉시 접근하는 파일은 전체 용량의 **10~20% 내외**에 불과합니다.
* **온디맨드 로딩:** SOCI는 이미지 내부 파일들의 위치 오프셋 정보를 담은 별도의 인덱스(**SOCI Index**)를 미리 생성해 둡니다. 컨테이너 실행 시 수 MB 크기의 인덱스만 먼저 받은 뒤 바로 부팅하고, 나머지 파일은 실제 코드가 해당 파일을 읽으려 할 때 `HTTP Range Request`를 통해 필요한 블록만 병렬로 가져옵니다.

---

## 3. 아키텍처 및 동작 원리

### 기존 OCI 방식 vs SOCI 방식 비교

* **기존 OCI 방식 (직렬 처리 및 전체 다운로드):**
  `Image Pull (20GB 전체 다운로드)` ➔ `Unpack (전체 압축 해제)` ➔ `Container Start` (긴 대기 시간 발생)

* **SOCI 방식 (인덱스 기반 지연 로딩):**
  `SOCI Index Pull (수 MB)` ➔ `Container Start (즉시 실행)` + `On-demand Fetch (실행 중 필요한 블록만 병렬 로드)`

### 핵심 구성 요소
* **`soci-snapshotter`:** 워커 노드의 컨테이너 런타임(`containerd`)에 연동되는 스냅샷 플러그인으로, FUSE 파일시스템을 통해 원격 레지스트리의 이미지 레이어를 로컬 디스크처럼 마운트합니다.
* **OCI Referrers API (OCI 1.1 표준):** 생성된 SOCI 인덱스를 원본 컨테이너 이미지와 연결(매핑)하여 레지스트리에 저장하기 위해 사용됩니다.

---

## 4. 실전 적용 가이드 (Hands-on)

### Step 1: SOCI 인덱스 생성 및 레지스트리 푸시
기존에 빌드된 DLC 이미지에 대해 `soci` CLI를 사용하여 인덱스를 생성하고 레지스트리에 푸시합니다.

```bash
# 1. 로컬 containerd에 있는 이미지로부터 SOCI 인덱스 생성
soci create --min-layer-size 10485760 my-registry/llm-serving-dlc:v1

# 2. 생성된 인덱스를 레지스트리에 푸시 (OCI Referrers API 활용)
soci push my-registry/llm-serving-dlc:v1
```

> **💡 성능 튜닝 팁:** DLC처럼 파일 수가 많고 레이어가 큰 경우 `--min-layer-size`(인덱싱할 최소 레이어 크기)나 `--span-size`(파일 분할 단위, 기본 4MB) 옵션을 워크로드의 I/O 패턴에 맞게 조정하면 부팅 속도를 더욱 최적화할 수 있습니다.

### Step 2: 런타임 환경 구성 (`containerd`)
워커 노드에서 `containerd`가 기본 `overlayfs` 대신 `soci` 스냅샷터를 사용하도록 설정합니다. (AWS Fargate/Lambda 환경에서는 별도 노드 설정 없이 인덱스만 ECR에 있으면 자동 적용되며, EKS나 일반 K8s에서는 노드 설정이 필요합니다.)

```toml
# /etc/containerd/config.toml 예시
[proxy_plugins]
  [proxy_plugins.soci]
    type = "snapshot"
    address = "/run/soci-snapshotter-grpc/soci-snapshotter-grpc.sock"

[plugins."io.containerd.grpc.v1.cri".containerd]
  snapshotter = "soci"
  disable_snapshot_annotations = false
```

---

## 5. 벤치마크 결과 (Before vs After)

*(실제 테스트 환경의 수치를 아래 표에 기입하여 비교해 보세요)*

| 측정 항목 | 기존 OCI 방식 | SOCI 적용 후 | 개선율 |
| :--- | :--- | :--- | :--- |
| **컨테이너 이미지 크기** | 18.5 GB | 18.5 GB (Index: 12 MB) | - |
| **이미지 Pull ~ Container Running** | 3분 40초 | **22초** | **약 90% 단축** |
| **첫 추론 응답(TTFT 포함)까지 총 시간** | 4분 30초 | **1분 12초** | **약 73% 단축** |

---

## 6. 도입 시 주의사항 및 트레이드오프

1. **런타임 초기 I/O 지연 (Warm-up 필요성):**
   컨테이너 상태가 `Running`으로 바뀌는 시간은 극적으로 줄어들지만, 첫 추론 요청이 들어올 때 아직 다운로드되지 않은 파이썬 라이브러리나 CUDA 커널을 읽으면서 미세한 네트워크 I/O 지연이 발생할 수 있습니다. Readiness Probe 단계에서 가벼운 더미 추론(Warm-up)을 수행하면 실제 사용자 트래픽의 지연을 방지할 수 있습니다.
2. **노드 CPU 및 네트워크 대역폭:**
   `soci-snapshotter`가 유저 스페이스 파일시스템(FUSE) 기반으로 동작하므로, 초기 로딩 시 네트워크 대역폭과 CPU 자원을 일부 사용합니다. GPU 인스턴스처럼 스펙이 높은 노드에서는 영향이 미미하지만 사전 부하 테스트를 권장합니다.
3. **이미지 무결성 및 보안 정책 유지:**
   원본 컨테이너 이미지의 내용이나 SHA256 다이제스트를 전혀 변경하지 않고 별도의 인덱스 아티팩트만 연결하므로, 기존의 취약점 스캐닝이나 이미지 서명(Cosign 등) 파이프라인을 그대로 유지할 수 있습니다.
