tokenizer.apply_chat_template() 은
알파카 포멧의 데이터를 
```
{
  "instruction": "Kubernetes Pod가 CrashLoopBackOff일 때 디버깅 방법은?",
  "output": "kubectl describe pod, kubectl logs 순서로 확인하고..."
}
```
Qwen의 아래와 같은 포맷으로 변경한다. 
```
<|im_start|>system
You are a helpful DevOps and ML engineering assistant.<|im_end|>
<|im_start|>user
Kubernetes Pod가 CrashLoopBackOff일 때 디버깅 방법은?<|im_end|>
<|im_start|>assistant
kubectl describe pod, kubectl logs 순서로 확인하고...<|im_end|>
```




