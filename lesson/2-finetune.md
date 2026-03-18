## Foundation 모델 ##
* https://huggingface.co/Qwen/Qwen3.5-27B
```
Qwen3.5 (2026년 2월):
  - Agentic AI 시대를 위해 설계 ← 딱 맞음
  - 네이티브 멀티모달 (텍스트 + 이미지 + 비디오)
  - 하이브리드 아키텍처 (Gated DeltaNet + MoE)
  - 256K 컨텍스트
  - 201개 언어
```

## LLM Benchmark ##
```
pip install lm-eval

import sys
!{sys.executable} -m lm_eval --model hf \
  --model_args pretrained=Qwen/Qwen3.5-27B,dtype=bfloat16 \
  --tasks mmlu,arc_challenge,gsm8k,hellaswag,lambada_openai,winogrande,truthfulqa_mc2,openbookqa,toxigen,bbq \
  --batch_size 4 \
  --output_path ./eval_results/
```



## PPL ##
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
파인튜닝 전후로 모델에 대한 PPL 값을 측정하여 비교하면 해당 모델에 대한 도메인 이해도를 비교 측저할 수 있다. 예를 들어
```
파인튜닝 전 도메인 PPL: 15.3
파인튜닝 후 도메인 PPL: 4.2 
```
인 경우 도메인에 대한 이해도가 향상된 것이다.   

#### #### 
동시에 일반 텍스트에 대한 PPL도 같이 측정해서, 일반 PPL이 크게 올라가면 catastrophic forgetting이 발생한 거라고 판단할 수 있다.
```
              도메인 PPL    일반 PPL
파인튜닝 전     15.3         8.1
파인튜닝 후      4.2         8.5   ← 일반 능력 유지, 도메인 향상 (좋음)
파인튜닝 후      4.2        25.0   ← catastrophic forgetting (나쁨)
```
한마디로 PPL은 "모델이 이 도메인 텍스트를 얼마나 자연스럽게 느끼는가"의 수치화이고, 파인튜닝 효과를 정량적으로 검증하는 가장 기본적인 방법이다.

### PPL 측정 ###
* https://github.com/gnosia93/agentic-ai-eks/blob/main/code/qwen_ppl.py 


## 파인튜닝 ##
* https://github.com/gnosia93/agentic-ai-eks/blob/main/code/qwen_finetune.py
