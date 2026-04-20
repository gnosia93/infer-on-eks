## lm-eval-harness ##

lm-evaluation-harness는 EleutherAI가 개발·공개한 대표적인 오픈소스 LLM 평가 프레임워크이다. MMLU, ARC, HellaSwag, TruthfulQA, GSM8K 등 수백 개의 벤치마크를 동일한 프롬프트 형식과 채점 규칙으로 돌려, 여러 모델의 성능을 공정하게 비교할 수 있다. HuggingFace 모델, vLLM 서버, OpenAI 호환 API 등 다양한 백엔드를 지원해 로컬 모델부터 상용 API까지 일관된 기준으로 평가할 수 있다는 점이 특징이다. 모델이 다음 토큰을 고를 때 평균 몇 개 후보 사이에서 헤매는가? 를 측정하는 언어 모델링 능력 (Perplexity) 측정 역시 가능하다. 
  - 일반 능력 
  - 언어 모델링 능력 (Perplexity)
    
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
```
[대상 모델]
 ├─ 오픈소스 모델 (GPU Pod)
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


### 1. HuggingFace 토큰 ###

* HF 계정 만들고 로그인
* gated 모델들 먼저 쭉 돌면서 "Agree and access" 전부 누르기 (Llama, Gemma, Mistral, Cohere...)
* 마지막에 Read 권한 토큰 하나 발급
* HF_TOKEN 환경변수나 huggingface-cli login으로 주입
* HF 토큰을 시크릿으로 생성
```
kubectl create secret generic hf-token \
  -n llm-eval \
  --from-literal=token=$HF_TOKEN
```

### 2. Manifest 다운로드 ###
```
curl -o vllm-eval.yaml \
https://raw.githubusercontent.com/gnosia93/eks-agentic-ai/refs/heads/main/code/eval/vllm-eval.yaml
```

### 3. 모델 테스트 ###
```
#!/bin/bash
# eval-all.sh
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

  # 함수 빠져나갈 때 port-forward 무조건 정리
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

  # 5. 도메인 평가
  python scripts/domain_eval.py --model "$name"

  # 6. vLLM 정리 (port-forward는 trap이 처리)
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

