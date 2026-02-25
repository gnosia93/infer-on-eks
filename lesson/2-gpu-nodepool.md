
```
# 1. 저장소 클론
git clone https://github.com/coder/code-server
cd code-server

# GPU 리소스 요청
# code-server Helm Chart - GPU + LoadBalancer + 비밀번호 설정
# 사용법: helm upgrade --install vscode-gpu ci/helm-chart -f vscode-gpu-simple.yaml --namespace vscode --create-namespace

service:
  type: LoadBalancer
  port: 8080
extraArgs:
  - --auth
  - password
extraEnvVars:
  - name: PASSWORD
    value: "yourpassword"

resources:
  requests:
    memory: "8Gi"
    cpu: "4"
    nvidia.com/gpu: 1  # GPU 1개 요청
  limits:
    memory: "16Gi"
    cpu: "8"
    nvidia.com/gpu: 1

nodeSelector:
  nvidia.com/gpu: "true"

tolerations:
  - key: nvidia.com/gpu
    operator: Exists
    effect: NoSchedule

persistence:
  enabled: true
  size: 50Gi


# 2. LoadBalancer + 비밀번호 설정
helm upgrade --install code-server ci/helm-chart \
  --set service.type=LoadBalancer \
  --set extraArgs="{--auth,password}" \
  --set-string extraEnvVars[0].name=PASSWORD \
  --set-string extraEnvVars[0].value="yourpassword"

# GPU 설정으로 설치
helm install vscode-gpu ci/helm-chart \
  -f vscode-gpu-simple.yaml \
  --namespace vscode \
  --create-namespace

kubectl exec -n vscode -it $(kubectl get pod -n vscode -o jsonpath='{.items[0].metadata.name}') -- nvidia-smi

```
