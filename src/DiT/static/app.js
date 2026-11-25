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
