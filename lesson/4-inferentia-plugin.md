AWS Inferentia2(Inf2) 인스턴스의 Neuron Cores 및 Devices를 쿠버네티스 스케줄러가 정상적으로 인식하게 하려면, AWS에서 제공하는 공식 AWS Neuron Helm 차트를 사용하는 것이 가장 깔끔하고 권장되는 방법입니다.
이 차트를 설치하면 Neuron Device Plugin 뿐만 아니라 토폴로지 기반의 최적 스케줄링을 돕는 Neuron Scheduler Extension, 노드 장애를 감지하는 Node Problem Detector까지 일괄적으로 설치할 수 있습니다.

```
# Helm을 통해 AWS 공용 ECR OCI 레지스트리의 차트 가져오기 및 설치
helm upgrade --install neuron-helm-chart oci://public.ecr.aws/neuron/neuron-helm-chart \
  --namespace kube-system \
  --create-namespace \
  --wait
```

* DaemonSet 확인 (Device Plugin이 잘 뜨는지)
```
kubectl get ds neuron-device-plugin -n kube-system
```

* 노드가 Neuron Cores를 인식했는지 확인
```
kubectl get nodes "-o=custom-columns=NAME:.metadata.name,NeuronCore:.status.allocatable.aws\.amazon\.com/neuroncore,NeuronDevice:.status.allocatable.aws\.amazon\.com/neuron"
```
결과 예시 (inf2.xlarge 기준): NeuronCore에 2가 정상적으로 찍히면 성공입니다! (칩 1개당 NeuronCore가 2개 포함되어 있음)
