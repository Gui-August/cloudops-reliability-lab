import json
import subprocess
from pathlib import Path

result = subprocess.run(
    [
        "kubectl", "get", "deployment", "prometheus",
        "-n", "observability", "-o", "json"
    ],
    capture_output=True,
    text=True,
    check=True
)

deployment = json.loads(result.stdout)

spec = deployment["spec"]
pod_spec = spec["template"]["spec"]

# Evitar dois Prometheus usando o mesmo TSDB.
spec["strategy"] = {"type": "Recreate"}

# Vincular o pod ao nó onde está o PVC local-path.
pod_spec["nodeSelector"] = {
    **pod_spec.get("nodeSelector", {}),
    "kubernetes.io/hostname": "k3d-xp-sre-lab-server-0"
}

# Substituir apenas o volume de dados.
found = False

for volume in pod_spec["volumes"]:
    if volume["name"] == "data":
        volume.pop("emptyDir", None)
        volume["persistentVolumeClaim"] = {
            "claimName": "prometheus-storage"
        }
        found = True

if not found:
    raise RuntimeError("Volume 'data' não encontrado.")

# Preservar os demais campos existentes.
for key in (
    "replicas",
    "progressDeadlineSeconds",
    "revisionHistoryLimit"
):
    spec.pop(key, None)

manifest = {
    "apiVersion": "apps/v1",
    "kind": "Deployment",
    "metadata": {
        "name": "prometheus",
        "namespace": "observability"
    },
    "spec": spec
}

output = Path("observability/prometheus-pvc-deployment.json")
output.parent.mkdir(parents=True, exist_ok=True)

output.write_text(
    json.dumps(manifest, indent=2),
    encoding="utf-8"
)

print("Manifesto criado:", output)
print("Estratégia:", spec["strategy"])
print("Volume:", [
    v for v in pod_spec["volumes"]
    if v["name"] == "data"
])
