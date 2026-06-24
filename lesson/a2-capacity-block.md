*	개념: 대규모 GPU 인스턴스(예: p5.48xlarge)를 특정 기간 동안 확정적으로 예약하여 사용할 수 있는 AWS 기능입니다.
*	적용: Karpenter가 긴급하게 대규모 GPU 스케일아웃을 시도할 때 발생할 수 있는 '용량 부족(ICE: Insufficient Capacity Error)' 리스크를 방지하기 위해, 예정된 피크 타임이나 대규모 벤치마크 테스트 시 Capacity Block을 EKS 노드 그룹과 연동하여 안정적인 자원을 확보합니다.
