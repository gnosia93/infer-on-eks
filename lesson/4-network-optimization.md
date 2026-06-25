EKS에서 GPU, CPU, 혹은 AWS Neuron(Inferentia)을 활용해 **분산 인퍼런스(Distributed Inference)**를 수행할 때 CoreDNS와 Kube-Proxy 최적화가 필수적인 이유는, 분산 인퍼런스의 아키텍처적 특성인 "극단적으로 높은 빈도의 내부 통신(High-Frequency East-West Traffic)" 때문입니다.
대규모 AI 모델(예: LLM)을 여러 노드나 칩에 쪼개어 서빙할 때, 이 두 컴포넌트가 병목 지점이 되면 아무리 비싼 GPU/Neuron 칩을 써도 성능이 나오지 않습니다. 구체적인 이유는 다음과 같습니다.

### 1. CoreDNS 최적화가 필요한 이유 (서비스 발견의 병목 제거) ###
분산 인퍼런스 환경에서는 하나의 요청을 처리하기 위해 내부의 여러 Worker Pod들이 서로를 찾고 통신해야 합니다.
*	DNS 질의 폭주 (Storm): 분산 인퍼런스 프레임워크(예: Ray, vLLM, TorchElastic 등)는 초기 구동 시점이나 요청 파이프라인 처리 시 내부 Pod의 도메인 이름(예: worker-1.inference.svc.cluster.local)을 집중적으로 조회합니다.
*	ndots:5 문제로 인한 지연: 쿠버네티스의 기본 DNS 설정(ndots:5) 때문에 내부 주소를 하나 찾을 때도 무조건 외부 도메인 서프릭스까지 붙여가며 최대 4~5번의 무의미한 DNS 요청을 보냅니다. CoreDNS가 이 부하를 견디지 못하면 **DNS Timeout(5초 지연)**이 발생하여 인퍼런스 응답 속도(Latency)가 튀게 됩니다.
*	💡 최적화 방법: CoreDNS의 복제본(Replica) 수를 늘리고 HPA를 설정하거나, 노드 로컬에서 DNS 캐싱을 수행하는 NodeLocal DNSCache를 반드시 도입해야 합니다. 또한 Pod 설정에서 ndots:1로 낮추는 것을 검토해야 합니다.

### 2. Kube-Proxy 최적화가 필요한 이유 (네트워크 포워딩 효율화) ###
Kube-Proxy는 쿠버네티스 서비스(Service)의 가상 IP로 들어오는 트래픽을 실제 인퍼런스 Pod로 라우팅해주는 역할을 합니다. 기본 설정인 iptables 모드는 분산 인퍼런스 환경에서 치명적인 한계가 있습니다.
*	iptables의 O(N) 탐색 한계: iptables 모드는 서비스와 Pod가 늘어날 때마다 규칙(Rule)을 순차적으로(Linear) 탐색합니다. 분산 인퍼런스로 인해 Pod 개수가 수백, 수천 개로 스케일아웃되면 네트워크 패킷 하나를 보낼 때마다 이 수많은 규칙을 처음부터 끝까지 훑어야 하므로 CPU 오버헤드가 커지고 패킷 전송이 느려집니다.
*	IPVS 모드의 O(1) 성능: Kube-Proxy를 IPVS(IP Virtual Server) 모드로 변경하면 해시 테이블을 사용하기 때문에 서비스/Pod 개수와 상관없이 항상 일정하고 극단적으로 빠른 훠워딩 성능을 보장합니다.
* 💡 최적화 방법: EKS 클러스터 생성 후 Kube-Proxy 설정을 mode: ipvs로 변경하고 필요한 커널 모듈(ip_vs, ip_vs_rr 등)을 로드하도록 세팅합니다. (최신 아키텍처에서는 Cilium 같은 eBPF 기반 CNI를 사용해 Kube-Proxy를 아예 대체하기도 합니다.)

### 🏎️ 결론: 대동맥이 막히면 심장이 뛰지 않는다 ###
GPU/Neuron 칩이 아무리 빠른 속도로 연산(Compute)을 끝내도, 분산 인퍼런스 프레임워크 내에서 "어느 노드로 패킷을 보내야 하는지 찾고(CoreDNS)", **"그 노드로 패킷을 전달하는 과정(Kube-Proxy)"**에서 수 밀리초(ms)씩 지연이 발생하면 전체 초당 토큰 생성 수(TPS)가 급감하고 칩들이 놀게 됩니다(GPU Underutilization).
따라서 연산 자원의 돈값을 제대로 치르게 하려면 이 두 가지 네트워크 인프라 최적화가 밑바탕에 깔려 있어야 합니다.
