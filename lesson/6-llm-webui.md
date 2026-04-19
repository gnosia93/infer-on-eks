
## Agentic AI 아키텍처 ##
![](https://github.com/gnosia93/eks-agentic-ai/blob/main/lesson/images/agentic-arch.png)

### Open WebUI 설치 ###
```
helm repo add open-webui https://helm.openwebui.com/
helm repo update
```
open-webui-values.yaml 파일을 만든다.
```
cat << 'EOF' > open-webui-values.yaml
ollama:
  enabled: false

# 일단 이 필드 빼두고 WebUI 띄우기 / 로그인 후 Settings에서 나중에 추가 가능
openaiBaseApiUrls: []
openaiApiKey: "dummy"

persistence:
  enabled: true
  size: 20Gi
  storageClass: gp3

service:
  type: LoadBalancer
  port: 80
#  annotations:
#    service.beta.kubernetes.io/aws-load-balancer-type: "external"
#    service.beta.kubernetes.io/aws-load-balancer-nlb-target-type: "ip"
#    service.beta.kubernetes.io/aws-load-balancer-scheme: "internet-facing"

resources:
  requests:
    cpu: "2"
    memory: "4Gi"
  limits:
    cpu: "4"
    memory: "8Gi"

extraEnvVars:
  - name: WEBUI_NAME
    value: "Agentic AI Workshop"
  - name: DEFAULT_USER_ROLE
    value: "user"
  - name: ENABLE_SIGNUP
    value: "true"
EOF
```
> [!TIP] 
> 현재 차트의 기본 values.yaml 확인    
> helm show values open-webui/open-webui > default-values.yaml  
> 
> 필요한 부분만 grep    
> grep -A1 -iE "openai|ollama|env" default-values.yaml    
>
> open-webui 삭제  
> helm uninstall open-webui -n webui

helm 차트를 이용하여 배포한다. 
```
helm upgrade --install open-webui open-webui/open-webui \
  -n webui --create-namespace \
  -f open-webui-values.yaml
```

파드를 확인한다. 
```
kubectl get pods -n webui
```
[결과]
```
NAME                                        READY   STATUS    RESTARTS   AGE
pod/open-webui-0                            1/1     Running   0          6m17s
pod/open-webui-pipelines-69bc6c5b55-t9gnh   1/1     Running   0          6m17s
pod/open-webui-redis-9f9f74bd4-knkzz        1/1     Running   0          6m17s
```

서비스를 조회한다.
```
kubectl get svc -n webui
```
[결과]
```
NAME                   TYPE           CLUSTER-IP       EXTERNAL-IP                                                                    PORT(S)        AGE
open-webui             LoadBalancer   172.20.58.54     aa4d05703f46e4cb8bbd4db68b1adb14-1250901711.ap-northeast-2.elb.amazonaws.com   80:32300/TCP   7m27s
open-webui-pipelines   ClusterIP      172.20.14.185    <none>                                                                         9099/TCP       7m27s
open-webui-redis       ClusterIP      172.20.137.186   <none>                                                                         6379/TCP       7m27s
```
