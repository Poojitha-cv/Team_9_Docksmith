# runtime.py - Container Runtime
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
        raise Exception(f"Image '{image_tag}' not found in ~/.docksmith/images/")

    with open(path, "r") as f:
        return json.load(f)


# --------------------------
# SAFE TAR EXTRACTION
# Shared by both build engine and runtime — hard requirement satisfied.
# Skips (never raises on) entries that would escape rootfs.
# Works with Alpine-style tars that use relative paths like etc/ssl/certs.
# --------------------------
def safe_extract_tar(tar_path, rootfs):
    """
    Safely extract a tar archive into rootfs.
    Entries that would escape rootfs are silently skipped.
    Uses os.path.normpath (no filesystem access) to check paths,
    so it works correctly even when destination directories don't exist yet.
    """
    rootfs_abs = os.path.abspath(rootfs)

    with tarfile.open(tar_path, "r") as tar:
        for member in tar.getmembers():
            # --- Sanitize the member name ---
            name = member.name

            # Strip leading slashes and ./ repeatedly
            while True:
                if name.startswith("./"):
                    name = name[2:]
                elif name.startswith("/"):
                    name = name[1:]
                else:
                    break

            # Skip the root entry "." or empty names
            if not name or name == ".":
                continue

            # Use normpath (pure math, no filesystem calls) to resolve ".." etc.
            target_path = os.path.normpath(os.path.join(rootfs_abs, name))

            # Must stay inside rootfs
            if not target_path.startswith(rootfs_abs + os.sep) and target_path != rootfs_abs:
                # Silently skip — path traversal attempt
                continue

            # Override member name with the sanitized relative path
            member.name = name

            try:
                tar.extract(member, path=rootfs, set_attrs=False)
                # Re-apply mode bits only (skip uid/gid — we may not be root)
                full_path = os.path.join(rootfs, name)
                if not os.path.islink(full_path) and os.path.exists(full_path):
                    try:
                        os.chmod(full_path, member.mode)
                    except (OSError, PermissionError):
                        pass
            except (KeyError, AttributeError, tarfile.ExtractError, OSError):
                # Skip device files and other entries that need root
                continue


def extract_layers(layers, rootfs):
    """
    Extract all image layers in order into rootfs.
    Each layer is a delta tar; later layers overwrite earlier ones.
    """
    for layer in layers:
        digest = layer["digest"].replace("sha256:", "")
        layer_path = os.path.join(LAYERS_DIR, digest + ".tar")

        if not os.path.exists(layer_path):
            raise Exception(
                f"Layer file missing for digest {digest[:12]}. "
                f"The image may be broken. Rebuild the image."
            )

        safe_extract_tar(layer_path, rootfs)


# --------------------------
# RUN COMMAND
# Used by the build engine for RUN instructions.
# SAME isolation primitive (unshare + chroot) as run_container — hard requirement.
# --------------------------
def run_command(cmd_str, build_root, env_vars, workdir="/"):
    """
    Executes a shell command inside build_root using unshare + chroot.

    Parameters
    ----------
    cmd_str    : shell command string from the RUN instruction
    build_root : path to the assembled layer filesystem
    env_vars   : dict of ENV key=value pairs accumulated so far in the build
    workdir    : current WORKDIR value at the time the RUN instruction executes
                 (defaults to "/" if not set)
    """
    rootfs = os.path.realpath(build_root)

    if not workdir.startswith("/"):
        raise Exception(
            f"Invalid WORKDIR '{workdir}': must be an absolute path starting with /"
        )

    # Minimal env — no host environment leaks into the build
    env = {"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"}
    env.update(env_vars)

    cd_cmd = f"cd {workdir} || exit 1"

    full_cmd = [
        "unshare",
        "--user",
        "--map-root-user",
        "--mount",
        "--pid",
        "--fork",
        "--mount-proc",
        "chroot", rootfs,
        "/bin/sh", "-c",
        f"{cd_cmd} && {cmd_str}",
    ]

    try:
        result = subprocess.run(full_cmd, env=env)
    except FileNotFoundError:
        raise Exception(
            "unshare not found — process isolation is required. "
            "Install util-linux (sudo apt install util-linux)."
        )

    if result.returncode != 0:
        raise Exception(
            f"RUN command failed with exit code {result.returncode}: {cmd_str}"
        )

    return result.returncode


# --------------------------
# RUN PROCESS IN CONTAINER (internal helper)
# --------------------------
def run_in_container(rootfs, cmd, env_vars, workdir):
    """
    Launches cmd inside rootfs using unshare + chroot.
    Blocks until the process exits, then returns the exit code.
    Same isolation primitive as run_command — hard requirement satisfied.
    """
    if not workdir.startswith("/"):
        raise Exception(
            f"Invalid WORKDIR '{workdir}': must be an absolute path starting with /"
        )

    safe_root = os.path.realpath(rootfs)

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
        "--mount-proc",
        "chroot", safe_root,
        "/bin/sh", "-c",
        shell_cmd,
    ]

    env = {"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"}
    env.update(env_vars)

    try:
        result = subprocess.run(full_cmd, env=env)
    except FileNotFoundError:
        raise Exception(
            "unshare not found — process isolation is required. "
            "Install util-linux (sudo apt install util-linux)."
        )

    exit_code = result.returncode
    print(f"Container exited with code {exit_code}")
    return exit_code


# --------------------------
# MAIN RUNTIME ENTRY POINT
# Called by docksmith run <name:tag> [cmd] [-e KEY=VALUE ...]
# --------------------------
def run_container(image_tag, cmd_override=None, env_override=None):
    """
    Assembles the image filesystem from its layers into a temp directory,
    runs the container process in isolation, waits for exit, then cleans up.
    """
    manifest = load_manifest(image_tag)
    config = manifest.get("config", {})
    layers = manifest.get("layers", [])

    rootfs = tempfile.mkdtemp(prefix="docksmith_run_")

    try:
        # Extract all image layers in order into rootfs
        extract_layers(layers, rootfs)

        # Build the process environment — start clean, no host env leaks
        env = {"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"}

        for item in config.get("Env", []):
            key, val = item.split("=", 1)
            env[key] = val

        # -e overrides take precedence over image ENV
        if env_override:
            for k, v in env_override.items():
                env[k] = v

        # Determine command
        if cmd_override:
            cmd = cmd_override
        else:
            cmd = config.get("Cmd")

        if not cmd or not isinstance(cmd, list):
            raise Exception(
                "No CMD defined in the image and no command provided at runtime.\n"
                "Define CMD in the Docksmithfile or pass a command:\n"
                "  docksmith run name:tag /bin/sh"
            )

        # Resolve working directory (default: /)
        workdir = config.get("WorkingDir") or "/"

        full_workdir = os.path.join(rootfs, workdir.lstrip("/"))
        if not os.path.exists(full_workdir):
            raise Exception(
                f"WORKDIR '{workdir}' does not exist in the container filesystem.\n"
                f"Ensure the build engine creates it (WORKDIR instruction in Docksmithfile)."
            )

        return run_in_container(rootfs, cmd, env, workdir)

    finally:
        shutil.rmtree(rootfs, ignore_errors=True)
