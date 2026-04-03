# The runtime module
import os
import json
import tarfile
import tempfile
import shutil
import subprocess

DOCKSMITH_HOME = os.path.expanduser("~/.docksmith")
IMAGES_DIR = os.path.join(DOCKSMITH_HOME, "images")
LAYERS_DIR = os.path.join(DOCKSMITH_HOME, "layers")


# --------------------------
# LOAD IMAGE MANIFEST
# --------------------------
def load_manifest(image_tag):
    if ":" not in image_tag:
        raise Exception("Image must be in format name:tag")

    name, tag = image_tag.split(":")
    path = os.path.join(IMAGES_DIR, f"{name}_{tag}.json")

    if not os.path.exists(path):
        raise Exception(f"Image {image_tag} not found")

    with open(path, "r") as f:
        return json.load(f)


# --------------------------
# SAFE TAR EXTRACTION (path traversal fix applied)
# --------------------------
def extract_layers(layers, rootfs):
    for layer in layers:
        digest = layer["digest"].replace("sha256:", "")
        layer_path = os.path.join(LAYERS_DIR, digest + ".tar")

        if not os.path.exists(layer_path):
            raise Exception(f"Layer {digest} missing on disk")

        with tarfile.open(layer_path, "r") as tar:
            safe_root = os.path.realpath(rootfs) + os.sep
            for member in tar.getmembers():
                member_path = os.path.join(rootfs, member.name)
                if not os.path.realpath(member_path).startswith(safe_root):
                    raise Exception(f"Unsafe tar extraction detected: {member.name}")

            tar.extractall(path=rootfs)


# --------------------------
# RUN COMMAND (used by build engine for RUN instruction)
# --------------------------
def run_command(cmd_str, build_root, env_vars, workdir="/"):
    """
    Executes a shell command inside build_root using unshare
    for isolation. Works without root in WSL/Linux.
    Same isolation primitive as run_container.
    """
    rootfs = os.path.realpath(build_root)

    # Defensive check — enforce absolute workdir
    if not workdir.startswith("/"):
        raise Exception(f"Invalid WORKDIR '{workdir}': must be absolute path starting with /")

    # Clean minimal env + injected build vars only
    env = {"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"}
    env.update(env_vars)

    # cd into workdir first, fail loudly if it doesn't exist
    cd_cmd = f"cd {workdir} || exit 1"

    full_cmd = [
        "unshare",
        "--user",
        "--map-root-user",
        "--mount",
        "--pid",
        "--fork",
        "chroot", rootfs,
        "/bin/sh", "-c",
        f"{cd_cmd} && {cmd_str}"
    ]

    try:
        result = subprocess.run(full_cmd, env=env)
    except FileNotFoundError:
        raise Exception("unshare not available — isolation is required. Install util-linux.")

    if result.returncode != 0:
        raise Exception(f"RUN command failed with exit code {result.returncode}: {cmd_str}")

    return result.returncode


# --------------------------
# RUN PROCESS IN CONTAINER
# --------------------------
def run_in_container(rootfs, cmd, env_vars, workdir):

    # Defensive check — enforce absolute workdir
    if not workdir.startswith("/"):
        raise Exception(f"Invalid WORKDIR '{workdir}': must be absolute path starting with /")

    safe_root = os.path.realpath(rootfs)

    # cd into workdir, fail loudly if it doesn't exist
    cd_cmd = f"cd {workdir} || exit 1"

    if len(cmd) == 3 and cmd[0] == "/bin/sh" and cmd[1] == "-c":
        shell_cmd = f"{cd_cmd} && {cmd[2]}"
    else:
        shell_cmd = f"{cd_cmd} && " + " ".join(cmd)

    full_cmd = [
        "unshare",
        "--user",
        "--map-root-user",
        "--mount",
        "--pid",
        "--fork",
        "chroot", safe_root,
        "/bin/sh", "-c",
        shell_cmd
    ]

    # Minimal env — no host env leak
    env = {"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"}
    env.update(env_vars)

    try:
        result = subprocess.run(full_cmd, env=env)
    except FileNotFoundError:
        raise Exception("unshare not available — isolation is required. Install util-linux.")

    exit_code = result.returncode
    print(f"Container exited with code {exit_code}")
    return exit_code


# --------------------------
# MAIN RUNTIME FUNCTION
# --------------------------
def run_container(image_tag, cmd_override=None, env_override=None):

    manifest = load_manifest(image_tag)

    config = manifest.get("config", {})
    layers = manifest.get("layers", [])

    # Step 1: create rootfs
    rootfs = tempfile.mkdtemp()

    try:
        # Step 2: extract layers
        extract_layers(layers, rootfs)

        # Step 3: minimal env — no host env leak
        env = {"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"}

        # Image ENV
        for item in config.get("Env", []):
            key, val = item.split("=", 1)
            env[key] = val

        # Override ENV (-e flags take precedence)
        if env_override:
            for k, v in env_override.items():
                env[k] = v

        # Step 4: determine command
        if cmd_override:
            cmd = cmd_override
        else:
            cmd = config.get("Cmd")

        if not cmd or not isinstance(cmd, list):
            raise Exception("Invalid or missing CMD. Define CMD in Docksmithfile or pass a command at runtime.")

        # Step 5: working directory
        workdir = config.get("WorkingDir", "/")

        # WORKDIR must exist in container — build engine is responsible for creating it
        full_workdir = os.path.join(rootfs, workdir.lstrip("/"))
        if not os.path.exists(full_workdir):
            raise Exception(f"WORKDIR '{workdir}' does not exist in container filesystem. Create it during build.")

        # Step 6: run container
        return run_in_container(rootfs, cmd, env, workdir)

    finally:
        # Step 7: cleanup always runs even if above fails
        shutil.rmtree(rootfs)