
### 테스트 대상 모델 ###
```
[대상 모델]
 ├─ 로컬 배포 (GPU Pod)
 │   ├─ Llama 3.1 8B
 │   ├─ Qwen 2.5 7B / 32B
 │   ├─ Gemma 2 9B
 │   └─ Mistral 7B
 └─ API 호출
     ├─ Claude 3.5 Sonnet (Bedrock)
     ├─ Claude 3 Haiku (Bedrock)
     └─ Llama 3.1 70B (Bedrock)
```


### Bedrock 접근 준비 ###

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
