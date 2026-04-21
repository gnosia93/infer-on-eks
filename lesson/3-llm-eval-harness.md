## lm-eval-harness ##

lm-evaluation-harness는 EleutherAI가 개발·공개한 대표적인 오픈소스 LLM 평가 프레임워크로 `언어 모델의 일반 능력`과 `언어 모델링 능력(Perplexity)` 측정이 가능하다.  HuggingFace 모델, vLLM 서버, OpenAI 호환 API 등 다양한 백엔드를 지원해 로컬 모델부터 상용 API까지 일관된 기준으로 평가할 수 있다는 점이 특징이다. 
- 일반 능력 : MMLU, ARC, HellaSwag, TruthfulQA, GSM8K 등 수백 개의 벤치마크를 동일한 프롬프트 형식과 채점 규칙으로 돌려, 여러 모델의 성능을 공정하게 비교. 
- 언어 모델링 능력 (Perplexity) :
  모델이 실제 텍스트를 얼마나 "예상 밖"이라고 느끼는지를 재는 지표로 수식적으로는 모델이 텍스트 각 토큰에 부여한 확률의 기하평균의 역수로 정의되며, "모델이 다음 토큰을 고를 때 평균 몇 개 후보 사이에서 헤매는가" 로 직관적으로 해석할 수 있다. 값이 낮을수록 모델이 해당 텍스트 분포에 익숙하다는 뜻이며, 학습 진행도 체크, 도메인 적합도 비교, 모델 간 언어 능력 비교에 두루 쓰인다. 단, Claude·GPT-4o 같은 상용 API 모델은 logprobs를 제공하지 않아 측정이 불가능하며, 오픈 웨이트 모델을 vLLM 등으로 직접 호스팅해야 한다
    
### 주요 벤치마크 ###
#### MMLU (Massive Multitask Language Understanding) ####
수학, 역사, 법학, 의학, 컴퓨터과학 등 57개 분야에 걸친 약 14,000개의 객관식 문제로 구성된 벤치마크로 중·고등학생 수준부터 전문가 수준까지 난이도가 다양해, 모델이 얼마나 폭넓은 지식과 전문 분야의 추론 능력을 갖췄는지 측정한다. LLM 성능을 논할 때 가장 먼저 언급되는 대표적인 지표이다.

* 측정 영역: 지식 범위, 학문적 추론
* 형식: 4지선다 객관식
* 점수: Accuracy (%)

#### ARC (AI2 Reasoning Challenge) ####
Allen Institute for AI가 만든 초·중학 과학 문제 벤치마크로, 쉬운 문제를 모은 ARC-Easy와 단순 암기로 못 푸는 ARC-Challenge 두 세트로 나뉜다. 특히 ARC-Challenge는 여러 단서를 조합해 추론해야 풀리는 문제들로 구성되어, 모델의 논리적 추론 능력을 평가하는 데 널리 쓰인다.

* 측정 영역: 과학적 추론, 상식 기반 논리
* 형식: 4지선다 객관식
* 주요 변형: ARC-Easy, ARC-Challenge (난이도 높음)

#### HellaSwag ####
주어진 상황 설명 뒤에 이어질 가장 자연스러운 문장을 네 개의 선택지 중 고르는 상식 추론 벤치마크이다. 사람에게는 쉽지만 모델에게는 까다롭게 만들어진 문제들이라, 일상 상식과 문맥 이해력을 재는 데 적합하다. 문제의 선택지가 기계 생성 + 사람 검증으로 설계되어, 단순 패턴 매칭으로는 풀기 어렵도록 구성돼 있다.

* 측정 영역: 상식, 문맥적 자연스러움 판단
* 형식: 문장 완성형 4지선다

#### TruthfulQA ####
사람들이 흔히 오해하거나 잘못 알고 있는 주제들에 대해 모델이 얼마나 사실과 다른 답변(hallucination)을 피할 수 있는지 측정하는 벤치마크이다. 예를 들어 미신, 도시전설, 잘못된 상식 같은 함정 질문에 모델이 쉽게 넘어가지 않는지를 평가한다. 단순 지식보다 답변의 진실성(truthfulness) 에 초점을 둔 독특한 지표이다.

* 측정 영역: 사실성, 환각 저항력
* 형식: 객관식(MC1/MC2) 또는 생성형
* 주의: 점수 높다고 반드시 "진실된 답"을 생성한다는 보장은 없음 (선택지 판별 능력 측정)

#### GSM8K (Grade School Math 8K) ####
OpenAI가 공개한 초등 수준의 단계별 수학 문제 8,500개로 구성된 벤치마크이다. 사칙연산 자체는 어렵지 않지만 문제를 읽고 풀이 과정을 여러 단계로 추론해야 해서, 모델의 Chain-of-Thought(연쇄적 사고) 능력을 평가하는 표준 지표로 자리잡았다. 숫자만 맞히는 게 아니라 풀이 과정의 논리를 보는 평가에도 자주 활용된다.

* 측정 영역: 수학 추론, 단계적 사고
* 형식: 서술형 답 (최종 숫자 매칭)
* 평가 방식: 정답 숫자 일치 또는 풀이 과정 채점

### 추가 벤치마크 (필요시) ###
* `Winogrande`
문장 속 대명사가 가리키는 대상을 고르는 상식 기반 공지시 해결(coreference resolution) 벤치마크이다. "상을 받은 사람은 기뻐했다. 그/그녀는 누구인가?" 같은 문제로, 겉보기엔 간단하지만 세상에 대한 배경 지식이 있어야 풀 수 있다.

* `HumanEval / MBPP`
코드 생성 능력을 평가하는 벤치마크로, 함수 시그니처와 설명을 주고 실행 가능한 파이썬 코드를 작성하게 한 뒤, 테스트 케이스 통과 여부로 채점한다. pass@k 지표(k번 시도 중 하나라도 통과하는 비율)로 측정한다.

* `MT-Bench`
80개의 다중 턴 대화 질문에 대해 GPT-4 같은 강한 모델이 답변 품질을 1~10점으로 채점하는 벤치마크로, 객관식 정답이 아닌 대화 품질·유용성을 재는 LLM-as-a-Judge 방식의 대표 예이다.

* `BBH (BIG-Bench Hard)`
BIG-Bench 중에서도 특히 어려운 23개 태스크를 추린 세트로 논리 퍼즐, 기호 추론, 복잡한 지시 따르기 등 모델의 고차원 추론을 평가한다.

* `MATH`
고등학교~대학 경시 수준의 본격적인 수학 문제 12,500개. GSM8K보다 훨씬 어렵고, 수식 전개와 증명 능력까지 요구한다.


### 평가 대상 모델 ###
본 워크샵에서는 아래의 모델들에 대한 평가를 수행할 예정이다.
```
[대상 모델]
 ├─ 오픈소스 모델
 │   ├─ Llama 3.1 8B
 │   ├─ Qwen 2.5 7B / 32B
 │   ├─ Gemma 2 9B
 │   └─ Mistral 7B
 └─ API 호출
     ├─ Claude 3.5 Sonnet (Bedrock)
     ├─ Claude 3 Haiku (Bedrock)
     └─ Llama 3.1 70B (Bedrock)
```

## 오픈소스 모델 ##
오픈 소스 모델중 일부는 HF_TOKEN 정보를 필요로 하는 gated 모델이다.

### 1. HuggingFace 토큰 생성 ###
* HF 계정 만들고 로그인
* gated 모델들 먼저 쭉 돌면서 "Agree and access" 전부 누르기 (Llama, Gemma, Mistral, Cohere...)
* 마지막에 Read 권한 토큰 하나 발급
* HF_TOKEN 환경변수나 huggingface-cli login으로 주입
* HF 토큰을 시크릿으로 생성
```
kubectl create secret generic hf-token -n llm-eval \
  --from-literal=token=$HF_TOKEN
```

### 2. Manifest 다운로드 ###
```
mkdir eval && cd eval
pip install lm-eval
kubectl create ns llm-eval
kubectl create serviceaccount llm-eval-sa -n llm-eval

curl -o vllm-eval.yaml \
https://raw.githubusercontent.com/gnosia93/eks-agentic-ai/refs/heads/main/code/eval/vllm-eval.yaml
```

### 3. 모델 테스트 (스크립트) ###
```
cat << 'EOF' > eval-all.sh
#!/bin/bash
set -euo pipefail

MODELS=(
  "Qwen/Qwen2.5-7B-Instruct"
  "meta-llama/Llama-3.1-8B-Instruct"
  "google/gemma-2-9b-it"
  "mistralai/Mistral-7B-Instruct-v0.3"
  "CohereLabs/c4ai-command-r7b-12-2024"
)

run_eval() {
  local model="$1"
  local name="$2"
  local manifest="vllm-eval-${name}.yaml"
  local pf_pid=""

  # 함수 빠져나갈 때 port-forward 설정을 정리
  cleanup_pf() {
    if [[ -n "$pf_pid" ]]; then
      kill "$pf_pid" 2>/dev/null || true
      wait "$pf_pid" 2>/dev/null || true
      pf_pid=""
    fi
  }
  trap cleanup_pf RETURN

  echo "=== [$(date +%T)] $model ==="

  # 1. vLLM 매니페스트 생성 및 배포
  export MODEL="$model"
  envsubst < vllm-eval.yaml > "$manifest"
  kubectl apply -f "$manifest"

  # 2. Ready 대기
  if ! kubectl -n llm-eval rollout status deploy/vllm-eval --timeout=600s; then
    echo "!! rollout failed for $model"
    kubectl -n llm-eval logs deploy/vllm-eval --tail=100 || true
    kubectl delete -f "$manifest" --ignore-not-found
    return 1
  fi

  # 3. port-forward 기동
  kubectl -n llm-eval port-forward svc/vllm-eval 8000:8000 >/dev/null 2>&1 &
  pf_pid=$!
  sleep 3

  # 4. lm-eval-harness 실행 (localhost로)
  # 4-a. 지식/추론 벤치 (chat completions)
  lm_eval \
    --model local-chat-completions \
    --model_args "model=${model},base_url=http://localhost:8000/v1/chat/completions" \
    --tasks mmlu,arc_challenge,hellaswag \
    --output_path "results/${name}"
  
  # 4-b. 언어 모델링 (completions + logprobs)
  lm_eval \
    --model local-completions \
    --model_args "model=${model},base_url=http://localhost:8000/v1/completions,tokenizer_backend=huggingface,tokenized_requests=False" \
    --tasks wikitext,lambada_openai \
    --output_path "results/${name}-ppl"

  # 5. vLLM 정리 (port-forward는 trap이 처리)
  kubectl delete -f "$manifest" --ignore-not-found
}

for MODEL in "${MODELS[@]}"; do
  NAME=$(echo "${MODEL##*/}" | tr '[:upper:]' '[:lower:]')
  if ! run_eval "$MODEL" "$NAME"; then
    echo "!! skipping $MODEL, continuing with next"
    continue
  fi
done
echo "=== all evaluations complete ==="
EOF
```
평가를 실행한다.
```
bash eval-all.sh
```


### 4. 결과 확인 ###
`결과 테이블로 출력`:
```
python -m lm_eval.utils.zeno_visualize --data_path results/
```

`또는 간단히 jq로`:
```
for f in results/*/*/results_*.json; do
  model=$(jq -r '.model_name' "$f")
  mmlu=$(jq -r '.results.mmlu."acc,none"' "$f")
  arc=$(jq -r '.results.arc_challenge."acc_norm,none"' "$f")
  hella=$(jq -r '.results.hellaswag."acc_norm,none"' "$f")
  printf "%-40s mmlu=%.4f arc=%.4f hella=%.4f\n" "$model" "$mmlu" "$arc" "$hella"
done
```

## 허깅페이스 라이브러리를 활용한 PPL 측정 ##
아래 예제는 qwen 모델의 PPL 을 허깅페이스 API 로 측정하는 방법이다. 
![](https://github.com/gnosia93/agentic-ai-eks/blob/main/lesson/images/qwen-ppl.png)
* https://github.com/gnosia93/agentic-ai-eks/blob/main/code/qwen_ppl.py 

## 참고 - Perplexity(PPL) ##
언어모델이 다음 토큰을 얼마나 잘 예측하는지 측정하는 지표라, "자연스러운 텍스트 코퍼스" 하나에 대해 쭉 읽히면서 loss를 재는 방식이다. 그래서 "벤치마크"라기보단 "평가용 코퍼스"에 가깝다.

### 영어권의 표준 데이터셋 ###
* WikiText-2 / WikiText-103: 위키피디아 good/featured 문서로 만든 데이터셋. 논문에서 제일 많이 보임. WikiText-2는 작고 빠른 스모크 테스트용, WikiText-103은 본격 측정용. HF: wikitext
* Penn Treeboank (PTB): 옛날부터 쓰던 고전. 요즘 LLM 논문에선 잘 안 쓰지만 여전히 언급은 됨. 크기가 작고 전처리가 강해서 현대 LLM 평가엔 살짝 부적절
* C4: T5 학습에 쓰인 웹 크롤 코퍼스. Common Crawl 정제본. 큰 규모라 일부 샘플링해서 측정
* The Pile: EleutherAI가 만든 825GB 멀티도메인 코퍼스 (책, 논문, 코드, 위키 등 22개 서브셋). 서브셋별 PPL을 따로 보는 경우도 많음
* LAMBADA: 마지막 단어를 맞추는 문맥 이해 평가. PPL도 재지만 accuracy가 더 중요한 지표. HF: lambada
* PG-19: Project Gutenberg의 장문 소설. 긴 컨텍스트 평가용
* RedPajama / SlimPajama: LLaMA 재현용으로 만든 오픈 대형 코퍼스. 일부를 validation으로 써서 PPL 측정

### 양자화/압축 논문에서 사실상 표준 ###
GPTQ, AWQ, SmoothQuant 같은 논문들은 거의 항상 아래의 조합을 사용한다.

* WikiText-2
* C4 (validation split)
* PTB (가끔)
이 세 개의 PPL로, 양자화 전후로 모델이 얼마나 안 망가졌는지 보는 게 관례이다.

### 긴 컨텍스트 평가 ###

* PG-19: 장문 소설
* GovReport, ArXiv: 긴 문서
* Needle-in-a-Haystack: 엄밀히는 PPL 아니고 검색 성공률이지만 long-context 평가에서 자주 같이 언급됨

### 한국어 ###

* KLUE: 종합 벤치마크인데 PPL 직접 측정보다는 downstream task 위주
* 나무위키 / 한국어 위키: 직접 받아서 쓰는 경우가 많음. 표준화된 split이 있진 않아요
* KoWiki, Modu (국립국어원 모두의 말뭉치): 한국어 PPL 측정에 자주 동원됨

> [!NOTE]
> PPL은 토크나이저가 다르면 절대 비교가 불가하고 같은 모델 계열끼리만 의미가 있다. 예를들어 LLaMA끼리, Qwen끼리 이런 식이다.
> 그래서 요즘은 "모델 성능 평가"로는 PPL보다 MMLU, HellaSwag, GSM8K 같은 downstream 벤치를 더 신뢰한다. PPL은 주로 "양자화/프루닝 후에 분포가 덜 망가졌나"를 보는 용도로 남아있다.
> 데이터셋 오염(contamination) 이슈 때문에 최근 모델은 WikiText 같은 공개 코퍼스의 PPL이 비정상적으로 낮게 나올 수 있어 해석할 때 주의가 필요하다.


## 레퍼런스 ##

* https://artificialanalysis.ai/leaderboards/models
