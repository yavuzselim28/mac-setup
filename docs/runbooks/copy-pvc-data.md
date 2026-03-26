# Copy Data Between PVCs

## Problem
When a Helm release name changes, a new empty PVC is created.
The old PVC still contains the data (e.g. Ollama models) but the new Pod uses the new empty PVC.

## When do I need this?
- After renaming a Helm release
- After migrating from manual `helm install` to ArgoCD
- When moving data from one PVC to another

## Solution
Create a temporary Pod that mounts both PVCs and copies the data.

## Steps

### 1. Check which PVCs exist
```bash
kubectl get pvc -n <namespace>
```

### 2. Create the copy Pod
```bash
cat > /tmp/copy-pod.yaml << 'YAML'
apiVersion: v1
kind: Pod
metadata:
  name: ollama-copy
  namespace: <namespace>
spec:
  containers:
    - name: copy
      image: <any-image-already-in-cluster>
      command: ["sh", "-c", "cp -av /old/. /new/ && echo DONE"]
      volumeMounts:
        - name: old-storage
          mountPath: /old
        - name: new-storage
          mountPath: /new
  volumes:
    - name: old-storage
      persistentVolumeClaim:
        claimName: <source-pvc-name>
    - name: new-storage
      persistentVolumeClaim:
        claimName: <destination-pvc-name>
  restartPolicy: Never
YAML

kubectl apply -f /tmp/copy-pod.yaml
```

### 3. Watch the logs
```bash
kubectl logs -n <namespace> ollama-copy -f
```
Wait for `DONE` at the end.

### 4. Cleanup
```bash
kubectl delete pod ollama-copy -n <namespace>
```

### 5. Restart the Deployment
```bash
kubectl rollout restart deployment <deployment-name> -n <namespace>
```

## Command Explanation

| Command | Meaning |
|---------|---------|
| `sh -c` | Open a shell and execute the following command |
| `cp` | Copy |
| `-a` | Archive mode — preserves permissions, timestamps, and copies recursively |
| `-v` | Verbose — shows each file being copied |
| `/old/.` | Everything inside /old including hidden files |
| `&& echo DONE` | Print DONE only if copy was successful |
| `restartPolicy: Never` | Pod runs once and stops, does not restart |

## Notes
- `ReadWriteOnce` PVCs can only be mounted by one Pod at a time
- Make sure the source PVC is not mounted by another Pod before copying
- Use an image that is already in the cluster if there is no internet access
