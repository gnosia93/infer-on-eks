# GPU 하드웨어 스펙 기반 LLM 처리량(토큰/초) 및 필요 인스턴스 산출 공식 가이드

본 문서는 GPU의 **VRAM 용량**과 **메모리 대역폭(Memory Bandwidth)** 스펙을 바탕으로, 단일 GPU당 최대 동시 접속자 수(Batch Size), 초당 총 출력 토큰 처리량(Throughput), 그리고 목표 트래픽을 감당하기 위한 필요 인스턴스 대수를 계산하는 표준 공식을 정리한 가이드입니다.

---

## 1. 전제 조건 및 핵심 원리

* **KV 캐시(KV Cache) 활성화 기준:** 현대 추론 엔진(vLLM, SGLang 등)에서는 KV 캐시가 기본 활성화되어 있습니다.
  * **연산량 측면:** 이전 토큰의 Key/Value 행렬을 재사용하므로 중복 연산이 사라져 실시간 스트리밍이 가능해집니다.
  * **메모리 측면:** 대신 동시 접속자 수와 문맥 길이에 비례해 VRAM 용량을 점유하며, 매 토큰 생성(Decode) 스텝마다 모델 가중치와 함께 메모리에서 읽혀 대역폭을 소모합니다.
* **메모리 대역폭 바운드(Memory Bandwidth Bound):** LLM의 텍스트 생성(Decode) 단계는 연산(FLOPS)보다 **GPU 메모리에서 연산 코어로 가중치와 KV 캐시를 읽어 들이는 속도(GB/s)**에 의해 성능 한계가 결정됩니다.

---

## 2. 단계별 계산 공식 순서

### [1단계] 사용자 1명당 KV 캐시 점유 용량 계산
모델 아키텍처(GQA 적용 여부 등)와 평균 입·출력 문맥 길이를 기준으로 1개의 요청(Sequence)이 차지하는 VRAM 크기를 구합니다.

$$\text{KV Cache}_{1\text{token}} (\text{Bytes}) = 2 \times L \times H_{kv} \times D_{head} \times P$$

* $L$: 트랜스포머 레이어 수 (Layers)
* $H_{kv}$: Key-Value 헤드 수 (GQA 적용 시 전체 어텐션 헤드보다 작음)
* $D_{head}$: 헤드당 차원 크기 (Head Dimension)
* $P$: 데이터 정밀도 바이트 수 (FP16/BF16 = `2 Bytes`, FP8 = `1 Byte`)

$$\text{1명당 평균 KV Cache (GB)} = \frac{\text{KV Cache}_{1\text{token}} \times \text{평균 총 문맥 길이(입력+출력 토큰)}}{1024^3}$$

---

### [2단계] VRAM 용량 기반 '최대 동시 접속자 수(Batch Size)' 계산
전체 GPU VRAM에서 모델 가중치와 시스템/활성화(Activation) 예비 메모리를 제외한 나머지 공간에 몇 명분의 KV 캐시를 동시에 적재할 수 있는지 산출합니다.

$$\text{KV Cache 가용 VRAM (GB)} = \text{전체 VRAM} - \text{모델 가중치 용량} - \text{시스템 여유분}$$

$$\text{최대 동시 접속자 수 (Batch)} = \left\lfloor \frac{\text{KV Cache 가용 VRAM (GB)}}{\text{1명당 평균 KV Cache (GB)}} \right\rfloor$$

*(※ 실무에서는 메모리 단편화 및 순간 긴 문맥 유입을 대비해 이론상 최대 Batch의 **70~80% 수준**을 안전 유효 Batch로 설정합니다.)*

---

### [3단계] 메모리 대역폭 기반 '초당 총 출력 토큰(Throughput)' 계산
유효 동시 접속자($B$)를 한 번에 배칭(Continuous Batching)하여 토큰 1스텝을 생성할 때 걸리는 시간을 구하고, GPU 1장당 초당 총 출력 토큰 수를 도출합니다.

$$\text{1스텝 읽기 데이터량 (GB)} = \text{모델 가중치 (GB)} + (B \times \text{1명당 평균 KV Cache})$$

$$\text{유효 메모리 대역폭 (GB/s)} = \text{하드웨어 스펙 대역폭 (GB/s)} \times \eta \quad (\eta \approx 0.80 \sim 0.85)$$

$$\text{1스텝 소요 시간 (초)} = \frac{\text{1스텝 읽기 데이터량 (GB)}}{\text{유효 메모리 대역폭 (GB/s)}}$$

$$\text{GPU 1장당 초당 총 출력 토큰 (TPS)} = \frac{B}{\text{1스텝 소요 시간 (초)}}$$

*(※ 참고: 개별 사용자 체감 스트리밍 속도 = $\frac{1}{\text{1스텝 소요 시간(초)}}$ 토큰/초)*

---

### [4단계] 목표 트래픽 대비 필요 인스턴스 대수 산출
서비스의 목표 월간(또는 일간) 출력 토큰량을 초당 요구량으로 환산한 뒤, 노드당 처리량으로 나누어 최종 인스턴스 수량을 결정합니다.

$$\text{초당 요구 출력 토큰} = \frac{\text{월간 목표 출력 토큰 수}}{30\text{일} \times 86,400\text{초}} \quad (\text{24시간 균등 기준})$$

$$\text{필요 인스턴스 대수} = \left\lceil \frac{\text{초당 요구 출력 토큰}}{\text{GPU 1장당 TPS} \times \text{인스턴스당 GPU 수}} \right\rceil$$

---

## 3. 실전 계산 예시 (`Gemma 4 31B` + `RTX PRO 6000 Blackwell 96GB`)

### 입력 스펙 및 가정
* **타겟 모델:** `Gemma 4 31B` (Dense, **FP8 양자화** 적용 → 모델 가중치 약 **31 GB**)
* **타겟 인스턴스:** AWS `g7e.2xlarge` / `g7e.4xlarge` (NVIDIA RTX PRO 6000 Blackwell **96 GB VRAM** 1장, 메모리 대역폭 **1,800 GB/s**)
* **서비스 트래픽 가정:**
  * 월간 총 1,500억 토큰 (입력 30% = 450억 / **출력 70% = 1,050억 토큰**)
  * 1회 요청당 평균 문맥 길이: **2,000 토큰** (입력 600 + 출력 1,400)

### 단계별 산출 과정

1. **1단계 (1명당 KV 캐시):**
   * `Gemma 4 31B`의 토큰당 KV 캐시 점유량 $\approx 0.25\text{ MB}$
   * $2,000\text{ 토큰} \times 0.25\text{ MB} = \mathbf{0.5\text{ GB / 1명}}$

2. **2단계 (최대 동시 접속자 수):**
   * KV 캐시 가용 공간: $96\text{ GB} - 31\text{ GB (가중치)} - 15\text{ GB (시스템 여유분)} = \mathbf{50\text{ GB}}$
   * 이론상 최대 Batch: $50\text{ GB} \div 0.5\text{ GB} = 100\text{명}$
   * 실무 안전 유효 Batch($B$): **64명** 적용

3. **3단계 (GPU 1장당 초당 총 출력 토큰):**
   * 1스텝 읽기 데이터량: $31\text{ GB} + (64\text{명} \times 0.5\text{ GB}) = \mathbf{63\text{ GB}}$
   * 유효 메모리 대역폭 (효율 80%): $1,800\text{ GB/s} \times 0.80 = \mathbf{1,440\text{ GB/s}}$
   * 1스텝 소요 시간: $63\text{ GB} \div 1,440\text{ GB/s} = \mathbf{0.04375\text{초}}$ *(사용자 1명당 체감 속도 $\approx 22.8\text{ tok/s}$)*
   * GPU 1장당 이론 총 처리량: $64\text{명} \div 0.04375\text{초} \approx \mathbf{1,462\text{ tok/s}}$
   * **실무 보수적 산정치 (긴 문맥 버퍼 반영): `1,200 출력 토큰/초` (대당)**

4. **4단계 (필요 인스턴스 대수):**
   * 초당 요구 출력 토큰 (24시간 균등): $105,000,000,000 \div (30 \times 86,400) \approx \mathbf{40,509\text{ tok/s}}$
   * 필요 인스턴스 수량: $40,509 \div 1,200 = 33.75 \rightarrow$ **총 34대** (`g7e.2xlarge` 또는 `g7e.4xlarge`)

---

## 4. 요약 비교표 (단일 요청 vs 동시 배칭)

| 구분 | Batch = 1 (단독 실행) | Continuous Batching = 64 (실서비스) | 비고 |
| :--- | :---: | :---: | :--- |
| **1스텝 읽기 데이터량** | 31.5 GB (가중치 31 + KV 0.5) | **63.0 GB** (가중치 31 + KV 32) | 동시 접속자 수만큼 KV 캐시 증가 |
| **1스텝 소요 시간** | 약 0.0219초 | **약 0.0438초** | 대역폭 1,440 GB/s 기준 |
| **개별 사용자 체감 속도** | **약 45 ~ 50 tok/s** | **약 20 ~ 23 tok/s** | 실시간 스트리밍에 충분한 속도 유지 |
| **GPU 1장당 총 출력량** | **약 45 ~ 50 tok/s** | **약 1,200 ~ 1,460 tok/s** | **약 25배 이상의 처리 효율 증대** |

---

## 5. 실무 주의사항 (벤치마크 필수)
* 위 공식은 하드웨어 스펙 기반의 기준선이며, 실제 운영 환경에서는 **평균 프롬프트 길이(Prefill 부하)**, **출력 길이 편차**, **vLLM 파라미터(`max-num-seqs`, `gpu-memory-utilization`)**에 따라 실측값이 20~30% 달라질 수 있습니다.
* 대규모 약정(1년 Zonal RI 등) 체결 전 반드시 온디맨드 인스턴스 1대를 임대해 `vllm bench serve`로 실제 트래픽 비율과 동일한 부하 테스트를 수행해야 합니다.
