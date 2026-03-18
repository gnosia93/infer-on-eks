### Foundation 모델 ###
* https://huggingface.co/Qwen/Qwen3.5-27B
```
Qwen3.5 (2026년 2월):
  - Agentic AI 시대를 위해 설계 ← 딱 맞음
  - 네이티브 멀티모달 (텍스트 + 이미지 + 비디오)
  - 하이브리드 아키텍처 (Gated DeltaNet + MoE)
  - 256K 컨텍스트
  - 201개 언어
```

### PPL 측정 ###
파인튜닝 이전에 "DevOps/머신러닝" 도메인에 대한 모델의 이해도를 측정한다. 
PPL(Perplexity)은 모델이 주어진 텍스트를 얼마나 "당연하게" 예측하는지를 측정하는 지표로, 수학적으로는 모델이 다음 토큰을 예측할 때의 평균 불확실성이다.
```
PPL = exp(-1/N × Σ log P(token_i | token_1, ..., token_i-1))
```
* PPL = 1: 모델이 다음 단어를 100% 확신 (완벽한 예측)
* PPL = 10: 매 토큰마다 평균 10개 후보 중 고민
* PPL = 100: 매 토큰마다 100개 후보 중 고민 (잘 모르는 도메인)
PPL 값이 낮을수록 좋다.
#### #### 
* https://github.com/gnosia93/agentic-ai-eks/blob/main/code/qwen_ppl.py




### 파인튜닝 ###
* https://github.com/gnosia93/agentic-ai-eks/blob/main/code/qwen_finetune.py
