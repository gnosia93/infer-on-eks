lm-evaluation-harness는 EleutherAI가 개발·공개한 대표적인 오픈소스 LLM 평가 프레임워크이다. MMLU, ARC, HellaSwag, TruthfulQA, GSM8K 등 수백 개의 벤치마크를 동일한 프롬프트 형식과 채점 규칙으로 돌려, 여러 모델의 성능을 공정하게 비교할 수 있다. HuggingFace 모델, vLLM 서버, OpenAI 호환 API 등 다양한 백엔드를 지원해 로컬 모델부터 상용 API까지 일관된 기준으로 평가할 수 있다는 점이 특징이다.


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
Llama, Gemma 등 승인 필요한 모델은 HF 토큰 시크릿으로 제공:
```
kubectl create secret generic hf-token \
  -n llm-eval \
  --from-literal=token=$HF_TOKEN
```

### 2. Deployment 다운로드 ###
```
curl -o vllm-eval.yaml \
https://raw.githubusercontent.com/gnosia93/eks-agentic-ai/refs/heads/main/code/eval/vllm-eval.yaml
```

### 3. 모델 테스트 ###
```
#!/bin/bash
# eval-all.sh

MODELS=(
  "Qwen/Qwen2.5-7B-Instruct"
  "meta-llama/Llama-3.1-8B-Instruct"
  "google/gemma-2-9b-it"
)

for MODEL in "${MODELS[@]}"; do
  NAME=$(echo $MODEL | tr '/' '-' | tr '[:upper:]' '[:lower:]')
  echo "=== $MODEL ==="

  # 1. vLLM 기동
  envsubst < vllm-eval.yaml > vllm-eval-${MODEL}.yaml
  kubectl apply -f vllm-eval-${MODEL}.yaml

  # 2. Ready 될 때까지 대기
  kubectl -n llm-eval rollout status deploy/vllm-current --timeout=600s

  # 3. 평가 실행 (CPU Pod에서)
  lm_eval --model local-chat-completions \
    --model_args model=$MODEL,base_url=http://vllm-current:8000/v1/chat/completions \
    --tasks mmlu,arc_challenge,hellaswag \
    --output_path /results/$NAME

  # 4. 다른 평가들도 실행
  python /scripts/domain_eval.py --model $NAME

  # 5. vLLM 내림
  kubectl delete -f vllm-eval-${MODEL}.yaml
done
```

```
# 변수 설정
export MODEL="Qwen/Qwen2.5-7B-Instruct"

# 적용 (템플릿 치환)
envsubst < vllm-l40s.yaml | kubectl apply -f -

# 로딩 로그 보기
kubectl -n llm-eval logs -f deploy/vllm-current

# Ready 확인
kubectl -n llm-eval rollout status deploy/vllm-current --timeout=900s
```

```
# Port-forward
kubectl -n llm-eval port-forward svc/vllm-current 8000:8000

# 다른 터미널
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen2.5-7B-Instruct",
    "messages": [{"role": "user", "content": "안녕?"}],
    "max_tokens": 50
  }'
```


## Bedrock 모델 ##

IRSA로 평가 Pod에 권한 부여:
```
cat > bedrock-eval-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
      "bedrock:Converse",
      "bedrock:ConverseStream"
    ],
    "Resource": "*"
  }]
}
EOF

aws iam create-policy \
  --policy-name LLMEvalBedrockAccess \
  --policy-document file://bedrock-eval-policy.json

eksctl create iamserviceaccount \
  --cluster=$CLUSTER_NAME \
  --namespace=llm-eval \
  --name=llm-eval-sa \
  --attach-policy-arn=arn:aws:iam::${ACCOUNT_ID}:policy/LLMEvalBedrockAccess \
  --approve
```


