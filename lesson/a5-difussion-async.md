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
project/
├── app.py
└── static/
    ├── index.html
    └── app.js
```

* app.py
```

```  

* static/index.html
```
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <title>Image Generator</title>
</head>
<body>
  <form id="form">
    <input id="prompt" placeholder="프롬프트" required>
    <input id="image" type="file" accept="image/png,image/jpeg,image/webp">
    <button>생성</button>
  </form>
  <progress id="bar" max="1" value="0"></progress>
  <p id="status"></p>
  <img id="result" alt="">
  <script src="/app.js"></script>
</body>
</html>
```
* static/app.js
```
const form = document.getElementById("form");
const bar = document.getElementById("bar");
const statusEl = document.getElementById("status");
const result = document.getElementById("result");

form.addEventListener("submit", async (e) => {
  e.preventDefault();

  // 1. 생성 요청: 텍스트와 선택적 입력 이미지를 multipart로 전송
  const body = new FormData();
  body.append("prompt", document.getElementById("prompt").value);
  const file = document.getElementById("image").files[0];
  if (file) body.append("image", file);

  const res = await fetch("/v1/generations", { method: "POST", body });
  if (res.status !== 202) {
    statusEl.textContent = `요청 실패: ${res.status}`;
    return;
  }
  const { job_id } = await res.json();

  // 2. 받은 job_id로 진행률 구독
  watch(job_id);
});

function watch(jobId) {
  const es = new EventSource(`/v1/generations/${jobId}/events`);

  es.addEventListener("progress", (e) => {
    const { step, total } = JSON.parse(e.data);
    bar.value = step / total;
    statusEl.textContent = `생성 중 ${step}/${total}`;
  });

  es.addEventListener("completed", (e) => {
    result.src = JSON.parse(e.data).result_url;
    statusEl.textContent = "완료";
    es.close();
  });

  es.addEventListener("failed", (e) => {
    const { status, error } = JSON.parse(e.data);
    statusEl.textContent = `실패 (${status}): ${error ?? ""}`;
    es.close();
  });

  es.onerror = () => {
    if (es.readyState === EventSource.CLOSED) {
      statusEl.textContent = "연결이 끊겼습니다. 새로고침 후 다시 시도하세요.";
    }
  };
}
```
