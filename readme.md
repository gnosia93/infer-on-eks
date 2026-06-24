# Inference ON EKS

* [C1. VPC 생성하기](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/1-create-vpc.md)

* [C2. EKS 클러스터 생성하기](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/2-create-eks.md)

* [C3. Karpenter 노드풀 생성](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/3-karpenter-nodepool.md)
  * cpu
  * gpu
  * 인퍼런시아 

* [C4. 플로그인 설치](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/4-cluster-plugin.md)

* [C5. lustre 파일시스템 생성](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/5-create-lustre.md)
      
* [C6. LeaderWorkerSet (LWS)](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/6-LeaderWorkerSet.md)
   * [ray 인프라](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/2-ray.md)
   * [cpu 인퍼런스 - 그라비톤](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/2-lws.md)
   * [gpu 인퍼런스]
   * [AWS 인퍼런시아]

* C7. LLM 성능 평가 및 보안
   * [llm 성능 평가](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/3-promptfoo-perf.md) 
   * llm 보안 취약점 스캔
   * LLM 성능 테스트
     *	툴: Locust, vLLM benchmark 등을 활용하여 동시 요청 수 대비 처리량(TTFT: Time to First Token, ITL: Inter-Token Latency, RPS)을 측정합니다.
     * 	목적: 인프라 스케일 아웃 임계값 설정을 위한 정량적 데이터 확보.

* [C8. GPU Observability]

* [C9. DRA](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/9-dra.md)


## Appendix ##

* [A1. 피지컬 AI - VLA/VLM]

* [A2. Capcity Block]


  
## 레퍼런스 ##

* [모두의 로보틱스 - VLA 입문](https://wikidocs.net/book/19039)


---
* 이론 교재
   * AI Infra 의 이해 (90 Min)
   * 모델 인프런스 이센셜 (60 Min)
      * eks 인퍼런스 ./w lws + plugin + lustre.
      * prmptfool 이론.. --> llm 테스트이론.. + promptfoo 설명.

