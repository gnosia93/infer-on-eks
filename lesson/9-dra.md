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
