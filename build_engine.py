import json
import os
import subprocess
import shutil
import glob
import tarfile
import hashlib
import time
import shlex

from parser import parse_docksmithfile
from manifest import create_manifest
from layer_manager import create_layer


def snapshot_files(root):
    state = {}
    for root_dir, _, files in os.walk(root):
        for f in files:
            path = os.path.join(root_dir, f)
            rel = os.path.relpath(path, root)
            with open(path, "rb") as fp:
                state[rel] = hashlib.sha256(fp.read()).hexdigest()
    return state


def hash_files(file_list, context):
    hashes = {}
    for file in sorted(file_list):
        full = os.path.join(context, file)
        if os.path.isfile(full):
            with open(full, "rb") as f:
                hashes[file] = hashlib.sha256(f.read()).hexdigest()
    return hashes


# ✅ FIXED FUNCTION
def load_base_image(image_name, build_root):

    # support empty base
    if image_name == "scratch":
        return None

    path = os.path.expanduser(f"~/.docksmith/images/{image_name.replace(':', '_')}.json")

    if not os.path.exists(path):
        raise Exception(f"Base image '{image_name}' not found")

    with open(path) as f:
        manifest = json.load(f)

    for layer in manifest.get("layers", []):
        digest = layer["digest"].split(":")[1]
        layer_file = os.path.expanduser(f"~/.docksmith/layers/{digest}.tar")

        if not os.path.exists(layer_file):
            raise Exception(f"Layer {digest} missing")

        with tarfile.open(layer_file) as tar:
            tar.extractall(build_root)

    return manifest


def execute_build(name, tag, context=".", no_cache=False):

    context = os.path.abspath(context)
    instructions = parse_docksmithfile(os.path.join(context, "Docksmithfile"))

    env_vars = {}
    layers = []
    cmd = []
    workdir = "/"
    pending_workdir = None

    build_root = "/tmp/docksmith_build"

    if os.path.exists(build_root):
        shutil.rmtree(build_root)

    os.makedirs(build_root)

    print("Starting Docksmith Build...\n")

    total = len(instructions)

    prev_state = {}

    for step, (inst, arg) in enumerate(instructions, start=1):

        prev_layer_digest = layers[-1]["digest"] if layers else None
        start = time.time()
        cache_status = ""

        if inst == "FROM":
            load_base_image(arg, build_root)
            prev_state = snapshot_files(build_root)

        elif inst == "WORKDIR":
            pending_workdir = arg

        elif inst == "ENV":
            key, value = arg.split("=", 1)
            env_vars[key] = value

        elif inst == "COPY":

            if pending_workdir:
                path = os.path.join(build_root, pending_workdir.lstrip("/"))
                os.makedirs(path, exist_ok=True)
                workdir = pending_workdir
                pending_workdir = None

            parts = shlex.split(arg)
            src, dest = parts

            dest_path = os.path.join(build_root, dest.lstrip("/"))
            os.makedirs(dest_path, exist_ok=True)

            matched = glob.glob(os.path.join(context, src), recursive=True)
            rel_files = [os.path.relpath(f, context) for f in matched]

            file_hashes = hash_files(rel_files, context)

            cache_hit = False
            if not no_cache:
                try:
                    from cache import cache_lookup
                    cache_hit = cache_lookup(
                        inst, arg, env_vars.copy(), workdir,
                        prev_layer_digest, context, file_hashes, layers
                    )
                except ImportError:
                    pass

            if cache_hit:
                cache_status = "[CACHE HIT]"
            else:
                cache_status = "[CACHE MISS]"

                for file in matched:
                    if os.path.isdir(file):
                        shutil.copytree(file, os.path.join(dest_path, os.path.basename(file)), dirs_exist_ok=True)
                    else:
                        shutil.copy2(file, os.path.join(dest_path, os.path.basename(file)))

                new_state = snapshot_files(build_root)

                changed = [
                    f for f in new_state
                    if f not in prev_state or prev_state[f] != new_state[f]
                ]

                layer = create_layer(build_root, changed)
                layer["createdBy"] = f"COPY {arg}"

                layers.append(layer)
                prev_state = new_state

        elif inst == "RUN":

            if pending_workdir:
                path = os.path.join(build_root, pending_workdir.lstrip("/"))
                os.makedirs(path, exist_ok=True)
                workdir = pending_workdir
                pending_workdir = None

            cache_hit = False
            if not no_cache:
                try:
                    from cache import cache_lookup
                    cache_hit = cache_lookup(
                        inst, arg, env_vars.copy(), workdir,
                        prev_layer_digest, context, {}, layers
                    )
                except ImportError:
                    pass

            if cache_hit:
                cache_status = "[CACHE HIT]"
            else:
                cache_status = "[CACHE MISS]"

                try:
                    from runtime import run_command
                    run_command(arg, build_root, env_vars)
                except ImportError:
                    subprocess.run(arg, shell=True, cwd=build_root, env={**os.environ, **env_vars})

                new_state = snapshot_files(build_root)

                changed = [
                    f for f in new_state
                    if f not in prev_state or prev_state[f] != new_state[f]
                ]

                layer = create_layer(build_root, changed)
                layer["createdBy"] = f"RUN {arg}"

                layers.append(layer)
                prev_state = new_state

        elif inst == "CMD":
            cmd = json.loads(arg)

        duration = round(time.time() - start, 2)

        if inst in ["COPY", "RUN"]:
            print(f"Step {step}/{total} : {inst} {arg} {cache_status} {duration}s")
        else:
            print(f"Step {step}/{total} : {inst} {arg}")

    env_list = [f"{k}={v}" for k, v in sorted(env_vars.items())]

    create_manifest(name, tag, layers, env_list, cmd, workdir)

    print("\nBuild Completed!")