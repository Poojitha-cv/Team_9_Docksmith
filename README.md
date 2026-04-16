**Docksmith**

Docksmith is a simplified Docker-like container system built from scratch. It demonstrates image building, caching, layering, and process isolation using Linux primitives.

**FEATURES**

Custom CLI (docksmith.py)
Supports instructions: FROM, COPY, RUN, WORKDIR, ENV, CMD
Layer-based image system
Deterministic build caching
Process isolation using unshare and chroot
Fully offline (no network required)

**PROJECT STRUCTURE**

docksmith/
├── docksmith.py
├── build_engine.py
├── runtime.py
├── parser.py
├── cache.py
├── manifest.py
├── layer_manager.py
├── import_base_image.py
├── Docksmithfile
├── run_demo.sh

SETUP

Install dependencies:

sudo apt update
sudo apt install python3 util-linux

**Import base image:**

python3 import_base_image.py alpine.tar alpine:3.18

**BUILD IMAGE**

python3 docksmith.py build -t myapp:latest .

**LIST IMAGES**

python3 docksmith.py images

**RUN CONTAINER**

python3 docksmith.py run myapp:latest

**Run with environment override:**

python3 docksmith.py run -e NAME=OVERRIDE myapp:latest

**REMOVE IMAGE**

python3 docksmith.py rmi myapp:latest

**DEMO SCRIPT**

chmod +x run_demo.sh
./run_demo.sh

**IMAGE STORAGE**

Images stored in:
~/.docksmith/images/

Layers stored in:
~/.docksmith/layers/

**View manifest:**

cat ~/.docksmith/images/myapp_latest.json

**BUILD CACHE**

CACHE HIT → reuse layer
CACHE MISS → rebuild layer
Any change invalidates next steps

**ISOLATION**

Uses unshare + chroot
Same mechanism for build and run
Container cannot access host filesystem

**CONSTRAINTS**

No Docker or external runtimes
No internet during build/run
Linux required
Layers are immutable

**DEMO FLOW**

Cold build → CACHE MISS
Warm build → CACHE HIT
Modify file → cache invalidation
List images
Run container
ENV override
Isolation test
Remove image

**CONCLUSION**

Docksmith demonstrates:

Layered filesystem
Content-addressable storage
Build caching
Process isolation
