<!--
SPDX-FileCopyrightText: 2026 CBC/Radio-Canada
SPDX-License-Identifier: CC-BY-4.0
-->

# MCM-Intel RDMA Build and Testing Guide

This document provides a complete walkthrough for setting up and testing Intel's Media Communications Mesh (MCM) with RDMA capabilities on Ubuntu systems. It covers installation prerequisites, build instructions, environment configuration, and video streaming tests using both TCP and RDMA Verbs providers.

## 1. Key MCM Components

| Component | Function | Role |
| --------- | -------- | ---- |
| **mesh-agent** | Control plane service for managing MCM topology | Runs on receiver or control node |
| **media proxy** | Data plane proxy for media stream routing | Runs on both sender and receiver |
| **FFmpeg MCM plugin** | Custom FFmpeg output/input format for MCM streams | Used for video encoding and testing |

## 2. Installation / Build Process

The following process is required to prepare two new swrvers for the MCM RDMA communication.

## Prerequisites

**According to Intel's official documentation the following are needed to build and run the MCM application:**

- Linux server
- RDMA-capable Network Interface Card (NIC)
- Updated NIC drivers and firmware – Strong recommendation is to update them

## Build and install steps

1. Clone the repository

   ```bash
   git clone https://github.com/OpenVisualCloud/Media-Communications-Mesh.git
   ```

2. Navigate to the Media-Communications-Mesh directory

    ```bash
    cd Media-Communications-Mesh
    ```

3. Install dependencies. There are two options.

    **Use environment preparation scripts** `setup_build_env.sh`

    Run the following commands:

    ```bash
    sudo ./scripts/setup_build_env.sh
    sudo ./scripts/setup_ice_irdma.sh all
    ```

    - `setup_build_env.sh` prepares the whole build stack and build dependencies that are mandatory for bare metal version of MCM
    - `setup_ice_irdma.sh all` to download, patch, setup and install ICE as well as iRDMA drivers

    **Reboot the host after the scripts are executed.**

    ```bash
    sudo reboot
    ```

4. Build the Media Communications Mesh software components

    Run the build script

    ```bash
    sudo ./build.sh
    ```

    This script builds and installs the following software components
    - SDK API library
       - File name: `libmcm_dp.so`
       - Header file to include: [`mesh_dp.h`](../../sdk/include/mesh_dp.h)
    - Media Proxy
       - Executable file name: `media_proxy`
    - Mesh Agent
       - Executable file name: `mesh-agent`

## 4. Testing

A demo of how it should be running, ensure you're in the **Media-Communications-Mesh** directory:

**Server 1 (Receiver side setup)**

```bash
mesh-agent 

# Open another terminal

export NODE_1_IP=<rdma_interface_ip> && export NODE_1_PF_IP=<rdma_interface_ip> && export NODE_1_VF=<pci_express_address> && export NODE_1_VF_IP=<rdma_interface_ip>

sudo media_proxy -d $NODE_1_VF -i $NODE_1_VF_IP --rdma_ip=$NODE_1_PF_IP --agent $NODE_1_IP:50051 -p 9200-9299

```

**Server 2 (Sender side setup)**

```bash

export NODE_2_IP=<rdma_interface_ip> && export NODE_2_PF_IP=<rdma_interface_ip> && export NODE_2_VF=0000:2f:00.1 && export NODE_2_VF_IP=<rdma_interface_ip> && NODE_1_IP=<rdma_interface_ip>

sudo media_proxy -d $NODE_2_VF -i $NODE_2_VF_IP --rdma_ip=$NODE_2_PF_IP --agent $NODE_1_IP:50051  -p 9200-9299  

#Open another terminal
Using UDP:
sudo ffmpeg -f mcm -conn_type multipoint-group -urn intel-1-rdma -rdma_provider verbs -rdma_num_endpoints 1 -video_size 1920x1080 -frame_rate 30 -payload_type 96 -i 0 -vcodec libx264 -r 30 -b:v 32000k -strict -2 -f mpegts udp://<<ip_address>>:21000

Using RTP:
sudo ffmpeg -f mcm -conn_type multipoint-group -urn intel-1-rdma -rdma_provider verbs -rdma_num_endpoints 1 -video_size 1920x1080 -frame_rate 30 -payload_type 96 -i 0 -vcodec libx264 -r 30 -b:v 32000k -strict -2 -sdp_file /opt/sdp_file1.sdp -f rtp rtp://<<ip_address>>:21000
```

**Server 1 Generate UDP stream from RDMA flow**

```bash
# Continue with the following command on another terminal on the same server
sudo ffmpeg -stream_loop -1 -s 1920x1080 -r 30 -pix_fmt yuv422p10le -re -i /opt/yuv422p10le_1080p.yuv -f mcm -conn_type multipoint-group -urn intel-1-rdma -rdma_provider verbs -rdma_num_endpoints 1 -video_size 1920x1080 -frame_rate 30 -payload_type 96 -
 
```

**Server 3 View UDP stream**

```bash
# This server is used as a viewer that decodes the RDMA frames passed between the 2 servers
ffplay -protocol_whitelist rtp,udp -i udp://<<ip_address>>:21000
```
