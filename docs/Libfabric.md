# Libfabric Fabtests User Guide

This guide explains how to run and verify **Libfabric fabtests** across test servers.  
It is intended for users who already have **Libfabric** and **fabtests** installed and configured.  
If you have not completed setup, refer to the **[setup.md](./setup.md)** file before proceeding.

---

## 1. Overview

Fabtests is a functional and performance test suite for **Libfabric**.  
It validates communication between endpoints using different providers (e.g., TCP, Verbs)  
and ensures correct RDMA behavior and performance.

This document describes:
- How to prepare the environment for testing  
- How to run fabtests between a server and client  
- How to interpret results and handle common issues  

For deeper explanations of test parameters and fabric architecture, refer to the **[RDMA Confluence](https://cbcradiocanada.atlassian.net/wiki/spaces/ENG/pages/5597298950/RDMA+Network)** page.

---

## 2. Pre-Requisites

Before running any fabtests:

- **Libfabric and Fabtests must be installed.**  
  If not, follow the installation steps in [setup.md](./setup.md).

- **Server Access:**  
  You must have SSH access to both the **server** and **client** test nodes.  Each node is password-protected.  
  - If you do not know the credentials, reach out to the **RDMA Team** for access.

- **Test Directory:**  
  All tests must be executed within the `fabtests` directory structure under the Libfabric source.  
  Running tests from the wrong directory often leads to errors.

---

## 3. Accessing the Test Environment

1. SSH into the designated **server node**:

   ```bash
   ssh lab@<server_ip>
    ```
2. Navigate to the fabtests directory:

    ```bash
    cd ~/libfabric/fabtests
    ```

3. Confirm that subdirectories such as functional and benchmarks exist:
    ```bash
    ls
    # Example output:
    # benchmarks  functional  ...
    ```
4. Repeat the same steps on the client node before beginning tests.

### Test Naming and Categories
|Category|Directory|Description|
|--------|---------|-----------|
|Functional|	~/libfabric/fabtests/functional|	Tests core Libfabric functionality such as messaging, RMA, and atomic operations.
Benchmark|	~/libfabric/fabtests/benchmarks|	Measures performance metrics such as bandwidth and latency.
Unit Tests|	~/libfabric/fabtests/unit|	Tests individual library functions; used primarily for debugging builds.
Utility / Scripts|	~/libfabric/fabtests/scripts|	Contains helper and setup scripts for automated runs.

**When unsure where a test resides, use the find command to locate it:**

```bash
    find ~/libfabric/fabtests -type f -name "fi_*"
```
---
## 4. Running Fabtests

Fabtests are generally run as paired commands — one on the server and one on the client.

Each test binary supports the following general syntax:

```bash
# On Server:
<test_name> -p <provider> -s <rdma_interface_ip>

# On Client:
<test_name> <rdma_interface_ip> -p <provider>

```
- Where:

    - `test_name` is the fabtest executable (e.g., fi_msg, fi_msg_bw, fi_rdm_pingpong)

    - `provider` specifies the communication provider (tcp or verbs)

    - `rdma_interface_ip` is the IP address of the network interface for the servers (can be retrieved by running `ip a`)
     

**All tests should be run from within the correct directory (e.g., functional, benchmarks) depending on the test type.**


### Interpreting Test Results

- **PASS** indicates successful connection establishment and data exchange.
    - Successful tests typically print summary results followed by a PASS status.

- **FAIL** often means missing dependencies, incorrect directory, or network issues.
    - Failures may print FAIL or indicate missing libraries or unsupported features.

- For bandwidth tests, higher MB/s indicates better performance.
- For latency tests, lower µs values indicate better performance.

**Record all results for comparison against baseline TCP tests.**

---

## 5. Example Tests (Verbs Provider)

Below are examples of two common fabtests executed using the verbs provider.

#### Example: `fi_msg` (Functional Message Transfer Test)

**Server Side:**
```bash
cd ~/libfabric/fabtests/functional
./fi_msg -p verbs -s <rdma_interface_ip>
```
**Client Side:**
```bash
cd ~/libfabric/fabtests/functional
./fi_msg <rdma_interface_ip> -p verbs
```
#### Example Successful Output:

**Server Side:**
![Successful Test Output Screenshot](./assets/images/Succesful_test_server.png)
**Client Side:**
![Successful Test Output Screenshot](./assets/images/Succesful_test_client.png)

---

## 6. Modifying Functional Tests (To be Expanded)
(Expand here)

---

## 7. Common Issues and Tips (To Be Expanded)
**Issues Encountered:**
(Expand here)

**Below are general recommendations to ensure smooth testing:**

- Always navigate to the correct subdirectory (`functional`, `benchmarks`, etc.) before running a test.

- Verify that both nodes can reach each other via `ping` before starting a test.

- Confirm that the correct provider is available by running:

    ```bash
    fi_info -p <provider>
    ```

- If you encounter connection errors, ensure the IP used matches the server’s RDMA-capable interface.

- Run tests sequentially; avoid running multiple fabtests in parallel on the same NIC.
    - More experimentation is needed for parallel data exchange

---

## 8. References
- Libfabric Documentation: https://ofiwg.github.io/libfabric/

- [setup.md](./setup.md) – Instructions for Libfabric and Fabtests installation

- [Team Confluence Page](https://cbcradiocanada.atlassian.net/wiki/spaces/ENG/pages/5597298950/RDMA+Network) – Detailed explanations of test behavior and provider-level analysis

- Reach out to Alexandre Dugas and Sunday Nyamweno for more detail
