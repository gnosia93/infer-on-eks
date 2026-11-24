# NVIDIA GPU 분산 훈련 장애 가이드

PyTorch와 NCCL로 여러 GPU와 노드에서 훈련할 때 생기는 장애 유형, 좀비·잔여 프로세스, 탐지·디버깅·복구 방법을 정리했습니다. 명령과 설정 예시는 Slurm과 Kubernetes 환경을 기준으로 합니다.

**목차**

1. 장애 유형
2. 좀비·잔여 프로세스
3. 탐지: 헬스체크와 모니터링
4. NCCL 행 디버깅
5. 체크포인트와 자동 재시작
6. 참고 자료

---

## 1. 장애 유형

분산 훈련은 GPU들이 매 스텝 동기화하기 때문에 GPU나 링크 하나만 망가져도 잡 전체가 멈추거나 느려집니다. 장애는 증상(어떻게 드러나는지)과 원인 계층(어디서 생기는지)으로 나눠 보면 진단하기 쉽습니다.

### 1.1 증상으로 본 분류

| 유형 | 증상 | 대표 원인 |
|---|---|---|
| 크래시 | 프로세스가 에러를 내고 종료됨 | 수정 불가 ECC 오류, GPU 이탈, OOM, 코드 버그 |
| 행(hang) | 에러 없이 진행이 멈춤. NCCL 타임아웃(PyTorch 기본 10분)이 지나야 종료됨 | 네트워크 링크 다운, 한 rank의 비정상 종료, rank 간 collective 불일치 |
| 느려짐(straggler, fail-slow) | 잡은 돌지만 처리량이 떨어짐. 동기식이라 가장 느린 GPU에 전체 속도가 맞춰짐 | 열·전력 스로틀링, PCIe·NVLink 링크 저하, 네트워크 혼잡, 스토리지 지연 |
| 조용한 오류(SDC) | 에러 없이 계산 결과가 틀림. loss spike나 NaN으로만 보이거나 아예 안 보임 | GPU 연산 유닛이나 메모리의 미검출 결함 |

표의 아래쪽 유형일수록 찾기 어렵습니다. 크래시는 로그에 바로 남지만, 느려짐과 SDC는 처리량과 loss를 따로 모니터링해야 잡힙니다(3장). loss spike나 NaN은 하이퍼파라미터나 수치 정밀도 때문일 수도 있습니다. 같은 체크포인트와 데이터로 다른 노드에서 다시 돌려 재현되는지 보면 SDC인지 구분할 수 있습니다.

### 1.2 원인 계층별 분류

#### GPU 하드웨어

| 장애 | 신호 (주로 dmesg의 XID) | 영향 |
|---|---|---|
| GPU 이탈 | XID 79 "GPU has fallen off the bus" | 노드 재부팅 필요, 반복되면 교체 |
| HBM·SRAM ECC 오류 | correctable은 대개 무해. uncorrectable은 XID 48, 94, 95 | 94는 해당 프로세스만 영향. 95는 그 GPU의 모든 프로세스가 영향받고 리셋 필요 |
| HBM row remapping | XID 63, 64 (remap 기록 이벤트, 기록 실패) | GPU 리셋 후 반영됨. 예비 row가 바닥나 remap이 실패하면 교체(RMA) 대상 |
| GSP(GPU System Processor) 오류 | XID 119, 120 | GPU 무응답, 리셋이나 재부팅 필요 |
| 발열·전력 | 클럭 스로틀링, 써멀 센서 이상 | 주로 느려짐, 심하면 중단 |
| NVLink·NVSwitch 오류 | NVLink XID(74, 최신 카탈로그는 144~150), NVSwitch SXid | 노드 내 통신 실패나 대역폭 저하 |
| Fabric Manager 문제 (NVSwitch 기반 HGX) | 서비스 미기동, 드라이버와 버전 불일치 | CUDA 초기화 실패(error 802)로 잡 시작 불가 |

XID별 권장 조치는 NVIDIA Xid Catalog에 정리돼 있습니다. XID 154가 함께 찍히면 그 이벤트가 알려주는 복구 조치를 따르면 됩니다.

#### 노드 간 네트워크 (InfiniBand, RoCE)

| 장애 | 신호 | 영향 |
|---|---|---|
| 링크 플랩, 케이블·트랜시버 불량 | IB 포트 카운터의 symbol error, link downed 증가 | NCCL 에러나 행 |
| 스위치 고장 | 여러 노드에서 동시에 링크 다운 | 그 스위치에 붙은 노드 전체가 영향받음 |
| NIC(HCA) 고장 | 포트 down, 펌웨어 오류 | 해당 노드 통신 불가 |
| 혼잡 (RoCE는 PFC·ECN 설정의 영향이 큼) | PFC pause 프레임 급증, 특정 collective만 지연 | 느려짐, 심하면 타임아웃 |
| GPUDirect RDMA 미동작 | `nvidia-peermem` 미로드 등. `NCCL_DEBUG=INFO` 로그에 GDRDMA가 안 보임 | 에러 없이 대역폭만 떨어짐 |

#### 호스트·인프라

- **노드 부품 고장:** CPU, 시스템 메모리, SSD, 전원 공급 장치, IO 확장 보드가 대상입니다. 노드 하나가 빠지면 잡 전체가 중단됩니다.
- **PCIe 링크 다운그레이드:** GPU나 NIC가 x16 대신 x8처럼 낮은 폭이나 속도로 협상되면 에러 없이 느려집니다.
- **스토리지:** 공유 파일시스템이 느리면 데이터 로딩이 멈추고, 체크포인트 저장이 실패하거나 오래 걸립니다.
- **계획된 유지보수:** Llama 3 훈련에서는 펌웨어·커널 업그레이드 같은 자동 유지보수 때문에 하루 한 번 이상 중단이 생겼습니다.

#### 소프트웨어·설정

- **NCCL 행·타임아웃:** rank마다 collective 호출 순서나 텐서 크기가 다르면(desync) 서로를 기다리다 멈춥니다. 한 rank가 죽어도 나머지 rank는 타임아웃까지 기다립니다. 모든 rank가 타임아웃 로그를 남기므로 처음 멈춘 rank를 찾아야 합니다(4장).
- **메모리 부족:** GPU OOM은 가변 시퀀스 길이로 인한 메모리 피크나 단편화 때문에 생깁니다. 호스트 OOM은 DataLoader 워커나 pinned memory 때문에 생깁니다.
- **컨테이너 `/dev/shm` 부족:** Docker 기본값인 64MB로는 NCCL의 노드 내 공유 메모리 통신이 실패할 수 있습니다. `--shm-size`나 `--ipc=host`로 늘립니다.
- **버전·설정 불일치:** 드라이버, CUDA, NCCL, Fabric Manager, NIC 펌웨어의 조합이 안 맞는 경우입니다. NCCL이 엉뚱한 네트워크 인터페이스를 잡으면 `NCCL_SOCKET_IFNAME`, `NCCL_IB_HCA`로 지정합니다.
- **초기화(rendezvous) 실패:** `MASTER_ADDR`/`MASTER_PORT` 설정, 방화벽, DNS 문제로 생깁니다.
- **애플리케이션 버그:** illegal memory access 같은 경우입니다. XID 13, 31, 43은 하드웨어보다 코드가 원인일 때가 많습니다.

### 1.3 실제 빈도: Llama 3 405B 사례

Meta는 최대 16K개의 H100으로 Llama 3 405B를 사전 훈련하면서 54일 동안 잡 중단을 466번 겪었습니다. 47번은 계획된 중단이었고, 나머지 419번은 예기치 않은 중단으로 하루 약 7.8번(3시간에 한 번꼴)입니다. 예기치 않은 중단의 약 78%는 하드웨어 문제였고(확인 또는 의심), GPU 관련이 58.7%로 가장 많았습니다.

| 원인 | 중단 횟수 |
|---|---|
| GPU 불량 | 148 |
| GPU HBM3 메모리 | 72 |
| 소프트웨어 버그 | 54 |
| 네트워크 스위치·케이블 | 35 |
| 계획에 없던 호스트 유지보수 | 32 |
| GPU SRAM 메모리 | 19 |
| GPU System Processor | 17 |
| NIC | 7 |
| NCCL watchdog 타임아웃 (원인 불명) | 7 |
| Silent Data Corruption | 6 |

출처: The Llama 3 Herd of Models 3.3.4절, Table 5

이 정도 규모에서는 장애를 아예 없애기보다 빨리 감지해서 자동으로 재시작하는 쪽이 현실적입니다. Meta는 대부분의 장애를 자동화로 처리해 큰 수동 개입은 3번뿐이었고, 유효 훈련 시간을 90% 이상으로 유지했습니다.

---

## 2. 좀비·잔여 프로세스

분산 훈련에서 "좀비"라고 부르는 프로세스는 대부분 엄밀한 의미의 좀비가 아닙니다. 엄밀한 좀비(ps의 `Z`, `<defunct>`)는 이미 종료됐는데 부모가 `wait()`로 회수하지 않아 프로세스 테이블에만 남은 항목이고, PID 하나만 차지합니다. 현장에서 문제가 되는 건 잡이 죽거나 끝난 뒤에도 GPU 메모리와 포트를 잡고 남은 프로세스입니다.

| 종류 | ps STAT | `kill -9` | GPU 메모리 |
|---|---|---|---|
| 행 걸린 프로세스 | R, S | 죽음 | 점유 |
| 고아 프로세스 | R, S (보통 PPID가 1) | 죽음 | 점유 |
| 커널 안에서 멈춘 프로세스 | D, 또는 `<defunct>`인데 D 상태 스레드가 남음 | 안 죽음 | 점유 |
| 진짜 좀비 | Z (`<defunct>`) | 해당 없음. 부모가 회수하거나 종료돼야 사라짐 | 점유 안 함 |

### 2.1 생기는 이유

#### 한 rank가 죽으면 나머지 rank가 기다리다 멈춤

collective 연산은 모든 rank가 참여해야 끝납니다. 한 rank가 크래시하면 나머지 rank는 NCCL 커널 안에서 그 rank를 계속 기다립니다. 최근 PyTorch는 NCCL watchdog이 타임아웃(기본 10분) 뒤 이런 프로세스를 종료합니다. 구버전이거나 이 기능을 끈 경우(`TORCH_NCCL_ASYNC_ERROR_HANDLING=0`)에는 무한정 기다립니다.

#### 런처가 먼저 죽어 정리 신호가 전달되지 않음

torchrun이나 mpirun은 워커 하나가 죽으면 나머지 워커에 신호를 보내 정리합니다. 그런데 런처 자신이 `kill -9`나 OOM killer로 죽으면 정리를 못 하고, 워커는 PID 1에 입양된 고아로 남습니다.

- pdsh나 ssh로 원격 노드에 프로세스를 띄우는 런처(DeepSpeed의 기본 멀티노드 런처 등)는 헤드 노드의 런처가 죽어도 원격 프로세스가 남기 쉽습니다.
- Slurm 잡 안에서 `srun` 대신 ssh로 띄운 프로세스는 pam_slurm_adopt가 없으면 잡 cgroup 밖에 있어서, 잡이 끝나도 정리되지 않습니다.

#### 커널 안에서 멈춰 `kill -9`가 안 먹힘 (D 상태)

D 상태(uninterruptible sleep)인 스레드는 시그널로 깨어나지 않으므로 SIGKILL도 처리되지 않습니다. GPU가 응답하지 않는 상황(XID 79, 119 등)에서는 드라이버 호출이나 종료 시 자원 정리가 끝나지 않아 스레드가 이 상태로 묶일 수 있습니다. NFS나 Lustre 같은 공유 파일시스템이 멈추면 체크포인트 저장이나 데이터 로딩 중인 스레드도 같은 상태가 됩니다.

ps에서 `<defunct>`로 보이는데 GPU 메모리가 안 풀리면 이 경우를 먼저 의심합니다. 메인 스레드는 종료됐지만 NCCL이나 CUDA 스레드 하나가 드라이버 안에서 멈춘 상태입니다. GPU 메모리는 프로세스가 연 `/dev/nvidia*` 파일이 닫힐 때 해제되는데, 스레드가 하나라도 살아 있으면 이 파일이 닫히지 않습니다.

#### 자식 프로세스가 GPU 디바이스 파일을 물려받음

CUDA를 초기화한 뒤 fork로 만든 자식(DataLoader 워커, 직접 만든 multiprocessing 풀)은 `/dev/nvidia*` 파일 디스크립터도 물려받습니다. 그래서 부모가 죽어도 자식이 살아 있으면 GPU 메모리가 해제되지 않습니다. DataLoader 워커는 부모가 살아 있는지 주기적으로 확인해 스스로 종료하지만, 데이터를 읽다가 I/O에서 막혀 있으면 확인하지 못합니다.

#### 진짜 좀비가 쌓임

컨테이너에서 python이 PID 1이면 고아가 된 하위 프로세스(컴파일이나 데이터 처리용 subprocess 등)를 회수하지 않아 `<defunct>`가 쌓입니다. tini 같은 init 프로세스는 이 회수를 해 주지만 python은 하지 않습니다. 부모가 NCCL 행에 걸려 `wait()`를 호출하지 못하는 동안에도 먼저 끝난 자식이 좀비로 남습니다.

### 2.2 현상

- **다음 잡이 GPU를 못 씀:** 남은 프로세스가 GPU 메모리를 잡고 있으면 새 잡이 시작하자마자 CUDA OOM이 납니다. GPU가 Exclusive Process 모드면 `all CUDA-capable devices are busy or unavailable` 에러가 납니다. 메모리가 충분해도 남은 프로세스가 GPU를 계속 쓰면 시분할 때문에 새 잡이 느려집니다.
- **nvidia-smi와 실제 상태가 안 맞음:** 메모리 사용량은 보이는데 프로세스 목록이 비어 있거나, ps로 찾을 수 없는 PID가 나오기도 합니다. 컨테이너 안에서는 PID 네임스페이스가 달라 원래 안 보일 수도 있습니다.
- **GPU 사용률이 100%인데 진행이 없음:** 행 걸린 rank의 NCCL 커널이 busy-wait하고 있습니다.
- **포트 충돌:** 남은 프로세스가 torchrun의 rendezvous 포트(static 기본 29500, c10d 기본 29400)를 잡고 있으면 새 잡이 `EADDRINUSE`(address already in use)로 초기화에 실패합니다.
- **`kill -9`가 안 먹힘:** D 상태인 경우입니다. GPU를 쓰는 프로세스가 남아 있으면 GPU 리셋(`nvidia-smi -r`)도 실패하므로 결국 노드를 재부팅해야 합니다. dmesg에 `task ... blocked for more than 120 seconds` 경고가 찍히기도 합니다.
- **스케줄러 이상:** Slurm은 SIGKILL 후 UnkillableStepTimeout(기본 60초) 안에 프로세스가 안 죽으면 노드를 "Kill task failed" 사유로 drain합니다. Kubernetes에서는 Pod가 Terminating 상태에서 멈춥니다.
- **재시작 실패 반복:** 자동 재시작이 같은 노드에 잡을 다시 띄우면 남은 프로세스 때문에 OOM이나 포트 충돌로 또 실패합니다.
- **PID 고갈:** 좀비가 쌓여 컨테이너의 pids 제한에 걸리면 새 프로세스나 스레드를 만들지 못합니다(`Resource temporarily unavailable`).

### 2.3 확인 명령

```bash
# STAT: Z=좀비, D=커널 안에서 멈춤. PPID가 1이면 고아
ps -eo pid,ppid,stat,wchan:32,cmd | grep -E 'python|torchrun'

# <defunct>인데 GPU 메모리가 안 풀릴 때 스레드별 상태 확인
ps -L -p <PID> -o tid,stat,wchan:32,comm

# 커널 어디서 멈췄는지 확인. nvidia 함수면 GPU·드라이버, nfs·lustre면 스토리지 문제
sudo cat /proc/<PID>/task/*/stack

# nvidia-smi에 안 보일 때 GPU 디바이스 파일을 실제로 잡은 프로세스 찾기
sudo fuser -v /dev/nvidia*

# 포트를 잡은 프로세스 찾기
sudo ss -ltnp | grep <포트>
```

### 2.4 예방

- 컨테이너에는 init을 둡니다(`docker run --init`, tini, Kubernetes의 `shareProcessNamespace: true`).
- Slurm에서는 `srun`으로 프로세스를 띄워 잡이 끝날 때 잡 cgroup 안의 프로세스가 함께 정리되게 합니다. ssh를 꼭 써야 하면 pam_slurm_adopt를 설정합니다.
- 잡 시작 전(Slurm prolog 등)에 GPU 메모리를 쓰는 프로세스나 포트 점유가 있는지 확인하고, 있으면 정리하거나 그 노드를 뺍니다(5.5절).
- fork로 인한 디바이스 파일 상속이 문제라면 DataLoader에 `multiprocessing_context="spawn"`이나 `"forkserver"`를 지정합니다. 대신 워커 시작이 느려집니다.
- D 상태 프로세스는 소프트웨어로 없앨 수 없으므로, 발견되면 노드를 격리하고 재부팅합니다.

---

## 3. 탐지: 헬스체크와 모니터링

### 3.1 언제 무엇을 점검하나

| 시점 | 점검 | 걸리는 시간 (8 GPU 노드 기준) |
|---|---|---|
| 노드 투입·수리 후 | `dcgmi diag -r 3` 또는 `-r 4`, nccl-tests로 기준 대역폭 확인 | 35분(r3)~2.25시간(r4) 이내 |
| 잡 시작 전 (prolog) | `dcgmi diag -r 1`, GPU 개수, 남은 GPU 프로세스, IB 포트 상태 | 수 초 |
| 잡 실행 중 | DCGM 헬스체크, dcgm-exporter 메트릭, 커널 로그의 XID, IB 포트 카운터, rank별 연산 시간, loss·grad norm | 상시 |
| 잡 실패 후 | 실패한 노드에 `dcgmi diag -r 2`. 실패하면 drain 후 `-r 3`·`-r 4` | 10.5분(r2) 이내부터 |

### 3.2 DCGM 진단 (dcgmi diag)

DCGM 진단은 GPU에 부하를 거는 능동 점검이라 잡이 돌지 않는 GPU에서 실행합니다. `nv-hostengine`(nvidia-dcgm 서비스)이 떠 있어야 합니다.

| 레벨 | 소요 시간 (NVIDIA 문서, Hopper 측정값) | 추가되는 테스트 | NVIDIA 권장 용도 |
|---|---|---|---|
| `-r 1` | 2.5초 이내 | 소프트웨어·배포 점검 | 잡 시작 전 준비 상태 확인 |
| `-r 2` | 4 GPU 2.5분, 8 GPU 10.5분 이내 | PCIe·NVLink, GPU 메모리, 메모리 대역폭 | 잡 실패 후 점검 |
| `-r 3` | 4 GPU 10분, 8 GPU 35분 이내 | 연산·전력 스트레스, nvbandwidth, NCCL 테스트 | 관리자의 사후 분석 |
| `-r 4` | 4 GPU 45분, 8 GPU 2.25시간 이내 | 메모리 스트레스(memtest), pulse 테스트 | 관리자의 사후 분석 |

```bash
dcgmi diag -r 1        # 잡 시작 전
dcgmi diag -r 2 -j     # 잡 실패 후. JSON으로 출력해 스크립트로 판정
dcgmi diag -r 3        # 장애 의심 노드
```

DCGM 진단은 현재 환경에서 도는 온라인 진단입니다. 하드웨어를 완전히 검증하거나 RMA를 진행하려면 NVIDIA의 별도 오프라인 진단 도구(field diagnostics)가 필요합니다.

### 3.3 DCGM 백그라운드 헬스체크 (dcgmi health)

잡이 도는 동안에도 성능에 영향 없이 켜 둘 수 있는 수동 감시입니다.

```bash
dcgmi group -c allgpus --default     # 모든 GPU로 그룹 생성. 출력된 group ID 확인
dcgmi health -g <group_id> -s a      # 모든 감시 항목 켜기
dcgmi health -g <group_id> -c        # 현재 상태 조회
```

- 감시 항목 플래그: `p`(PCIe), `m`(메모리), `i`(InfoROM), `t`(온도·전력), `n`(NVLink), `d`(드라이버), `x`(ConnectX), `a`(전체)
- **Warning:** 지금 작업은 끝낼 수 있지만 나중에 살펴봐야 하는 문제입니다.
- **Error:** 현재 작업이 이미 손상됐거나 중단될 가능성이 높습니다. 잡을 멈추고 GPU를 점검합니다.
- GPU 이탈, 치명적인 XID, 드라이버가 요구하는 복구 조치(P2P 트래픽 중단, 리셋, 재부팅)도 이 경로로 보고됩니다.

### 3.4 dcgm-exporter 메트릭

dcgm-exporter는 DCGM 필드를 Prometheus 메트릭으로 내보냅니다. 수집 항목은 counters CSV로 정하는데, 장애 탐지에 필요한 항목 일부가 기본 CSV에서 주석 처리돼 있어 직접 켜야 합니다.

| 항목 | 용도 | 기본 CSV |
|---|---|---|
| 마지막 XID 값 | 치명적 GPU 오류 감지 | 켜짐 |
| row remap 수(uncorrectable), remap 실패 여부 | HBM 열화, 교체 판단 | 켜짐 |
| PCIe replay 횟수 | PCIe 링크 품질 | 켜짐 |
| 클럭, GPU·메모리 온도, 전력 | 스로틀링으로 인한 느려짐 | 켜짐 |
| GPU 엔진·텐서 코어·DRAM 활성 비율 | 행(사용률 패턴), 느려짐 | 켜짐 |
| ECC 오류 수 (volatile, aggregate) | 수정 불가 ECC 오류 | 꺼짐 |
| NVLink 오류 카운터 (CRC, replay, recovery) | NVLink 품질. GPU 세대별로 필드가 다름 | 꺼짐 |
| 스로틀 사유별 누적 시간 | 스로틀 원인 구분 | 꺼짐 |
| Fabric Manager 상태, fabric health | NVSwitch 시스템 | 꺼짐 |

- XID 메트릭은 마지막 XID 값만 담는 gauge라서, 값이 바뀌는 시점을 경보로 잡아야 하고 같은 XID가 반복되면 놓칠 수 있습니다. 커널 로그의 `NVRM: Xid` 줄도 로그 수집기로 함께 모읍니다.
- 최신 버전에는 일정 시간 창 안의 XID 개수를 세는 메트릭(`DCGM_EXP_XID_ERRORS_COUNT`, 기본 꺼짐)도 있습니다.
- 메트릭 이름은 버전마다 다릅니다(예: 구버전 `DCGM_FI_DEV_XID_ERRORS`, 최신 main 브랜치 `DCGM_FI_DEV_XID_ERROR`). 배포한 버전의 CSV를 기준으로 경보 규칙을 만듭니다.

### 3.5 네트워크 점검

```bash
ibstat                       # 포트별 State: Active, Rate 확인
perfquery -C mlx5_0 -P 1     # HCA·포트별 카운터: SymbolErrorCounter, LinkDownedCounter, PortRcvErrors 등
ibdiagnet                    # 패브릭 전체 점검 (관리자)
ethtool -S <인터페이스>       # RoCE: pause 프레임, discard 카운터
```

포트 카운터는 node_exporter의 infiniband collector 같은 도구로 수집하고, 값이 늘어나는 추세를 경보로 봅니다. 실제 통신 성능은 nccl-tests로 확인합니다.

```bash
# 노드 1대, GPU 8개
./build/all_reduce_perf -b 8 -e 8G -f 2 -g 8

# 여러 노드 (MPI=1로 빌드, GPU당 프로세스 1개. --mpi 값은 클러스터 설정에 맞게)
srun -N 2 --ntasks-per-node=8 --gpus-per-node=8 --mpi=pmix ./build/all_reduce_perf -b 8 -e 8G -f 2 -g 1
```

결과의 `busbw`를 정상 노드의 기준값과 비교합니다. 노드를 둘씩 짝지어 돌리면 느린 노드나 링크를 좁혀 갈 수 있습니다.

### 3.6 느려짐(straggler) 탐지

동기식 훈련에서는 모든 rank의 step 시간이 같아지므로 step 시간만으로는 느린 rank를 찾을 수 없습니다.

- rank별로 통신을 뺀 연산 시간을 재서 비교하면 가장 오래 걸리는 rank가 원인입니다. 연산과 통신이 겹치는 구성에서는 정확히 나누기 어려우므로 NVRx의 straggler detection처럼 rank별 GPU·CPU 성능을 비교해 주는 도구를 쓰는 편이 쉽습니다.
- `nvidia-smi -q -d PERFORMANCE`로 클럭 이벤트(스로틀) 사유를 확인합니다.
- `nvidia-smi -q`의 GPU Link Info에서 PCIe 링크의 현재 폭·속도가 최대값보다 낮은지 확인합니다.
- nccl-tests로 느린 노드나 링크를 찾습니다(3.5절).

### 3.7 SDC 탐지

- loss와 grad norm의 급격한 변화를 감시합니다.
- DDP나 HSDP처럼 복제본이 있는 구성에서는 복제본끼리 파라미터 체크섬을 주기적으로 비교합니다. 정상이면 값이 같습니다.
- loss spike가 나면 같은 체크포인트와 배치로 다른 노드에서 재실행합니다. 다른 노드에서는 정상이고 원래 노드에서만 재현되면 그 노드의 SDC를 의심합니다. 어느 노드에서나 재현되면 데이터나 수치 문제입니다.
- 의심 노드는 `dcgmi diag -r 3` 이상으로 점검합니다.

### 3.8 행 조기 탐지

- NCCL watchdog은 타임아웃(기본 10분)이 지나야 동작합니다. rank 0이 step 번호와 시각을 파일이나 메트릭으로 주기적으로 남기게 하고, 정상 step 시간의 몇 배 동안 갱신이 없으면 경보를 보내면 더 빨리 알 수 있습니다.
- GPU 사용률은 100%로 고정됐는데 텐서 코어 활성 비율과 전력이 떨어졌다면 NCCL 커널이 busy-wait 중일 가능성이 높습니다.
- NVRx의 fault tolerance는 코드 구간별 heartbeat로 행을 감지하고 실행 중인 잡 안에서 워커를 재시작합니다(실험적 프로젝트, PyTorch 2.9 이상).

---

## 4. NCCL 행 디버깅

### 4.1 미리 켜 둘 설정

행은 재현이 어려우므로 진단 정보가 자동으로 남도록 평소에 켜 둡니다.

```bash
# Flight Recorder (PyTorch 2.5 이상). 버전에 따라 기본값이 꺼짐일 수 있으니 명시
export TORCH_NCCL_TRACE_BUFFER_SIZE=2000     # 기록할 collective 수. 0이면 꺼짐
export TORCH_NCCL_DUMP_ON_TIMEOUT=1          # 타임아웃 시 rank별 덤프 파일 기록

# 덤프 경로 접두사. 모든 노드가 접근하는 공유 경로로 지정
FR_DIR=/shared/fr/${SLURM_JOB_ID}_${SLURM_RESTART_COUNT:-0}
mkdir -p "$FR_DIR"
export TORCH_FR_DUMP_TEMP_FILE=$FR_DIR/nccl_trace_rank_
export TORCH_NCCL_DEBUG_INFO_TEMP_FILE=$FR_DIR/nccl_trace_rank_   # 구버전용 이름

# NCCL 로그. 평소엔 WARN, 재현할 때 INFO. %h=호스트, %p=PID
mkdir -p /shared/nccl/${SLURM_JOB_ID}
export NCCL_DEBUG=WARN
export NCCL_DEBUG_FILE=/shared/nccl/${SLURM_JOB_ID}/nccl.%h.%p.log
```

타임아웃은 정상 상황에서 가장 오래 기다리는 구간보다 길게 잡습니다. 다른 rank의 체크포인트 저장, 첫 step의 컴파일, 평가 구간이 대표적입니다. 너무 짧으면 정상 대기를 행으로 오판합니다.

```python
from datetime import timedelta
import torch.distributed as dist

dist.init_process_group("nccl", timeout=timedelta(minutes=10))
```

rank 0만 로그를 남기면 원인 rank의 마지막 메시지가 사라집니다. rank별 로그를 파일로 남기고, 처음 실패한 rank의 traceback이 요약에 담기도록 `@record`를 붙입니다.

```python
from torch.distributed.elastic.multiprocessing.errors import record

@record   # torchrun 실패 요약의 "Root Cause (first observed failure)"에 traceback이 담김
def main():
    ...
```

```bash
torchrun --log-dir=/shared/logs/${SLURM_JOB_ID} --redirects=3 ... train.py   # rank별 stdout·stderr 파일
```

### 4.2 행이 났을 때 순서

1. **행인지 확인합니다.** step 로그나 heartbeat가 멈췄고 GPU 사용률이 100%로 고정돼 있으면 NCCL 행일 가능성이 높습니다.
2. **실행 중인 잡의 상태를 조회합니다.** NCCL 2.24 이상은 RAS가 기본으로 켜져 있습니다. 잡이 도는 아무 노드에서나 조회하면 응답 없는 프로세스와 communicator 상태를 볼 수 있습니다.
   ```bash
   ncclras                                   # 또는
   echo verbose status | nc localhost 28028
   ```
3. **모든 rank의 스택을 뜹니다.** 대부분의 rank는 같은 collective에서 기다리고 있고, 혼자 다른 위치에 있는 rank가 원인일 가능성이 높습니다. 컨테이너에서는 ptrace 권한(`SYS_PTRACE`)이 필요합니다.
   ```bash
   srun --overlap --jobid=<JOB_ID> -N <노드 수> --ntasks-per-node=1 \
     bash -c 'for p in $(pgrep -f train.py); do py-spy dump --native --pid $p; done'
   ```
4. **타임아웃 뒤 Flight Recorder 덤프를 분석합니다.** 모든 rank의 덤프를 한 디렉터리에 모은 뒤 실행하면 어느 rank가 어느 collective에 들어오지 않았는지 보여 줍니다.
   ```bash
   pip install tabulate
   torchfrtrace --prefix "nccl_trace_rank_" /shared/fr/<JOB_ID>_<RESTART_COUNT>/
   ```
5. **원인 rank의 노드를 확인합니다.** 그 노드의 dmesg(XID), NCCL WARN 로그, IB 포트 카운터를 봅니다.

### 4.3 원인 판별

| 원인 rank의 상태 | 흔한 원인 | 확인과 조치 |
|---|---|---|
| 이미 종료됨 | OOM, 예외, GPU 오류(XID) | torchrun 실패 요약의 Root Cause, 그 노드의 dmesg |
| 다른 collective를 호출 중 (순서·횟수 불일치) | desync: rank별 조건 분기, rank마다 다른 배치 수 | Flight Recorder 결과. 재현할 때는 `TORCH_DISTRIBUTED_DEBUG=DETAIL`(collective 일관성 검사, 오버헤드 있음) |
| collective 밖에서 멈춤 | 데이터 로딩·체크포인트 I/O 대기, Python 데드락 | `py-spy dump` 스택 |
| 모든 rank가 같은 collective에서 대기 | 네트워크나 GPU 장애 | NCCL WARN 로그, `ncclras`, IB 포트 카운터, dmesg XID |

rank마다 배치 수가 다른 경우: `DistributedSampler`는 기본으로 rank별 샘플 수를 맞추지만, `IterableDataset`이나 직접 만든 샘플러는 맞춰 주지 않습니다. 이때는 배치 수를 직접 맞추거나 DDP의 `Join` 컨텍스트 매니저를 씁니다.

### 4.4 자주 보는 메시지

| 메시지 | 의미 |
|---|---|
| `Watchdog caught collective operation timeout: WorkNCCL(SeqNum=..., OpType=...)` | 이 collective가 타임아웃 안에 끝나지 않음. 메시지를 남긴 rank가 아니라 다른 rank가 원인인 경우가 많음 |
| `NET/IB : Got completion from peer ... with error 12` | IB 재전송 한도 초과(`IBV_WC_RETRY_EXC_ERR`). 상대 노드가 죽었거나 링크 문제 |
| `unhandled system error` | 시스템 호출 실패. `/dev/shm` 부족, 네트워크 인터페이스 설정 등. `NCCL_DEBUG=INFO`로 직전 WARN 확인 |
| `CUDA error: an illegal memory access was encountered` | 주로 코드 버그. 같은 시각 dmesg에 XID 31 등이 있는지 확인 |

---

## 5. 체크포인트와 자동 재시작

### 5.1 체크포인트 주기

장애 한 번에 잃는 시간은 평균 "체크포인트 간격의 절반 + 재시작 시간"입니다. 저장 때문에 학습이 멈추는 시간을 C, 잡 전체의 평균 고장 간격을 M이라 하면 적정 간격 T는 Young의 근사식으로 구합니다.

**T ≈ √(2 × C × M)**

M은 GPU 하나가 아니라 잡 전체의 값이라, 잡이 커질수록 M이 짧아지고 간격도 짧아져야 합니다. M = 3시간(Llama 3의 예기치 않은 중단 간격)일 때 예시는 다음과 같습니다.

| 저장 방식 (예시) | C | 적정 간격 T |
|---|---|---|
| 동기 저장 | 30초 | 약 13분 |
| 비동기 저장 | 5초 | 약 5.5분 |

재시작 시간 R은 간격과 상관없이 장애마다 그대로 잃습니다. M = 3시간에 R = 10분이면 재시작 시간만으로 전체 시간의 약 5.6%를 잃으므로, 체크포인트 간격과 함께 재시작 시간도 줄여야 합니다(5.7절).

### 5.2 저장할 상태

| 상태 | 빠뜨리면 |
|---|---|
| 모델 파라미터, 옵티마이저 상태 | 학습을 이어갈 수 없음 |
| LR 스케줄러, global step, 처리한 토큰 수 | 학습률 스케줄이 처음부터 다시 시작됨 |
| 데이터 로더 위치 (sampler 상태, torchdata `StatefulDataLoader`) | 재시작 후 같은 데이터를 다시 보거나 건너뜀 |
| RNG 상태 (Python, NumPy, torch, CUDA) | dropout·데이터 증강이 달라져 재현성이 깨짐 |
| AMP `GradScaler` 상태 (fp16 사용 시) | loss scale이 초기값으로 돌아가 초반 step이 overflow로 건너뛰어짐 |

rank마다 값이 다른 상태(데이터 로더 위치, RNG)는 rank 번호를 넣은 키나 rank별 파일로 저장합니다.

### 5.3 저장 방식

- **분산 체크포인트(DCP):** `torch.distributed.checkpoint`는 rank별 shard를 병렬로 쓰고, 불러올 때 다른 world size로 다시 나눌(resharding) 수 있습니다. 노드 수가 바뀐 채로 재시작할 때 필요합니다.
- **비동기 저장:** `dcp.async_save`(PyTorch 2.4 이상)는 상태를 CPU 버퍼로 복사하는 동안만 학습을 멈추고 파일 쓰기는 백그라운드에서 합니다. CPU 메모리를 rank당 체크포인트 크기 × rank 수만큼 더 쓰므로 호스트 메모리 여유를 확인합니다. 저장 요청은 한 번에 하나만 진행하는 것이 권장됩니다.
- **복사 속도 개선:** `FileSystemWriter(cache_staged_state_dict=True)`는 고정(pinned) 메모리 버퍼로 복사를 빠르게 하지만 버퍼가 계속 메모리에 남습니다. PyTorch 2.9부터는 `async_stager=DefaultStager()`로 GPU에서 CPU로의 복사도 백그라운드로 넘길 수 있고, 이때는 다음 `optimizer.step()` 전에 이전 저장의 복사 완료(`staging_completion`)를 기다려야 합니다.

```python
import torch.distributed.checkpoint as dcp
from torch.distributed.checkpoint.state_dict import get_state_dict, set_state_dict
from torch.distributed.checkpoint.stateful import Stateful

class AppState(Stateful):
    """DCP가 저장·로드할 때 state_dict()와 load_state_dict()를 자동으로 호출한다."""

    def __init__(self, model, optimizer):
        self.model = model
        self.optimizer = optimizer

    def state_dict(self):
        model_sd, optim_sd = get_state_dict(self.model, self.optimizer)
        return {"model": model_sd, "optim": optim_sd}

    def load_state_dict(self, state_dict):
        set_state_dict(
            self.model,
            self.optimizer,
            model_state_dict=state_dict["model"],
            optim_state_dict=state_dict["optim"],
        )

ckpt_future = None
for step in range(start_step, total_steps):
    train_step()
    if step % ckpt_every == 0:
        if ckpt_future is not None:
            ckpt_future.result()  # 이전 비동기 저장이 끝날 때까지 대기 (한 번에 하나만)
        ckpt_future = dcp.async_save(
            {"app": AppState(model, optimizer)},
            checkpoint_id=f"/ckpt/step_{step:08d}",
        )

# 재시작할 때: 마지막으로 완성된 체크포인트에서 불러오기
dcp.load({"app": AppState(model, optimizer)}, checkpoint_id=latest_complete_dir)
```

- **완성된 체크포인트만 쓰기:** 저장 도중 죽으면 반쪽짜리 체크포인트가 남습니다. 저장이 끝난 뒤(비동기면 future 완료 후)에만 rank 0이 `latest` 같은 포인터 파일을 갱신하고, 재시작할 때는 포인터가 가리키는 체크포인트를 씁니다. DCP는 shard를 모두 쓴 뒤 마지막에 `.metadata` 파일을 기록하므로, `.metadata`가 없는 디렉터리는 불완전한 것으로 보고 건너뜁니다.
- **보존 정책:** 최근 몇 개만 남기면 SDC나 loss 발산이 늦게 발견됐을 때 돌아갈 곳이 없습니다. 최근 N개와 함께 일정 간격으로 일부를 오래 보관합니다.
- **계층형 저장:** 대규모에서는 로컬 NVMe나 다른 노드의 메모리에 먼저 쓰고 공유 스토리지로 비동기 복사하면 저장과 복구가 빨라집니다. NVRx의 local checkpointing이 이 방식을 제공합니다.

### 5.4 재시작 전략

재시작은 같은 노드에서 바로 다시 띄우는 **잡 내부 재시작**과, 문제 노드를 빼고 잡을 다시 제출하는 **재제출**로 나뉩니다. 하드웨어 문제는 같은 노드에서 재시작해도 다시 실패하므로 원인에 따라 고릅니다.

| 상황 | 대응 |
|---|---|
| 일시적 오류 (순간적인 네트워크 장애, 원인 불명의 NCCL 타임아웃 1회) | 잡 내부 재시작 (torchrun `--max-restarts`, NVRx) |
| 같은 노드나 rank에서 반복 실패 | 그 노드를 빼고 재제출 |
| 하드웨어 신호 (XID 79·95, row remap 실패, DCGM health Error, D 상태 프로세스, IB 포트 다운) | 즉시 노드 drain, 예비 노드로 재시작 |
| 모든 노드가 같은 step에서 같은 예외 (코드 버그, 재현되는 OOM이나 NaN) | 재시작해도 반복되므로 자동 재시작을 멈추고 사람이 확인 |

복구 순서:

1. **감지:** 프로세스 종료, watchdog 타임아웃, 헬스체크 실패
2. **원인 노드 식별:** torchrun 실패 요약, Flight Recorder, dmesg XID, DCGM health
3. **격리:** Slurm은 `scontrol update nodename=<노드> state=drain reason="<사유>"`, Kubernetes는 `kubectl cordon <노드>`
4. **교체:** 예비 노드 투입
5. **재시작:** 마지막으로 완성된 체크포인트에서 이어서 학습
6. **확인:** 재시작 직후 loss가 중단 직전 값과 이어지는지, step 시간이 정상인지 확인

torchrun 옵션:

- `--max-restarts=N`: 워커가 실패하면 모든 워커를 멈추고 다시 띄우는 횟수입니다. torchrun은 학습 상태를 저장해 주지 않으므로, 학습 스크립트가 시작할 때 마지막 체크포인트를 찾아 불러와야 합니다.
- `--nnodes=MIN:MAX`(예: `6:8`): 노드가 빠져도 MIN 이상이면 남은 노드로 계속합니다. world size가 바뀌므로 체크포인트 resharding과 배치 크기 조정이 필요합니다.

### 5.5 Slurm 구성 예시

잡 스크립트:

```bash
#!/bin/bash
#SBATCH --job-name=train
#SBATCH --nodes=8
#SBATCH --ntasks-per-node=1
#SBATCH --gpus-per-node=8
#SBATCH --requeue
#SBATCH --open-mode=append

# 행 디버깅 설정은 4.1절 참고
export TORCH_NCCL_DUMP_ON_TIMEOUT=1

HEAD_NODE=$(scontrol show hostnames "$SLURM_JOB_NODELIST" | head -n 1)

# 한 노드의 torchrun이 실패로 끝나면 step 전체를 종료해 다른 노드가 행에 걸리지 않게 함
srun --kill-on-bad-exit=1 torchrun \
  --nnodes="$SLURM_NNODES" \
  --nproc-per-node=8 \
  --rdzv-backend=c10d \
  --rdzv-endpoint="${HEAD_NODE}:29400" \
  --rdzv-id="$SLURM_JOB_ID" \
  --max-restarts=2 \
  train.py
rc=$?

# 실패했고 재제출 횟수가 남았으면 다시 큐에 넣음.
# 문제 노드는 prolog나 헬스체크가 drain하므로 같은 노드에 다시 배정되지 않음.
if [ "$rc" -ne 0 ] && [ "${SLURM_RESTART_COUNT:-0}" -lt 5 ]; then
  scontrol requeue "$SLURM_JOB_ID"
fi
exit "$rc"
```

Prolog (slurm.conf의 `Prolog=`):

```bash
#!/bin/bash
# 기대값과 경로는 클러스터에 맞게 수정
EXPECTED_GPUS=8
EXPECTED_IB_PORTS=8

fail() { echo "prolog: $1" >&2; exit 1; }

# GPU 개수
[ "$(nvidia-smi -L | wc -l)" -eq "$EXPECTED_GPUS" ] || fail "GPU 개수 불일치"

# 이전 잡이 남긴 GPU 프로세스
[ -z "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader)" ] || fail "남은 GPU 프로세스"

# DCGM 빠른 진단 (Hopper 기준 2.5초 이내)
out=$(dcgmi diag -r 1 2>&1) || fail "dcgmi diag -r 1 실패"
echo "$out" | grep -q "Fail" && fail "dcgmi diag -r 1 항목 실패"

# IB 포트 상태
[ "$(ibstat | grep -c 'State: Active')" -ge "$EXPECTED_IB_PORTS" ] || fail "Active IB 포트 부족"

exit 0
```

- Prolog가 0이 아닌 값으로 끝나면 Slurm은 노드를 DRAIN으로 바꾸고 잡을 다시 큐에 넣습니다. 기본으로는 잡이 hold 상태로 들어가므로, 자동으로 다시 돌게 하려면 `SchedulerParameters`에 `nohold_on_prolog_fail`을 넣습니다.
- 주기적인 노드 점검은 `HealthCheckProgram`(예: LBNL NHC)과 `HealthCheckInterval`로 설정합니다.
- 시간 제한이나 유지보수로 끝날 때를 대비해 `--signal=<신호>@<초>`로 미리 신호를 받아 체크포인트를 저장할 수 있습니다. 신호가 torchrun을 거쳐 워커까지 전달되는지 미리 테스트해 둡니다.

### 5.6 Kubernetes

- NVIDIA device plugin은 치명적인 XID가 난 GPU를 Unhealthy로 표시해 새 Pod에 할당하지 않습니다.
- 문제 노드는 `kubectl cordon`이나 taint로 스케줄링에서 뺍니다.
- 재시작은 JobSet의 `failurePolicy.maxRestarts`나 Kubeflow Trainer 같은 컨트롤러가 맡습니다.
- Pod는 종료될 때 SIGTERM을 받고, `terminationGracePeriodSeconds`(기본 30초)가 지나면 강제 종료됩니다. 그 안에 체크포인트를 저장하거나 유예 시간을 늘립니다.
- 컨테이너에는 init(tini, `shareProcessNamespace: true`)을 두어 좀비 프로세스를 회수합니다(2.4절).

### 5.7 복구 시간 줄이기

- 예비 노드를 확보해 두면 수리를 기다리지 않고 바로 재시작할 수 있습니다.
- 재시작 시간은 스케줄링, 컨테이너 이미지 pull, NCCL 초기화, 체크포인트 로드, `torch.compile` 컴파일로 이뤄집니다. 이미지는 노드에 미리 받아 두고, 체크포인트는 병렬로 읽고, 컴파일 결과는 캐시합니다.
- NVRx는 잡을 다시 스케줄링하지 않고 실행 중인 잡 안에서 워커를 재시작하는 기능을 제공합니다(실험적 프로젝트, PyTorch 2.9 이상).

---

## 6. 참고 자료

- The Llama 3 Herd of Models, 3.3.4절: https://arxiv.org/abs/2407.21783
- NVIDIA Xid Catalog: https://docs.nvidia.com/deploy/xid-errors/analyzing-xid-catalog.html
- DCGM Diagnostics: https://docs.nvidia.com/datacenter/dcgm/latest/user-guide/dcgm-diagnostics.html
- DCGM Health and Diagnostics: https://docs.nvidia.com/datacenter/dcgm/latest/user-guide/feature-overview.html
- dcgm-exporter 기본 counters CSV: https://github.com/NVIDIA/dcgm-exporter/blob/main/etc/default-counters.csv
- PyTorch Flight Recorder: https://docs.pytorch.org/tutorials/unstable/flight_recorder_tutorial.html
- PyTorch DCP 비동기 저장: https://docs.pytorch.org/tutorials/recipes/distributed_async_checkpoint_recipe.html
- NCCL RAS: https://docs.nvidia.com/deeplearning/nccl/user-guide/docs/troubleshooting/ras.html
- NVIDIA Resiliency Extension (NVRx): https://github.com/NVIDIA/nvidia-resiliency-ext
- J. W. Young, "A first order approximation to the optimum checkpoint interval", Communications of the ACM, 1974
