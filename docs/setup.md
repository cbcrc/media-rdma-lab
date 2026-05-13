<!--
SPDX-FileCopyrightText: 2026 CBC/Radio-Canada
SPDX-License-Identifier: CC-BY-4.0
-->

# How to Set Up a Server for RDMA
This document provides a complete step-by-step procedure for preparing an Ubuntu server for RDMA (Remote Direct Memory Access).  
Explanations are included throughout to clarify what each component does and why each step is required.

---

## 1. Install Required RDMA Packages

RDMA relies on a combination of kernel modules, user-space libraries, diagnostic tools, and provider plugins.  
Installing these packages ensures the operating system can communicate with RDMA hardware and run RDMA-based applications.

### What This Section Does
- Installs the core RDMA subsystem utilities (`rdma-core`)
- Adds user-space verbs libraries (`libibverbs`, `librdmacm`)
- Provides diagnostics such as `ibv_devinfo` and `infiniband-diags`
- Installs compiler and build tools required for building RDMA software (e.g., libfabric)

### Procedure
1. Update package lists to get latest versions.
2. Install RDMA user-space libraries and diagnostic tools.
3. Install development libraries for verbs and RDMA CM.
4. Install compilation tools for building libfabric and fabtests.
5. Verify that RDMA hardware and drivers are detected.

### Commands
```bash
sudo apt update
sudo apt install -y rdma-core ibverbs-providers perftest infiniband-diags
sudo apt install -y ibverbs-utils
sudo apt install -y libibverbs-dev librdmacm-dev
sudo apt install -y autoconf automake libtool gcc g++ make
sudo apt install -y build-essential pkg-config git
```

### Verification

`ibv_devinfo` queries the verbs provider to ensure RDMA hardware is recognized by the system.
```bash
sudo ibv_devinfo
ibv_devinfo
```

If the NIC appears with attributes such as `hca_id`, `transport`, or `fw_ver`, RDMA is functioning correctly.

---

## 2. Download the Libfabric Source Code

Libfabric is a high-performance network library that provides fabric services for RDMA applications.
Many RDMA test suites (e.g., Fabtests) depend on it.

### Why This Matters

- Libfabric offers a common API for multiple transport types (verbs, RoCE, TCP, etc.)

- RDMA testing tools rely on the verbs provider inside Libfabric

- Building from source ensures you get the latest updates and bug fixes

### Procedure

1. Clone the upstream Libfabric GitHub repo.

2. Enter the directory to prepare for building.

### Commands
```bash
git clone https://github.com/ofiwg/libfabric.git
cd libfabric
```
--- 

## 3. Build and Install Libfabric

Compiling libfabric ensures that the RDMA verbs provider is correctly enabled and configured.
The build process generates both the library and the test suite tools.

### What These Steps Do

- `./autogen.sh` generates the build system files.

- `./configure --enable-verbs` ensures Libfabric builds with RDMA verbs support.

- `make -j` compiles using all CPU cores for speed.

- `sudo make install` installs libfabric into /usr/local/.

- `sudo ldconfig` tells the system about new shared libraries.

### Commands
***Important Note:** Make sure you run these commands from inside the libfabric directory.*
```bash
./autogen.sh
./configure --enable-verbs
make -j "$(nproc)"
sudo make install
sudo ldconfig
```
--- 

## 4. Validate the Installation

After installing libfabric, you should verify that both RDMA CM and the verbs provider are functional.
This ensures that your environment is ready for fabric testing (e.g., fabtests).

### Why These Checks Matter

- `librdmacm` handles connection management for RDMA—required for RoCE and IB.

- `fi_info` displays available Libfabric providers and confirms verbs support.

- If `verbs` appears as a provider, RDMA is fully functional at the user-space level.

### Procedure

1. Confirm that RDMA CM library files exist.

2. Check that the verbs provider is active inside libfabric.

### Commands
```bash
# Check RDMA (CM) support — required for many RDMA applications
whereis librdmacm.so

# Validate the verbs provider using Libfabric's info tool
fi_info
```

If you see provider: verbs in the output, the setup is correct and complete.

---

## 5. Intel Ethernet (ICE) and RDMA Driver Setup (E810 / X722)

Intel RDMA functionality depends on a tightly coupled stack between the Intel Ethernet driver (`ice`) and the RDMA driver (`irdma`).  
For Intel E810 and X722 controllers, both components must be compatible versions to ensure RDMA (RoCE/verbs) works correctly.

Official driver package:  
https://www.intel.com/content/www/us/en/download/19632/linux-rdma-driver-for-the-e810-and-x722-intel-ethernet-controllers.html

---

### What This Section Does

- Installs or updates the Intel Ethernet driver (`ice`)
- Installs the matching out-of-tree RDMA driver (`irdma`)
- Ensures kernel module compatibility between NIC and RDMA stack
- Places the compiled RDMA kernel module into the correct kernel path

---

### Important Compatibility Note

- `ice` and `irdma` **must come from compatible Intel releases**
- Mismatched versions may cause:
  - `Unknown symbol in module` errors
  - `modprobe irdma` failures
  - Missing RDMA devices in `ibv_devices`

---

## 5.1 Install / Update ICE Driver

### Procedure

1. Extract Intel `ice` driver package  
2. Build kernel module  
3. Install into kernel modules tree  
4. Refresh module dependency database  

### Commands

```bash
tar -xvzf ice-*.tar.gz
cd ice-*/

make -j "$(nproc)"
sudo make install
sudo depmod -a

