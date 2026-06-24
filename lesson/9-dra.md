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
