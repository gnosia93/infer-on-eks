DRA (Dynamic Resource Allocation)
쿠버네티스 v1.26부터 도입된 새로운 자원 할당 방식입니다.
* 기존의 단순한 nvidia.com/gpu: 1 식의 정적 할당을 넘어, 파드가 실행 중에 GPU 자원을 동적으로 할당/해제하거나 공유(MIG, vGPU)할 수 있도록 지원하는 프레임워크입니다. 추론 워크로드의 자원 효율성을 극대화합니다.
