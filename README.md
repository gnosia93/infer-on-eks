
* [1. EKS 생성하기](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/1-create-eks.md)

* [2. GPU 노드풀 생성](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/2-gpu-nodepool.md)

* [3. TensorRT-LLM](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/3-tensorrt-llm.md)
   
* [4. NVIDIA Dyanmo](https://github.com/gnosia93/post-training/blob/main/lesson/4-dynamo.md)
  - [로컬 Docker 배포하기](https://github.com/gnosia93/interence-on-eks/blob/main/lesson/4-dynamo-docker.md) 
  - [EKS 배포하기](https://github.com/gnosia93/interence-on-eks/blob/main/lesson/4-dynamo-eks.md) 

* [5. Post Training](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/5-post-training.md)
  - 모델 성능 테스트하기 
  - 인퍼런스 성능 테스트
  - Pre-trained Base Model: 사전 학습 모델 준비 (예: Llama 3, Qwen 등)
  - SFT (Supervised Fine-tuning): 고품질 지시 데이터셋으로 미세 조정
  - Alignment (DPO/RLHF): 사람의 선호도를 반영하여 답변 정렬
  - Quantization: 최종 모델 압축 및 경량화 
  - Prunning
    
```
Step 1: 단일 컨테이너 방식 (Python FastAPI + Model) → "아, 트래픽 몰리니 GPU가 노네?"
Step 2: NVIDIA Dynamo/Triton 그래프 방식 도입 → "전처리(CPU), 추론(GPU), 후처리(GPU) 로 분리하여 GPU 사용률을 최대화 한다."
Step 3: Karpenter를 이용한 GPU 노드 오토스케일링 → "Keda or Planner 기반 비교"
```






## 레퍼런스 ##

* https://github.com/NVIDIA/Model-Optimizer/tree/main 
* https://github.com/huggingface/accelerate









