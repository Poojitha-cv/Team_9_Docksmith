import sys, tarfile, json, hashlib, os

def import_image(tar_path, image_tag):
    name, tag = image_tag.split(":")
    images_dir = os.path.expanduser("~/.docksmith/images")
    layers_dir = os.path.expanduser("~/.docksmith/layers")

    with tarfile.open(tar_path) as tar:
        manifest = json.load(tar.extractfile("manifest.json"))
        config = json.load(tar.extractfile(manifest[0]["Config"]))

        layers = []
        for layer_path in manifest[0]["Layers"]:
            raw = tar.extractfile(layer_path).read()
            digest = hashlib.sha256(raw).hexdigest()

            with open(f"{layers_dir}/{digest}.tar", "wb") as f:
                f.write(raw)

            layers.append({
                "digest": f"sha256:{digest}",
                "size": len(raw),
                "createdBy": "import"
            })

    img = {
        "name": name,
        "tag": tag,
        "digest": "",
        "created": "2024-01-01T00:00:00",
        "config": {
            "Env": config.get("config", {}).get("Env") or [],
            "Cmd": config.get("config", {}).get("Cmd") or [],
            "WorkingDir": config.get("config", {}).get("WorkingDir") or "/"
        },
        "layers": layers
    }

    data = json.dumps(img, sort_keys=True).encode()
    img["digest"] = "sha256:" + hashlib.sha256(data).hexdigest()

    with open(f"{images_dir}/{name}_{tag}.json", "w") as f:
        json.dump(img, f, indent=2)

    print("Imported successfully")

import_image(sys.argv[1], sys.argv[2])
