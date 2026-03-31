import os
import json

ALLOWED = ["FROM", "COPY", "RUN", "WORKDIR", "ENV", "CMD"]

def parse_docksmithfile(filepath="Docksmithfile"):
    if not os.path.exists(filepath):
        raise FileNotFoundError("Docksmithfile not found")

    instructions = []

    with open(filepath) as f:
        lines = f.readlines()

    for i, line in enumerate(lines, start=1):
        line = line.strip()
        if not line:
            continue

        parts = line.split(maxsplit=1)
        inst = parts[0].upper()
        arg = parts[1] if len(parts) > 1 else ""

        if inst not in ALLOWED:
            raise ValueError(f"Invalid instruction '{inst}' at line {i}")

        # ENV validation
        if inst == "ENV" and "=" not in arg:
            raise ValueError(f"Invalid ENV format at line {i}")

        # CMD validation
        if inst == "CMD":
            try:
                parsed = json.loads(arg)
                if not isinstance(parsed, list):
                    raise ValueError
            except:
                raise ValueError(f"CMD must be JSON array at line {i}")

        instructions.append((inst, arg))

    return instructions