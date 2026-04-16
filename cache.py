# Cache.py - Implements caching logic for Dockerfile instructions
import hashlib
import json
import os

CACHE_INDEX = os.path.expanduser("~/.docksmith/cache/index.json")
LAYER_DIR = os.path.expanduser("~/.docksmith/layers")


# ---------- COMPUTE CACHE KEY ----------
def compute_cache_key(inst, arg, env_vars, workdir, prev_layer_digest, file_hashes):
    prev = prev_layer_digest or ""
    instruction = f"{inst} {arg}"
    wd = workdir or ""
    env_str = ",".join(f"{k}={v}" for k, v in sorted(env_vars.items()))
    files_str = ",".join(f"{k}={v}" for k, v in sorted(file_hashes.items()))
    combined = f"{prev}|{instruction}|{wd}|{env_str}|{files_str}"
    return hashlib.sha256(combined.encode()).hexdigest()


# ---------- LOAD INDEX ----------
def load_index():
    if os.path.exists(CACHE_INDEX):
        with open(CACHE_INDEX) as f:
            return json.load(f)
    return {}


# ---------- SAVE INDEX ----------
def save_index(index):
    os.makedirs(os.path.dirname(CACHE_INDEX), exist_ok=True)
    with open(CACHE_INDEX, "w") as f:
        json.dump(index, f, indent=2)


# ---------- CACHE LOOKUP ----------
def cache_lookup(inst, arg, env_vars, workdir, prev_layer_digest, context, file_hashes, layers):
    key = compute_cache_key(inst, arg, env_vars, workdir, prev_layer_digest, file_hashes)
    index = load_index()

    if key in index:
        layer_digest = index[key]["digest"].replace("sha256:", "")
        layer_file = os.path.join(LAYER_DIR, f"{layer_digest}.tar")

        # FIX: if layer file missing → treat as MISS
        if not os.path.exists(layer_file):
            return False

        layers.append(index[key]["layer"])
        return True  # HIT

    return False  # MISS


# ---------- CACHE STORE ----------
def cache_store(inst, arg, env_vars, workdir, prev_layer_digest, file_hashes, layer):
    key = compute_cache_key(inst, arg, env_vars, workdir, prev_layer_digest, file_hashes)
    index = load_index()
    index[key] = {
        "digest": layer["digest"],
        "layer": layer
    }
    save_index(index)
