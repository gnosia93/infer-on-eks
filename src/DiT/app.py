import io
import json
import os
import time
import uuid
from contextlib import AsyncExitStack, asynccontextmanager

import aioboto3
import anyio
import asyncpg
import redis.asyncio as redis
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from redis.exceptions import RedisError, ResponseError

# 접속 정보는 환경변수로만 받는다 (코드에 자격 증명을 넣지 않음)
DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ["REDIS_URL"]
IMAGE_BUCKET = os.environ["IMAGE_BUCKET"]  # inputs/, outputs/ 프리픽스로 나눠 쓰는 비공개 버킷

JOB_STREAM = "generation_jobs"  # 작업 큐 (Redis Stream)
WORKER_GROUP = "gpu_workers"    # GPU 워커가 job을 나눠 가져가는 consumer group

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_SIDE = 2048
IMAGE_FORMATS = {  # Pillow 포맷 이름 → (확장자, Content-Type)
    "PNG": ("png", "image/png"),
    "JPEG": ("jpg", "image/jpeg"),
    "WEBP": ("webp", "image/webp"),
}

RETRY_MS = 3000        # 연결이 끊겼을 때 브라우저가 다시 연결하기까지의 간격
PING_INTERVAL = 15.0   # LB idle timeout(ALB 기본 60초)보다 짧게
POLL_TIMEOUT = 1.0     # 메시지가 없어도 1초마다 깨어나 클라이언트 연결 확인
URL_TTL = 600          # 결과 URL 유효 시간(초). 만료되면 GET /v1/generations/{id}로 재발급

TERMINAL = {"SUCCEEDED", "FAILED", "CANCELED"}

# decode_responses=True라서 메시지를 직접 .decode("utf-8") 할 필요가 없다
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncExitStack() as stack:
        app.state.db = await asyncpg.create_pool(DATABASE_URL)
        stack.push_async_callback(app.state.db.close)
        app.state.s3 = await stack.enter_async_context(aioboto3.Session().client("s3"))
        stack.push_async_callback(redis_client.aclose)

        # 워커보다 API가 먼저 떠도 job이 빠지지 않도록 consumer group을 미리 만든다 (id="0": 처음부터 읽기)
        try:
            await redis_client.xgroup_create(JOB_STREAM, WORKER_GROUP, id="0", mkstream=True)
        except ResponseError as e:
            if "BUSYGROUP" not in str(e):  # 이미 있으면 그대로 사용
                raise
        yield

app = FastAPI(lifespan=lifespan)

# ---------- 워커와 주고받는 메시지 형식 ----------
# 큐 (API → 워커): XADD generation_jobs  job_id, mode, params(JSON), input_key
# 이벤트 (워커 → API): PUBLISH job:{job_id}
#   {"type": "progress", "step": 10, "total": 30}
#   {"type": "completed", "result_key": "outputs/<job_id>/0.webp"}
#   {"type": "failed", "error": "..."}
#   {"type": "canceled"}
# 워커는 반드시 DB 상태를 먼저 갱신한 뒤 PUBLISH해야 한다 (SSE의 2번 단계가 이 순서에 의존).

# ---------- 공통 ----------

async def get_current_user_id(request: Request) -> str:
    """세션 쿠키를 검증해 user_id를 반환한다.

    EventSource는 Authorization 헤더를 붙일 수 없으므로 쿠키 기반 세션을 검증해야 한다.
    실제 검증을 연결하기 전까지는 모든 요청을 401로 거부한다.
    """
    if os.environ.get("AUTH_TEST_BYPASS") == "1":  # 로컬 테스트 전용. 배포 환경에서는 켜지 않는다
        return "test-user"
    raise HTTPException(status_code=401)

async def load_job(db: asyncpg.Pool, job_id: uuid.UUID, user_id: str):
    # 본인 job만 조회하고, 남의 job은 없는 것과 똑같이 취급한다(404)
    return await db.fetchrow(
        "SELECT status, result_key, error FROM jobs WHERE id = $1 AND user_id = $2",
        job_id,
        user_id,
    )

async def presign_result(s3, result_key: str) -> str:
    return await s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": IMAGE_BUCKET, "Key": result_key},
        ExpiresIn=URL_TTL,
    )

def inspect_image(data: bytes) -> str:
    """업로드된 이미지의 포맷과 크기를 확인한다. 픽셀 데이터는 디코딩하지 않는다."""
    try:
        with Image.open(io.BytesIO(data)) as im:
            fmt, (width, height) = im.format, im.size
            im.verify()
    except Exception as e:  # 이미지가 아니거나, 깨졌거나, 해상도가 비정상적으로 큰 파일
        raise ValueError("이미지 파일을 읽을 수 없습니다") from e
    if fmt not in IMAGE_FORMATS:
        raise ValueError("PNG, JPEG, WEBP만 지원합니다")
    if width > MAX_IMAGE_SIDE or height > MAX_IMAGE_SIDE:
        raise ValueError(f"이미지 가로·세로는 {MAX_IMAGE_SIDE}px 이하여야 합니다")
    return fmt

# ---------- 생성 요청: POST /v1/generations ----------

@app.post("/v1/generations", status_code=202)
async def create_generation(
    request: Request,
    prompt: str = Form("", max_length=1000),
    negative_prompt: str = Form("", max_length=1000),
    width: int = Form(1024, ge=256, le=1536, multiple_of=8),   # txt2img 출력 크기
    height: int = Form(1024, ge=256, le=1536, multiple_of=8),
    steps: int = Form(30, ge=1, le=50),
    guidance_scale: float = Form(7.0, ge=0.0, le=20.0),
    strength: float = Form(0.6, gt=0.0, le=1.0),                 # img2img: 원본을 얼마나 바꿀지
    seed: int | None = Form(None, ge=0, le=2**32 - 1),
    image: UploadFile | None = File(None),
    user_id: str = Depends(get_current_user_id),
):
    db, s3 = request.app.state.db, request.app.state.s3

    # 1. 입력 검증. 텍스트와 이미지 중 하나는 있어야 한다
    data = await image.read(MAX_IMAGE_BYTES + 1) if image is not None else b""
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="이미지는 10MB 이하여야 합니다")
    if not prompt.strip() and not data:
        raise HTTPException(status_code=422, detail="prompt와 image 중 하나는 필요합니다")

    job_id = uuid.uuid4()
    mode = "img2img" if data else "txt2img"
    params = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "steps": steps,
        "guidance_scale": guidance_scale,
        "seed": seed,
    }
    if mode == "txt2img":
        params.update(width=width, height=height)
    else:
        params["strength"] = strength

    # 2. 입력 이미지를 검사하고 S3에 저장. Pillow는 동기 코드라 스레드에서 돌려 이벤트 루프를 막지 않는다
    input_key = None
    if data:
        try:
            fmt = await run_in_threadpool(inspect_image, data)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
        ext, content_type = IMAGE_FORMATS[fmt]
        input_key = f"inputs/{job_id}.{ext}"
        await s3.put_object(Bucket=IMAGE_BUCKET, Key=input_key, Body=data, ContentType=content_type)

    # 3. DB에 job 생성. 큐보다 먼저 넣어야 워커와 SSE가 job을 못 찾는 일이 없다
    await db.execute(
        "INSERT INTO jobs (id, user_id, status, mode, params, input_key) "
        "VALUES ($1, $2, 'QUEUED', $3, $4, $5)",
        job_id,
        user_id,
        mode,
        json.dumps(params, ensure_ascii=False),
        input_key,
    )

    # 4. 큐에 적재. 실패하면 job을 FAILED로 바꿔 QUEUED 상태로 영원히 남지 않게 한다
    try:
        await redis_client.xadd(
            JOB_STREAM,
            {
                "job_id": str(job_id),
                "mode": mode,
                "params": json.dumps(params, ensure_ascii=False),
                "input_key": input_key or "",
            },
        )
    except RedisError:
        await db.execute(
            "UPDATE jobs SET status = 'FAILED', error = 'enqueue failed' WHERE id = $1", job_id
        )
        raise HTTPException(status_code=503, detail="잠시 후 다시 시도해 주세요")

    # 5. GPU 작업을 기다리지 않고 바로 202 응답. 이 요청은 여기서 끝난다
    return {
        "job_id": str(job_id),
        "status": "QUEUED",
        "status_url": f"/v1/generations/{job_id}",
        "events_url": f"/v1/generations/{job_id}/events",
    }

# ---------- 상태 조회 (polling): GET /v1/generations/{job_id} ----------

@app.get("/v1/generations/{job_id}")
async def get_generation(
    job_id: uuid.UUID,
    request: Request,
    user_id: str = Depends(get_current_user_id),
):
    job = await load_job(request.app.state.db, job_id, user_id)
    if job is None:
        raise HTTPException(status_code=404)

    body = {"job_id": str(job_id), "status": job["status"]}
    if job["status"] == "SUCCEEDED":
        body["result_url"] = await presign_result(request.app.state.s3, job["result_key"])
    elif job["status"] in TERMINAL:
        body["error"] = job["error"]
    return body

# ---------- 진행률 스트림 (SSE): GET /v1/generations/{job_id}/events ----------

def sse(event: str, data: dict) -> str:
    # json.dumps가 줄바꿈을 이스케이프하므로 data 한 줄로 안전하게 보낼 수 있다
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

async def completed_event(s3, result_key: str) -> str:
    return sse("completed", {"result_url": await presign_result(s3, result_key)})

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
            # 1. Redis에서 해당 job_id 채널을 먼저 구독한다
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

            # 3. 워커가 보낸 메시지를 클라이언트로 중계한다
            last_sent = time.monotonic()
            while True:
                # 클라이언트가 브라우저를 닫았는지 확인
                if await request.is_disconnected():
                    return

                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=POLL_TIMEOUT)
                if message is None:
                    # 타임아웃 방지용 빈 신호 (Keep-alive). 주석 줄이라 브라우저는 무시한다
                    if time.monotonic() - last_sent >= PING_INTERVAL:
                        yield ": ping\n\n"
                        last_sent = time.monotonic()
                    continue

                event = json.loads(message["data"])
                kind = event.get("type")

                if kind == "progress":
                    yield sse("progress", {"step": event["step"], "total": event["total"]})
                    last_sent = time.monotonic()
                elif kind == "completed":
                    # 완료 신호 수신 시 결과 URL을 보내고 종료
                    yield await completed_event(s3, event["result_key"])
                    return
                elif kind in ("failed", "canceled"):
                    yield sse("failed", {"status": kind.upper(), "error": event.get("error")})
                    return
        finally:
            # 4. 연결 종료 시 구독 해제와 Redis 연결 반납. unsubscribe()만 하면 연결이 풀로 돌아가지 않는다.
            #    클라이언트가 끊어서 작업이 취소된 경우에도 정리가 끝까지 실행되도록 shield로 감싼다.
            with anyio.CancelScope(shield=True):
                await pubsub.aclose()

    # 일반 JSON 대신 text/event-stream 형태로 응답 반환
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # nginx 같은 프록시가 이벤트를 모아 두지 않게 한다
        },
    )

# 정적 파일(index.html, app.js) 서빙. API 라우트를 모두 정의한 뒤 맨 마지막에 마운트한다.
# 먼저 마운트하면 "/"가 API 경로까지 가로챈다. static 폴더가 없으면 서버 시작 시 에러가 난다.
app.mount("/", StaticFiles(directory="static", html=True), name="static")
