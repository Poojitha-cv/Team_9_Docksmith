import json
import os
import hashlib
from datetime import datetime


def create_manifest(name, tag, layers, env, cmd, workdir):

    path = os.path.expanduser(f"~/.docksmith/images/{name}_{tag}.json")

    # 🔥 Preserve timestamp if file exists
    created_time = datetime.utcnow().isoformat()

    if os.path.exists(path):
        with open(path) as f:
            old = json.load(f)
            created_time = old.get("created", created_time)

    manifest = {
        "name": name,
        "tag": tag,
        "digest": "",
        "created": created_time,
        "config": {
            "Env": env,
            "Cmd": cmd,
            "WorkingDir": workdir
        },
        "layers": layers
    }

    data = json.dumps(manifest, sort_keys=True).encode()
    digest = hashlib.sha256(data).hexdigest()

    manifest["digest"] = f"sha256:{digest}"

    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, "w") as f:
        json.dump(manifest, f, indent=4)