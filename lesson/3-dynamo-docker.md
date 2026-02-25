### Docker 로 실행하기 ###

프롬프트 템플릿 적용, 토큰화(Tokenization), 그리고 라우팅 기능을 갖춘 OpenAI 호환 HTTP 서버를 시작한다.
--discovery-backend file 옵션을 사용하면 etcd(분산 설정 저장소) 설치 없이도 구동이 가능하다. 단, 이 경우 워커와 프론트엔드가 반드시 동일한 디스크 공간을 공유해야 한다.

```bash
docker run --gpus all --network host --rm -it nvcr.io/nvidia/ai-dynamo/tensorrtllm-runtime:0.8.1

python3 -m dynamo.frontend --http-port 8000 --discovery-backend file & 

python3 -m dynamo.trtllm --model-path Qwen/Qwen3-0.6B --discovery-backend file
```

curl 이용하여 인퍼런스 한다. 
```bash
curl localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3-0.6B",
    "messages": [
      {
        "role": "user",
        "content": "Hello, how are you?"
      }
    ],
    "stream": false,
    "max_tokens": 300
  }' | jq
```
curl 이용하여 streaming 모드로 인퍼런스 한다.
```bash
# -N 옵션은 curl이 데이터를 버퍼링하지 않고 즉시 출력하게 합니다.
curl -N localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3-0.6B",
    "messages": [{"role": "user", "content": "긴 이야기를 하나 해줘"}],
    "stream": true
  }'
```

