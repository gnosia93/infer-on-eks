![](https://github.com/gnosia93/infer-on-eks/blob/main/images/diffusion-async.png)

생성 요청(POST /v1/generations)은 API 서버가 Job을 DB와 큐에 넣고 202 Accepted와 job_id를 돌려주면 끝난다. API 서버는 그 요청을 붙잡고 GPU 작업이 끝나기를 기다리지 않는다. HTTP keep-alive 때문에 TCP 연결은 재사용을 위해 잠시 열려 있을 수 있지만, 그 요청과 응답은 이미 끝난 상태이다.

결과는 클라이언트가 job_id로 새 요청을 보내서 받아간다. 방법은 세 가지 중에서 구현할 수 있다.


| 방식 | 동작 | 적합한 경우 |
| :--- | :--- | :--- |
| **Polling** | `GET /v1/generations/{id}`를 1~2초마다 호출 | 가장 단순해서 처음 만들 때(MVP) 적합 |
| **SSE** | `GET /v1/generations/{id}/events` 연결을 열어 두면 서버가 진행률과 완료를 push | 웹 화면에서 진행률 표시 |
| **Webhook** | 요청할 때 `callback_url`을 받아 두고, 완료되면 서버가 그 URL을 호출 | 서버 간 연동 |


### SSE 흐름 ###
```
POST /v1/generations              → 202 {"job_id": "abc"}       여기서 요청 종료
GET  /v1/generations/abc/events   (별도 연결, 열린 채 유지)
     ← event: progress {"step": 10, "total": 30}
     ← event: progress {"step": 20, "total": 30}
     ← event: completed {"result_url": "https://..."}           서버가 스트림 종료
GET  https://.../outputs/abc/0.webp                             이미지 다운로드
```

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

```
import json
import os
import time
import uuid
from contextlib import AsyncExitStack, asynccontextmanager

import aioboto3
import anyio
import asyncpg
import redis.asyncio as redis
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

# 접속 정보는 환경변수로만 받는다 (코드에 자격 증명을 넣지 않음)
DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ["REDIS_URL"]
RESULT_BUCKET = os.environ["RESULT_BUCKET"]  # 비공개 버킷. 결과는 presigned URL로만 제공

RETRY_MS = 3000        # 연결이 끊겼을 때 브라우저가 다시 연결하기까지의 간격
PING_INTERVAL = 15.0   # LB idle timeout(ALB 기본 60초)보다 짧게
POLL_TIMEOUT = 1.0     # 메시지가 없어도 1초마다 깨어나 클라이언트 연결 확인
URL_TTL = 600          # 결과 URL 유효 시간(초). 만료되면 GET /v1/generations/{id}로 재발급

TERMINAL = {"SUCCEEDED", "FAILED", "CANCELED"}

redis_client = redis.from_url(REDIS_URL, decode_responses=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncExitStack() as stack:
        app.state.db = await asyncpg.create_pool(DATABASE_URL)
        stack.push_async_callback(app.state.db.close)
        app.state.s3 = await stack.enter_async_context(aioboto3.Session().client("s3"))
        stack.push_async_callback(redis_client.aclose)
        yield

app = FastAPI(lifespan=lifespan)

async def get_current_user_id(request: Request) -> str:
    """세션 쿠키를 검증해 user_id를 반환한다.

    EventSource는 Authorization 헤더를 붙일 수 없으므로 쿠키 기반 세션을 검증해야 한다.
    실제 검증을 연결하기 전까지는 모든 요청을 401로 거부한다.
    """
    if os.environ.get("AUTH_TEST_BYPASS") == "1":  # 로컬 테스트 전용. 배포 환경에서는 켜지 않는다
        return "test-user"
    raise HTTPException(status_code=401)

async def load_job(db: asyncpg.Pool, job_id: uuid.UUID, user_id: str):
    # jobs(id UUID, user_id TEXT, status TEXT, result_key TEXT, error TEXT) 테이블 가정.
    # 본인 job만 조회하고, 남의 job은 없는 것과 똑같이 취급한다(404).
    return await db.fetchrow(
        "SELECT status, result_key, error FROM jobs WHERE id = $1 AND user_id = $2",
        job_id,
        user_id,
    )

def sse(event: str, data: dict) -> str:
    # json.dumps가 줄바꿈을 이스케이프하므로 data 한 줄로 안전하게 보낼 수 있다
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

async def completed_event(s3, result_key: str) -> str:
    url = await s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": RESULT_BUCKET, "Key": result_key},
        ExpiresIn=URL_TTL,
    )
    return sse("completed", {"result_url": url})

# 워커가 job:{job_id} 채널로 PUBLISH하는 메시지 형식.
# 워커는 반드시 DB 상태를 먼저 갱신한 뒤 PUBLISH해야 한다 (아래 2번 단계가 이 순서에 의존).
#   {"type": "progress", "step": 10, "total": 30}
#   {"type": "completed", "result_key": "outputs/<job_id>/0.webp"}
#   {"type": "failed", "error": "..."}
#   {"type": "canceled"}

@app.get("/v1/generations/{job_id}/events")
async def stream_job_events(
    job_id: uuid.UUID,
    request: Request,
    user_id: str = Depends(get_current_user_id),
):
    db, s3 = request.app.state.db, request.app.state.s3

    # 없는 job이면 스트림을 열기 전에 404. 200이 아닌 응답에는 브라우저가 재연결하지 않는다
    if await load_job(db, job_id, user_id) is None:
        raise HTTPException(status_code=404)

    channel = f"job:{job_id}"

    async def event_generator():
        pubsub = redis_client.pubsub()
        try:
            # 1. 채널 구독을 먼저 한다
            await pubsub.subscribe(channel)
            yield f"retry: {RETRY_MS}\n\n"

            # 2. 구독한 다음에 DB에서 현재 상태를 읽는다.
            #    구독 전에 끝난 job은 여기서, 구독 후에 끝난 job은 pubsub 메시지로 잡히므로 완료를 놓치지 않는다.
            #    재연결 요청도 이 경로를 타므로, 연결이 끊긴 동안 바뀐 상태를 여기서 따라잡는다.
            job = await load_job(db, job_id, user_id)
            if job is None:
                return
            if job["status"] == "SUCCEEDED":
                yield await completed_event(s3, job["result_key"])
                return
            if job["status"] in TERMINAL:
                yield sse("failed", {"status": job["status"], "error": job["error"]})
                return

            # 3. 워커 이벤트를 클라이언트로 중계한다
            last_sent = time.monotonic()
            while True:
                if await request.is_disconnected():
                    return

                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=POLL_TIMEOUT)
                if message is None:
                    if time.monotonic() - last_sent >= PING_INTERVAL:
                        yield ": ping\n\n"  # 주석 줄. 브라우저는 무시하고, 프록시는 연결이 살아 있다고 본다
                        last_sent = time.monotonic()
                    continue

                event = json.loads(message["data"])
                kind = event.get("type")

                if kind == "progress":
                    yield sse("progress", {"step": event["step"], "total": event["total"]})
                    last_sent = time.monotonic()
                elif kind == "completed":
                    yield await completed_event(s3, event["result_key"])
                    return
                elif kind in ("failed", "canceled"):
                    yield sse("failed", {"status": kind.upper(), "error": event.get("error")})
                    return
        finally:
            # 4. 구독 해제와 Redis 연결 반납. unsubscribe()만 하면 연결이 풀로 돌아가지 않는다.
            #    클라이언트가 끊어서 작업이 취소된 경우에도 정리가 끝까지 실행되도록 shield로 감싼다.
            with anyio.CancelScope(shield=True):
                await pubsub.aclose()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # nginx 같은 프록시가 이벤트를 모아 두지 않게 한다
        },
    )
```
