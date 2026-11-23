
### 1. S3 모델 업로드 ###

```
# FP8 체크포인트를 받아 S3에 한 번 올립니다. 예비 버전이라 커밋을 고정하세요.
hf download RedHatAI/gemma-4-12B-it-FP8-Dynamic \
  --revision <COMMIT_SHA> \
  --local-dir ./gemma-4-12B-it-FP8-Dynamic

aws s3 sync ./gemma-4-12B-it-FP8-Dynamic \
  s3://<MODEL_BUCKET>/models/gemma-4-12B-it-FP8-Dynamic \
  --exclude ".cache/*"
```

### 2. ###
```
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::<MODEL_BUCKET>",
      "Condition": {
        "StringLike": {
          "s3:prefix": [
            "models/gemma-4-12B-it-FP8-Dynamic",
            "models/gemma-4-12B-it-FP8-Dynamic/*"
          ]
        }
      }
    },
    {
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::<MODEL_BUCKET>/models/gemma-4-12B-it-FP8-Dynamic/*"
    }
  ]
}
```
