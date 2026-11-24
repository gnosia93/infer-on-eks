# infer-on-eks

$\textcolor{#326CE5}{\text{W.I.P}}$

![](https://github.com/gnosia93/infer-on-eks/blob/main/images/llm-infer-arch-1.png)

### llm-d 확장 (Prefill 과 Decode 의 분리) ###
현재 아키텍처(ALB + LiteLLM + Envoy + vLLM)는 별도의 무거운 분산 추론 플랫폼 없이 기존 Kubernetes와 AWS 표준 컴포넌트만으로 멀티턴 성능과 고가용성을 모두 확보할 수 있는 최적 및 최소의 아키텍처다. 향후 대규모 트래픽 대응을 위해 llm-d를 도입하게 될 경우, 다음과 같은 추가 구성과 이점이 따른다.
• 추가 필요 요소: Kubernetes Gateway API(추론 확장), LeaderWorkerSet 등 전용 컨트롤 플레인 설치와 노드 간 고속 KV Cache 전송을 위한 네트워크/캐시 스토리지 구성.
• 도입 시 장점: 각 파드의 실시간 GPU 캐시 상태를 직접 인식해 라우팅하고, 연산(Prefill)과 생성(Decode) 노드를 분리 운영할 수 있어 초장문 컨텍스트 및 대규모 AI 에이전트 환경에서 GPU 처리량을 극대화할 수 있다.

Prefill(입력 처리)은 GPU 연산력을, Decode(토큰 생성)는 메모리 대역폭을 주로 사용하는 정반대의 자원 특성을 가진다. 따라서 일반적인 챗봇 환경에서는 통합 운영이 유리하며, 수만~10만 토큰 이상의 방대한 문서를 동시에 입력받아 긴 입력 처리가 전체 답변 생성 속도를 지연시키는 초대규모·초장문 환경에서만 두 단계의 분리를 고려한다.



### _Basic_ ###

* [C1. VPC 생성하기](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/1-create-vpc.md)

* [C2. EKS 클러스터 생성하기](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/2-create-eks.md)

* [C3. GPU 스케줄링 설정](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/3-gpu.md)
  
* C4. vLLM - Gemma4-12B 모델 배포
  * [모델 선정 기준 (Bedrock -> Open Weight)](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/4-model-selection.md)
  * [모델 배포하기 - 디플로이먼트/서비스](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/4-vllm.md)
  * [모델 레이턴시 측정](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/4-vllm-latency.md)
    
* C5. 세션 / 트래픽 라우팅
  * [LiteLLM 배포하기](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/5-litellm.md)
  * [세션 ID 기반 vLLM 요청 라우팅 (Istio/Envoy Consistent Hashing)](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/5-istio.md)
  * [서비스 엔드 포인트 만들기 - ALB Ingress](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/5-alb-ingress.md)

* [C6. 콜드 스타트 최적화 (파드 기동 시간 단축)](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/6-optimize-cold-start.md) [기존 7분 -> 4분]
  * [S3 Express One Zone 기반 초고속 모델 로딩](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/6-optimize-s3.md) [-3초] 
  * [GPU 노드풀 최적화](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/6-optimize-nodepool.md) [-2분]
  * [vLLM 기동 시간 단축](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/6-optimize-vllm-launch.md) [-1분]
    
* C7. Headroom-based Proactive Scaling with KEDA (한계치에 도달하기 전에 미리 확보)
  * [Prometheus 설치하기](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/7-keda-prometheus.md)
  * [KEDA 설치 및 ScaledObject 생성](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/7-keda-install.md)
  * [vLLM 파드 스케일링 테스트](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/7-keda-autoscaling-test.md)

* [C8. vLLM Network Policy](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/8-cni-network-policy.md) 

* C9. LLM 성능 평가 및 보안
   * [promptfoo 로 모델 성능 평가하기](https://aws.amazon.com/ko/blogs/tech/bedrock-promptfoo-eval/)
   * llm 보안 취약점 스캔
    
### _Advanced_ ###
      
* [C10. LeaderWorkerSet (LWS) & Ray 인프라](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/10-lws.md)
   * [ray 인프라](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/2-ray.md)

* [C11. GPU 모니터링](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/11.gpu-monitoring.md)

* [C12. TensorRT-LLM](https://github.com/gnosia93/lgraph-agentic-ai/blob/main/lesson/10-tensorrt-inference.md)

## Appendix ##

* [A1. Capcity Block](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/a2-capacity-block.md)
* [A2. EFA 모니터링](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/a2-efa-observability.md)
* [A4. MIG & DRA](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/a4-dra.md)
* [A5. 이미지 서비스 아키텍처](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/a5-difussion-async.md)
