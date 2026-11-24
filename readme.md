# infer-on-eks

This workshop is under construction, Not fully implemented yet ...

![](https://github.com/gnosia93/infer-on-eks/blob/main/images/infer-arch-2.jpg)



### 트래픽 흐름 ###
* AWS ALB → LiteLLM Service (Ingress/TargetGroup)를 바라봄 (ALB 유휴 타임아웃을 600초(10분)로 늘려 긴 SSE 스트리밍 보호)
* LiteLLM Proxy 파드 → Envoy Router Service를 바라봄 (api_base 설정)
* Envoy Router 파드 → vLLM Headless Service를 통해 각 vLLM 파드들의 실제 IP를 바라봄 (Envoy가 x-session-id 헤더를 해싱해서 특정 vLLM 파드 IP로 직접 꽂아줌)

 만약 EKS 클러스터에 Istio가 설치되어 있다면 별도의 Envoy 파드를 띄우지 않으므로, LiteLLM은 그냥 http://vllm-headless-service:8000/v1을 바라보고 Istio의 사이드카 프록시가 중간에서 가로채어 라우팅



### _Basic_ ###

* [C1. VPC 생성하기](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/1-create-vpc.md)

* [C2. EKS 클러스터 생성하기](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/2-create-eks.md)

* [C3. GPU 스케줄링 설정](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/3-gpu.md)
  
* C4. vLLM - Gemma4-12B 모델 배포
  * [모델 선정 기준 (Bedrock -> Open Weight)](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/4-model-selection.md)
  * [모델 배포하기 - 디플로이먼트/서비스](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/4-vllm.md)
  * [모델 레이턴시 측정](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/4-vllm-latency.md)
    
* C5. 세션 / 트래픽 라우팅
  * [LiteLLM](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/5-litellm.md)
  * [Istio L7 Router - Session Aware]
  * [AWS ALB - Ingress]
  * https://github.com/gnosia93/infer-on-eks/blob/main/lesson/litellm-istio-vllm-prefix-cache.md

* C6. 콜드 스타트 해결
  * https://github.com/gnosia93/infer-on-eks/blob/main/lesson/s3_datasync_fast_model_loading.md 
  * https://github.com/gnosia93/infer-on-eks/blob/main/lesson/eks_s3_fast_model_loading_full_guide.md
  * https://github.com/gnosia93/infer-on-eks/blob/main/lesson/llm-coldstart-soci-blog-outline.md  
  * https://github.com/gnosia93/infer-on-eks/blob/main/lesson/llm-coldstart-soci-karpenter-v2.md 
  * [배포시간 최적화 - SOCI Parallel Pull](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/4-vllm-optimized.md)

* C7. KEDA (Kubernetes Event-Driven Autoscaling)
  * [Prometheus 설치하기](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/7-keda-prometheus.md)
  * [GPU 파드 오토스케일링 설정하기](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/7.keda-autoscaling.md) 
  * [GPU 노드 Pre Scaling](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/6-auto-scaling.md)



* C8. LLM 성능 평가 및 보안
   * [LLM 성능 평가(LLM 품질 평가 - Model/Prompt Evaluation)](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/3-promptfoo-perf.md) 
   * llm 보안 취약점 스캔
    
### _Advanced_ ###



* [C9. lustre 설정](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/5-create-lustre.md)
      
* [C10. LeaderWorkerSet (LWS) & Ray 인프라](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/6-LeaderWorkerSet.md)
   * [ray 인프라](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/2-ray.md)

     
* [C11. MIG & DRA](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/9-dra.md)



## Appendix ##

* [A1. Capcity Block](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/a2-capacity-block.md)


