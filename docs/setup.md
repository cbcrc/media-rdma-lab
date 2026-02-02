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

