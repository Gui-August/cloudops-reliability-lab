import json
import subprocess
from pathlib import Path

result = subprocess.run(
    ["kubectl", "get", "deployment", "grafana",
     "-n", "observability", "-o", "json"],
    capture_output=True,
    text=True,
    check=True
)

deployment = json.loads(result.stdout)

spec = deployment["spec"]
template = spec["template"]
pod_spec = template["spec"]

# Evita executar dois Grafanas durante atualizações.
spec["strategy"] = {"type": "Recreate"}

# Substitui apenas o volume temporário.
for volume in pod_spec["volumes"]:
    if volume["name"] == "storage":
        volume.pop("emptyDir", None)
        volume["persistentVolumeClaim"] = {
            "claimName": "grafana-storage"
        }

# O PVC local-path está vinculado ao nó server-0.
pod_spec["nodeSelector"] = {
    "kubernetes.io/hostname": "k3d-xp-sre-lab-server-0"
}

# Gerar somente os campos necessários ao apply.
manifest = {
    "apiVersion": "apps/v1",
    "kind": "Deployment",
    "metadata": {
        "name": "grafana",
        "namespace": "observability"
    },
    "spec": spec
}

# Remover campos gerenciados pelo Kubernetes.
for key in (
    "replicas",
    "progressDeadlineSeconds",
    "revisionHistoryLimit"
):
    manifest["spec"].pop(key, None)

Path("observability/grafana-pvc-deployment.json").write_text(
    json.dumps(manifest, indent=2),
    encoding="utf-8"
)

print("Manifesto preparado com sucesso.")
