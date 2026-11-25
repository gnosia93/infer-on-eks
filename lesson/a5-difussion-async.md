![](https://github.com/gnosia93/infer-on-eks/blob/main/images/diffusion-async.png)

생성 요청(POST /v1/generations)은 API 서버가 Job을 DB와 큐에 넣고 202 Accepted와 job_id를 돌려주면 끝난다. API 서버는 그 요청을 붙잡고 GPU 작업이 끝나기를 기다리지 않는다. HTTP keep-alive 때문에 TCP 연결은 재사용을 위해 잠시 열려 있을 수 있지만, 그 요청과 응답은 이미 끝난 상태이다.

결과는 클라이언트가 job_id로 새 요청을 보내서 받아간다. 방법은 세 가지 중에서 구현할 수 있다.


| 방식 | 동작 | 적합한 경우 |
| :--- | :--- | :--- |
| **Polling** | `GET /v1/generations/{id}`를 1~2초마다 호출 | 가장 단순해서 처음 만들 때(MVP) 적합 |
| **SSE** | `GET /v1/generations/{id}/events` 연결을 열어 두면 서버가 진행률과 완료를 push | 웹 화면에서 진행률 표시 |
| **Webhook** | 요청할 때 `callback_url`을 받아 두고, 완료되면 서버가 그 URL을 호출 | 서버 간 연동 |


### API 서버 ###
```
import asyncio
import json
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
import redis.asyncio as redis

app = FastAPI()
redis_client = redis.from_url("redis://localhost:6379")

@app.get("/stream/{job_id}")
async def stream_image_status(job_id: str, request: Request):
    async def event_generator():
        # 1. Redis에서 해당 job_id 채널 구독
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(f"job:{job_id}")

        try:
            while True:
                # 클라이언트가 브라우저를 닫았는지 확인
                if await request.is_disconnected():
                    break

                # 2. 워커가 보낸 메시지가 있는지 대기 (15초 타임아웃으로 연결 유지용 핑 전송)
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15.0)
                
                if message:
                    # 3. 완료 신호 수신 시 클라이언트로 데이터 전송 후 종료
                    data = message["data"].decode("utf-8")
                    yield f"data: {data}\n\n"
                    break
                else:
                    # 타임아웃 방지용 빈 신호 (Keep-alive)
                    yield ": ping\n\n"
                    
        finally:
            # 4. 연결 종료 시 Redis 구독 해제 (메모리 누수 방지)
            await pubsub.unsubscribe(f"job:{job_id}")

    # 일반 JSON 대신 text/event-stream 형태로 응답 반환
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```
