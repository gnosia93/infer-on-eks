## NVIDIA Dyanmo (차세대 분산 추론 프레임워크) ##
NVIDIA Dynamo는 Triton Inference Server의 후속 기술로 대규모 데이터 센터 환경에서 생성형 AI 모델의 추론 성능을 극대화하기 위해 설계된 오픈 소스 분산 추론 프레임워크로 Prefill(입력 처리)과 Decode(출력 생성) 단계를 서로 다른 GPU 노드로 분리하여 병렬로 처리하는 분리형 서빙(Disaggregated Serving) 아키텍처를 핵심으로 한다. 이 과정에서 NIXL을 활용해 노드 간 KV 캐시 데이터를 연산 중단 없이 초고속으로 전송함으로써 전반적인 추론 지연 시간을 획기적으로 단축시키고, 사용자의 요청이 들어올 때 기존 캐시 데이터가 위치한 최적의 노드를 실시간으로 찾아주는 지능형 라우팅 기능을 수행하며, CPU DRAM이나 SSD까지 활용하는 계층형 메모리 관리를 통해 대규모 동시 접속 상황에서도 안정적인 서비스 성능을 유지한다. TensorRT-LLM, vLLM, SGLang 기존 엔진들과 유연하게 결합하여 거대 언어 모델(LLM) 서빙 능력을 극대화하는 통합 프레임워크 이다.
![](https://github.com/gnosia93/interence-on-eks/blob/main/lesson/images/nvidia-dynamo-1.png)


### NIXL(NVIDIA Inference Transfer Library)의 작동 원리 ###
* 연산 자원의 분리: NIXL은 통신을 위해 GPU의 연산 유닛(SM)을 사용하는 기존 NCCL 방식과 달리, GPU 내부의 전용 복사 엔진(Copy Engine)을 직접 제어하여 추론 연산과 데이터 전송을 완벽하게 병렬화.
* 커널 오버헤드 제거: 데이터를 보낼 때마다 GPU 커널을 매번 실행(Launch)하지 않고, CPU가 하드웨어를 직접 조작하는 비동기 방식을 채택하여 짧은 메시지를 빈번하게 주고받는 추론 환경에서 지연 시간을 획기적으로 줄임.
* 직통 데이터 경로(P2P & RDMA): 서버 내부에서는 NVLink를 통한 GPU 간 직접 접근(P2P)을, 서버 간에는 GPUDirect RDMA를 활용하여 CPU 메모리 거침 없이 GPU HBM 간의 고속도로를 생성.
* 하드웨어 레벨의 메모리 관리: 전송할 메모리 영역을 물리적으로 고정하는 Pinning과 물리 주소를 하드웨어에 직접 전달하는 Memory Registration을 통해, OS나 GPU SM의 간섭 없이도 안전하고 정확한 데이터 이동을 보장.
* 추론 효율의 극대화: 결과적으로 데이터 전송 중에도 GPU가 연산에만 100% 집중할 수 있게 하여, 특히 LLM의 KV Cache 전송이나 분산 추론 시 기존 대비 약 30~50% 이상의 성능 향상.


### NVIDIA Dynamo Vs TensorRT ###
|구분| 	NVIDIA Dynamo|	TensorRT / TRT-LLM|
|---|---|---|
|주 역할|	분산 추론 서버/오케스트레이터|	모델 최적화 런타임 엔진|
|작동 레이어|	하이레벨 (Infrastructure, Serving)|	저레벨 (Graph, Kernels, Hardware)|
|주요 대상|	대규모 클러스터 (Multi-node/GPU)| 단일/멀티 GPU 인스턴스|
|핵심 기술|	분산 스케줄링, Disaggregated Serving|	양자화(FP8/INT8), Layer Fusion|
|관계|	요청 관리자 (Backend로 TRT 사용)|	실제 연산 최적화기|


### KV Router ###

![](https://github.com/gnosia93/interence-on-eks/blob/main/lesson/images/nvidia-dynamo-2.png)
여기서 말하는 분산 처리는 "워크로드(Workload)의 분산"이지, "연산 데이터의 파편화"가 아니다. KV Router는 "가장 데이터가 많이 준비된 노드에게 요청을 통째로 넘겨서, 통신 없이 해당 노드 안에서만 연산을 끝내게 만드는" 아주 고전적이고 효율적인 L7 로드밸런서의 역할을 수행하는 것이다.

* 실시간 통신(NVLink) 없음: 데이터 이동 비용이 너무 비싸기 때문.
* 노드 내 완결성: 한 노드가 필요한 KV 캐시를 다 갖거나, 없으면 직접 새로 만듬.
* 지능적 배치: 라우터는 그저 "누가 어떤 캐시를 들고 있는가"만 보고 요청을 분산.


### FrontEnd 비동기 처리 예제 ###
```
import express, { Request, Response } from 'express';
import { connect, NatsConnection, JSONCodec, createInbox } from 'nats';
import { v4 as uuidv4 } from 'uuid';

const app = express();
const jc = JSONCodec(); // 메시지 직렬화/역직렬화 도구
let natsConn: NatsConnection;

// 1. NATS 연결 초기화
async function initNats() {
    natsConn = await connect({ servers: "nats://localhost:4222" });
    console.log("NATS 연결 성공");
}

app.post('/v1/chat', async (req: Request, res: Response) => {
    // 2. SSE(Server-Sent Events) 설정을 통해 HTTP 연결 유지
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');

    // 3. 이 요청만을 위한 고유한 응답 주소(Reply Subject) 생성
    // 이 주소는 etcd에 등록된 서비스 정보를 바탕으로 생성됨
    const replySubject = createInbox(); 

    // 4. [핵심] 이벤트 기반 구독 시작
    // 루프를 돌지 않고, 메시지가 도착할 때마다 이 비동기 이터레이터가 깨어남
    const sub = natsConn.subscribe(replySubject);
    
    // 이 비동기 루프는 Node.js 이벤트 루프에 의해 관리되며, 
    // 실제 데이터가 소켓에 도착했을 때만 리소스를 소모함
    (async () => {
        for await (const msg of sub) {
            const data = jc.decode(msg.data) as any;

            if (data.status === 'DONE') {
                res.write(`data: [DONE]\n\n`);
                res.end(); // HTTP 연결 종료
                sub.unsubscribe(); // NATS 구독 해제
                break;
            }

            // 백엔드에서 온 토큰을 클라이언트에게 즉시 스트리밍
            res.write(`data: ${JSON.stringify(data.content)}\n\n`);
        }
    })().catch(err => {
        console.error("스트리밍 에러:", err);
        res.end();
    });

    // 5. 백엔드(vLLM)로 요청 발행 (답장 주소 포함)
    // 여기서 'vllm.llama3'는 etcd의 라벨을 통해 결정된 대상 Subject
    natsConn.publish("vllm.llama3", jc.encode({
        prompt: req.body.prompt,
        requestId: uuidv4()
    }), { reply: replySubject });

    // 함수는 여기서 즉시 종료되지만, 위에서 만든 비동기 익명 함수가 
    // 클로저(Closure)를 통해 'res' 객체를 붙잡고 응답을 처리함
});

initNats().then(() => {
    app.listen(3000, () => console.log("Frontend API 서버 실행 중: 3000"));
});
```


## 레퍼런스 ##

* [Microservices Communication with NATS](https://www.geeksforgeeks.org/advance-java/microservices-communication-with-nats/)

