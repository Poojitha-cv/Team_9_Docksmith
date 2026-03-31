import os
import tarfile
import hashlib

LAYER_DIR = os.path.expanduser("~/.docksmith/layers")


def create_layer(root_path, files):

    os.makedirs(LAYER_DIR, exist_ok=True)

    temp_tar = os.path.join(LAYER_DIR, "temp.tar")

    with tarfile.open(temp_tar, "w") as tar:
        for file in sorted(files):
            full_path = os.path.join(root_path, file)

            if not os.path.exists(full_path):
                continue

            info = tar.gettarinfo(full_path, arcname=file)
            info.mtime = 0  # deterministic

            with open(full_path, "rb") as f:
                tar.addfile(info, f)

    # compute sha
    sha = hashlib.sha256()
    with open(temp_tar, "rb") as f:
        while chunk := f.read(8192):
            sha.update(chunk)

    digest = sha.hexdigest()

    final_name = f"{digest}.tar"
    final_path = os.path.join(LAYER_DIR, final_name)

    os.rename(temp_tar, final_path)

    size = os.path.getsize(final_path)

    return {
        "digest": f"sha256:{digest}",
        "file": final_name,
        "size": size
    }