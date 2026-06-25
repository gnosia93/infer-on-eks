## GPU 노드풀 생성 ##
```
cat <<EOF > nodepool-gpu.yaml 
apiVersion: karpenter.sh/v1
kind: NodePool
metadata:
  name: gpu
spec:
  template:
    metadata:
      labels:
        nodeType: "nvidia" 
    spec:
      requirements:
        - key: kubernetes.io/arch
          operator: In
          values: ["amd64"]
        - key: karpenter.sh/capacity-type
          operator: In
          values: ["spot", "on-demand", "reserved"]
        - key: karpenter.k8s.aws/instance-category
          operator: In
          values: ["g", "p"]
      nodeClassRef:
        group: karpenter.k8s.aws
        kind: EC2NodeClass
        name: gpu
      expireAfter: 720h # 30 * 24h = 720h
      taints:
      - key: "nvidia.com/gpu"            # nvidia-device-plugin 데몬은 nvidia.com/gpu=present:NoSchedule 테인트를 Tolerate 한다. 
        value: "present"                 # value 값으로 present 와 다른값을 설정하면 nvidia-device-plugin 이 동작하지 않는다 (GPU를 찾을 수 없다)   
        effect: NoSchedule               # nvidia-device-plugin 이 GPU 를 찾으면 Nvidia GPU 관련 각종 테인트와 레이블 등을 노드에 할당한다.  
  limits:
    cpu: 1000
  disruption:
    consolidationPolicy: WhenEmpty       # 이전 설정값은 WhenEmptyOrUnderutilized / 노드의 잦은 Not Ready 상태로의 변경으로 인해 수정  
    consolidateAfter: 20m
---
apiVersion: karpenter.k8s.aws/v1
kind: EC2NodeClass
metadata:
  name: gpu
spec:
  role: "eksctl-KarpenterNodeRole-infer-on-eks"
  amiSelectorTerms:
    # Required; when coupled with a pod that requests NVIDIA GPUs or AWS Neuron
    # devices, Karpenter will select the correct AL2023 accelerated AMI variant
    # see https://aws.amazon.com/ko/blogs/containers/amazon-eks-optimized-amazon-linux-2023-accelerated-amis-now-available/
    # EKS GPU Optimized AMI: NVIDIA 드라이버와 CUDA 런타임만 포함된 가벼운 이미지 (Karpenter가 자동으로 선택 가능) 가 설치됨.
    # 특정 DLAMI 가 필요한 경우 - name : 필드에 정의해야 함. 
    - alias: al2023@latest
  subnetSelectorTerms:
    - tags:
        karpenter.sh/discovery: "training-on-eks" 
  securityGroupSelectorTerms:
    - tags:
        karpenter.sh/discovery: "training-on-eks" 
  blockDeviceMappings:
    - deviceName: /dev/xvda
      ebs:
        volumeSize: 300Gi
        volumeType: gp3
EOF
```
ec2nodeclass 와 nodepol 을 생성한다.
```
kubectl apply -f nodepool-gpu.yaml
```
ec2nodeclass 와 nodepol 의 READY 필드의 값이 True 임것을 확인한다.
```
kubectl get ec2nodeclass,nodepool
```
[결과]
```
NAME                                 READY   AGE
ec2nodeclass.karpenter.k8s.aws/gpu   True    17s

NAME                        NODECLASS   NODES   READY   AGE
nodepool.karpenter.sh/gpu   gpu         0       True    17s
```
