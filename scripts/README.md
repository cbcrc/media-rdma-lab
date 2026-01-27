# Scripts for creating multiple flows

## Multiple MXL flows

### Steps to singletest RDMA in MXL

1. **Start the `mxl-fabrics-demo` on the target host**  
   This will generate a `target-info` token required by the initiator.

2. **Copy the `target-info` to the initiator host**  
   This token is needed to establish the RDMA connection.

3. **Generate an MXL flow on the initiator host**  
   This source will define the flow to be shared.

4. **Start the `mxl-fabrics-demo` on the initiator**  
   Use the appropriate flow file and the `target-info` token to connect to the target.

Follow these steps to validate RDMA functionality and domain separation in your MXL environment.

## Automated Network Saturation Testing

For comprehensive network saturation testing with multiple flows, use the Python automation scripts:

### Prerequisites

Install required Python packages:
```bash
pip install -r requirements.txt
```

### Configuration

Edit `config.json` to specify your target and initiator server details:

- **Management IPs**: Used for SSH connections and file transfers
- **RDMA Interface IPs**: Used for actual RDMA fabric traffic (--node parameter)
- **Server usernames and credentials**
- **Paths to MXL binaries**
- **Test parameters** (number of flows, resolutions, frame rates)

**Example configuration:**
```json
{
  "target_server": {
    "management_ip": "192.168.1.100",
    "rdma_interface_ip": "10.0.0.100",
    "username": "testuser"
  },
  "initiator_server": {
    "management_ip": "192.168.1.101", 
    "rdma_interface_ip": "10.0.0.101",
    "username": "testuser"
  }
}
```

**Important**: The RDMA interface IPs must be on the same network and capable of RDMA traffic (InfiniBand, RoCE, etc.).

### How the Test Works

1. **Environment Setup**: Creates `~/portable` directory and `/dev/shm/mxl` shared memory on both servers
2. **Flow Generation**: Creates multiple JSON flow files using Jinja2 templates with **deterministic UUIDs**
3. **File Distribution**: 
   - JSON flow files → Target server (`~/portable/mxl_flow_files/` directory)
   - JSON flow files + target mapping → Initiator server (`~/portable/mxl_test_data/` directory)
4. **Target Setup**: Starts multiple `mxl-fabrics-demo` target instances
5. **Initiator Setup**: 
   - Starts `mxl-gst-videotestsrc` for each flow
   - Connects `mxl-fabrics-demo` initiators to targets
6. **Monitoring**: Tracks bandwidth and process status
7. **Cleanup**: Removes processes, files, and shared memory

**Key Features:**

- **Human-Readable Filenames**: Flow files use descriptive names like `flow_1_1920x1080_30000_1001.json` while maintaining deterministic UUIDs for MXL compatibility
- **Parallel Execution**: Multiple flows run simultaneously for maximum network saturation
- **Automatic Cleanup**: Complete teardown of processes and temporary files

### Running the Saturation Test

```bash
# Run complete saturation test with default configuration
./network_saturation_test.py --config config.json

# Generate 50 flows for high-intensity testing  
./network_saturation_test.py --config config.json --num-flows 50

# Only generate flow files without starting test
./network_saturation_test.py --generate-only --num-flows 20
```

### Monitoring the Test

In a separate terminal, monitor network utilization:
```bash
# Monitor for 15 minutes on eth0 interface
./network_monitor.py --interface eth0 --duration 15

# Monitor with 1-second intervals for detailed data
./network_monitor.py --interface eth0 --duration 10 --interval 1
```

### Cleaning Up

Stop all processes and clean up test data:
```bash
# Full cleanup (local + remote servers)
./cleanup.py --config config.json

# Only clean up local processes
./cleanup.py --local-only

# Clean up processes but keep test data
./cleanup.py --config config.json --no-data
```

## Manual Single Flow Testing

### Target Server: Provision memory space on target server

Run the following command to start the demo target:

```bash
./mxl-fabrics-demo -d /dev/shm/mxl -f v210_flow.json -n <server_ip> --service 5000 -p verbs
```

### Initiator Server: Start an MXL source

```bash
./mxl-gst-videotestsrc -d /dev/shm/mxl/domain -f v210_flow.json
```

Open a new session (tab) on the Initiator Server and run:

### Initiator Server: Send MXL flow to target

```bash
./mxl-fabrics-demo -d /dev/shm/mxl -f <flow_uuid> -i -n <server_ip> --service 5000 -p verbs --target-info <copied_from_target>
```
