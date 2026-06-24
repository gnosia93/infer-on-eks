## MIG ##



## DRA (Dynamic Resource Allocation) ##

기존의 단순 개수 기반(nvidia.com/gpu: 1) 모델과 달리, DRA는 EKS v1.33+ 버전부터 기본 기능 게이트로 활성화되어, Pod 단위로 GPU 메모리 분할(MPS, Time-slicing), 토폴로지 인식 스케줄링 등을 세밀하게 제어할 수 있습니다.

* MPS / Time-slicing 실습: G5 또는 G6 인스턴스
* Hardware MIG 분할 실습: P4d 또는 P5 인스턴스


### NVIDIA GPU Operator (DRA Driver) 설치 ###
Kubernetes 스케줄러가 디바이스 정보를 인식(ResourceSlices 생성)하도록 NVIDIA DRA Driver가 포함된 GPU Operator를 헬름(Helm) 등으로 배포합니다.
```
helm upgrade --install gpu-operator nvidia/gpu-operator \
  -n gpu-operator --create-namespace \
  --set driver.enabled=true \
  --set dra.enabled=true   # 👈 DRA 컴포넌트 활성화 필수
```
💡 배포 완료 후 kubectl get deviceclasses 명령을 내렸을 때 gpu.nvidia.com 또는 mig.nvidia.com 같은 디바이스 클래스가 정상 조회되어야 합니다.


### 자원 템플릿(ResourceClaimTemplate) 생성 ###
사용자가 무작정 GPU를 통째로 가져가지 않고, 원하는 스펙(예: 특정 메모리 크기, MPS 공유 정책 등)을 선언할 수 있는 템플릿을 배포합니다.

```
# gpu-template.yaml
apiVersion: resource.k8s.io/v1alpha3
kind: ResourceClaimTemplate
metadata:
  name: nvidia-mps-gpu-template
  namespace: gpu-test
spec:
  spec:
    devices:
      requests:
      - name: my-gpu
        deviceClassName: gpu.nvidia.com
        selectors:
        - cel: "device.attributes['://nvidia.com'] >= 16384" # 최소 16GiB 이상 필터링
```

### 워크로드 Pod 배포 (DRA 연동) ###
컨테이너 내부 resources에 개수를 적는 대신, 최상단 resourceClaims 필드를 이용해 정의해 둔 템플릿을 바인딩합니다.
```
# gpu-pod.yaml
apiVersion: v1
kind: Pod
metadata:
  name: dra-gpu-inference-pod
  namespace: gpu-test
spec:
  containers:
  - name: cuda-container
    image: nvcr.io/nvidia/k8s/cuda-sample:vectoradd-cuda11.7.1
    resources: {} # ❌ 기존 nvidia.com/gpu 문법을 사용하지 않습니다.
    volumeDevices:
    - name: gpu-claim
      devicePath: /dev/nvidia0
  resourceClaims:
  - name: gpu-claim
    source:
      resourceClaimTemplateName: nvidia-mps-gpu-template # 👈 3번에서 만든 템플릿 지정
```

### 주의사항 ###
* 네임스페이스(Namespace) 제약: DRA 아키텍처 상 ResourceClaim 객체와 이를 사용하는 Pod는 반드시 동일한 네임스페이스에 존재해야 오류가 나지 않습니다.
* Karpenter 연동 유의: 오토스케일러인 Karpenter는 아직 동적 리소스 클레임 정보를 완벽하게 계산하여 노드를 띄우는 기능이 완전히 성숙하지 않았을 수 있습니다. 워크숍 환경에서는 수강생들의 혼선을 줄이기 위해 EKS 관리형 노드 그룹(MNG)으로 GPU 인스턴스 개수를 미리 고정해 두고 실습하는 것을 강력하게 권장합니다.

* 워크숍 참가자들이 실습할 구체적인 공유 시나리오(예: 하나의 GPU를 소형 LLM 추론 여러 개로 쪼개기 vs 대규모 모델 멀티 노드 훈련) 
