## AWS 인퍼런시아 ##

```
cat <<EOF > nodepool-inferentia.yaml 
apiVersion: karpenter.sh/v1
kind: NodePool
metadata:
  name: inferentia
spec:
  template:
    metadata:
      labels:
        nodeType: "inferentia" # 필요에 따라 식별용 레이블 변경
    spec:
      requirements:
        - key: kubernetes.io/arch
          operator: In
          values: ["amd64"]
        - key: karpenter.sh/capacity-type
          operator: In
          values: ["spot", "on-demand"]
        - key: karpenter.k8s.aws/instance-category
          operator: In
          values: ["inf", "trn"] # AWS Inferentia(inf) 및 Trainium(trn) 인스턴스 지정
      nodeClassRef:
        group: karpenter.k8s.aws
        kind: EC2NodeClass
        name: inferentia
      expireAfter: 720h 
      taints:
      - key: "aws.amazon.com/neuron"    # aws-neuron-device-plugin 데몬이 인식하는 테인트 기본값
        value: "v1"                      # 해당 노드에는 Neuron 칩을 사용하는 Pod만 스케줄링되도록 제한
        effect: NoSchedule               
  limits:
    cpu: 1000
  disruption:
    consolidationPolicy: WhenEmpty       
    consolidateAfter: 20m
---
apiVersion: karpenter.k8s.aws/v1
kind: EC2NodeClass
metadata:
  name: inferentia
spec:
  role: "eksctl-KarpenterNodeRole-infer-on-eks"
  amiSelectorTerms:
    # al2023@latest 앨리어스는 Pod가 AWS Neuron 디바이스를 요청할 때 
    # Karpenter가 자동으로 AL2023 Neuron 최적화 AMI를 선택해 줍니다.
    - alias: al2023@latest
  subnetSelectorTerms:
    - tags:
        karpenter.sh/discovery: "infer-on-eks" 
  securityGroupSelectorTerms:
    - tags:
        karpenter.sh/discovery: "infer-on-eks" 
  blockDeviceMappings:
    - deviceName: /dev/xvda
      ebs:
        volumeSize: 300Gi
        volumeType: gp3
EOF
```
