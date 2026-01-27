#!/usr/bin/env python3
"""
MXL RDMA Network Saturation Test Framework

This script orchestrates multiple MXL flows to saturate network bandwidth
between target and initiator servers using RDMA fabric connections.

This version has the ability to tag the flows 
"""

import json
import uuid
import hashlib
import subprocess
import time
import logging
import argparse
import os
from dotenv import load_dotenv
import threading
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional
from jinja2 import Environment, FileSystemLoader
import paramiko
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class FlowConfig:
    """Configuration for a single MXL flow"""
    flow_id: str
    flow_description: str
    flow_label: str
    frame_width: int = 1920
    frame_height: int = 1080
    frame_rate_numerator: int = 30000
    frame_rate_denominator: int = 1001
    
@dataclass
class TargetInfo:
    """Information about a target server instance"""
    flow_id: str
    target_token: str
    server_ip: str
    service_port: int
    process_id: Optional[int] = None

class MXLSaturationTest:
    """Main class for orchestrating MXL network saturation tests"""
    
    def __init__(self, config_file: Optional[str] = None):
        self.flows: List[FlowConfig] = []
        self.target_infos: List[TargetInfo] = []
        self.templates_dir = Path(__file__).parent / "templates"
        self.data_dir = Path(__file__).parent / "data"
        self.flows_dir = self.data_dir / "generated_flows"
        self.flows_dir.mkdir(exist_ok=True)
        
        # Load Jinja2 environment
        self.jinja_env = Environment(loader=FileSystemLoader(self.templates_dir))
        
        # Configuration
        self.config = self._load_config(config_file)
        self._validate_config()
        
    def _validate_config(self) -> None:
        """Validate configuration has required fields with helpful error messages"""
        required_fields = [
            ("target_server", "management_ip"),
            ("target_server", "rdma_interface_ip"), 
            ("target_server", "username"),
            ("initiator_server", "management_ip"),
            ("initiator_server", "rdma_interface_ip"),
            ("initiator_server", "username")
        ]
        
        missing_fields = []
        for section, field in required_fields:
            if section not in self.config or field not in self.config[section]:
                missing_fields.append(f"{section}.{field}")
        
        if missing_fields:
            logger.error("❌ Configuration validation failed!")
            logger.error("Missing required fields:")
            for field in missing_fields:
                logger.error(f"   • {field}")
            logger.error("")
            logger.error("💡 Example configuration:")
            logger.error('   {')
            logger.error('     "target_server": {')
            logger.error('       "management_ip": "192.168.1.100",')
            logger.error('       "rdma_interface_ip": "10.164.138.234",')
            logger.error('       "username": "your_username"')
            logger.error('     },')
            logger.error('     "initiator_server": {')
            logger.error('       "management_ip": "192.168.1.101",')
            logger.error('       "rdma_interface_ip": "10.164.138.235",')
            logger.error('       "username": "your_username"')
            logger.error('     }')
            logger.error('   }')
            raise ValueError(f"Missing required configuration fields: {', '.join(missing_fields)}")
        
        # Validate IP addresses look reasonable
        import re
        ip_pattern = r'^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$'
        
        for server_type in ["target_server", "initiator_server"]:
            for ip_type in ["management_ip", "rdma_interface_ip"]:
                ip = self.config[server_type][ip_type]
                if not re.match(ip_pattern, ip):
                    logger.warning(f"⚠️  {server_type}.{ip_type} might not be a valid IP: {ip}")
        
        logger.info("✅ Configuration validated successfully:")
        logger.info(f"   🎯 Target: {self.config['target_server']['management_ip']} "
                   f"(RDMA: {self.config['target_server']['rdma_interface_ip']})")
        logger.info(f"   🚀 Initiator: {self.config['initiator_server']['management_ip']} "
                   f"(RDMA: {self.config['initiator_server']['rdma_interface_ip']})")
        
    def _load_config(self, config_file: Optional[str]) -> Dict:
        """Load configuration from file or use defaults"""
        default_config = {
            "target_server": {
                "management_ip": "192.168.1.100",
                "rdma_interface_ip": "10.0.0.100",
                "username": "user",
                "mxl_demo_path": "./mxl-fabrics-demo",
                "mxl_gst_path": "./mxl-gst-testsrc",
                "base_service_port": 5000,
                "shared_memory_path": "/dev/shm/mxl"
            },
            "initiator_server": {
                "management_ip": "192.168.1.101",
                "rdma_interface_ip": "10.0.0.101",
                "username": "user",
                "mxl_demo_path": "./mxl-fabrics-demo",
                "mxl_gst_path": "./mxl-gst-testsrc",
                "shared_memory_path": "/dev/shm/mxl"
            },
            "test_parameters": {
                "num_flows": 10,
                "resolutions": [(1920, 1080), (3840, 2160)],
                "frame_rates": [(30000, 1001), (60000, 1001)],
                "use_mongodb": False,
                "mongodb_uri": "mongodb://localhost:27017/mxl_test"
            }
        }
        
        if config_file and os.path.exists(config_file):
            with open(config_file, 'r') as f:
                user_config = json.load(f)
                # Merge with defaults
                default_config.update(user_config)
                
        return default_config
    
    def generate_deterministic_uuid(self, seed_string: str) -> str:
        """Generate a deterministic UUID based on a seed string"""
        # Create a hash of the seed string
        hash_object = hashlib.md5(seed_string.encode())
        hash_hex = hash_object.hexdigest()
        
        # Format as UUID (8-4-4-4-12)
        deterministic_uuid = f"{hash_hex[:8]}-{hash_hex[8:12]}-{hash_hex[12:16]}-{hash_hex[16:20]}-{hash_hex[20:32]}"
        return deterministic_uuid
    
    def generate_flows(self, num_flows: int) -> List[FlowConfig]:
        """Generate multiple flow configurations"""
        logger.info(f"Generating {num_flows} flow configurations")
        
        flows = []
        resolutions = self.config["test_parameters"]["resolutions"]
        frame_rates = self.config["test_parameters"]["frame_rates"]
        
        for i in range(num_flows):
            # Cycle through different configurations
            resolution = resolutions[i % len(resolutions)]
            frame_rate = frame_rates[i % len(frame_rates)]
            
            # Create flow label first
            flow_label = f"flow_{i+1}_{resolution[0]}x{resolution[1]}_{frame_rate[0]}_{frame_rate[1]}"
            
            # Generate deterministic UUID based on flow label
            flow_id = self.generate_deterministic_uuid(flow_label)
            
            flow_config = FlowConfig(
                flow_id=flow_id,
                flow_description=f"Saturation Test Flow {i+1} - {resolution[0]}x{resolution[1]}",
                flow_label=flow_label,
                frame_width=resolution[0],
                frame_height=resolution[1],
                frame_rate_numerator=frame_rate[0],
                frame_rate_denominator=frame_rate[1]
            )
            flows.append(flow_config)
            
        self.flows = flows
        return flows
    
    def render_flow_json(self, flow_config: FlowConfig) -> str:
        """Render a flow configuration to JSON using Jinja2 template"""
        template = self.jinja_env.get_template("v210_flow.j2")
        
        # Convert dataclass to dict for template rendering
        template_vars = asdict(flow_config)
        
        rendered_json = template.render(**template_vars)
        return rendered_json
    
    def save_flow_files(self) -> List[Path]:
        """Save all flow configurations to JSON files"""
        logger.info(f"Saving {len(self.flows)} flow files to {self.flows_dir}")
        
        flow_files = []
        for flow in self.flows:
            flow_json = self.render_flow_json(flow)
            # Use flow label as filename instead of flow ID
            flow_file = self.flows_dir / f"{flow.flow_label}.json"
            
            with open(flow_file, 'w') as f:
                f.write(flow_json)
            flow_files.append(flow_file)
            
        return flow_files
    
    def start_target_server_instance(self, flow_config: FlowConfig, service_port: int) -> Optional[TargetInfo]:
        """Start a single mxl-fabrics-demo instance on target server"""
        management_ip = self.config["target_server"]["management_ip"]
        rdma_interface_ip = self.config["target_server"]["rdma_interface_ip"]
        username = self.config["target_server"]["username"]
        mxl_demo_path = self.config["target_server"]["mxl_demo_path"]
        shared_memory = self.config["target_server"]["shared_memory_path"]
        
        flow_file = f"./mxl_flow_files/{flow_config.flow_label}.json"
        
        # SSH command to start target and capture initial output, then background
        # We need to capture target-info from initial output before backgrounding
        # Use signal handling to make the process more resilient to interruptions
        command = (
            f"cd ~/portable-mxl-v1-1 && "
            f"nohup bash -c 'trap \"\" INT TERM; {mxl_demo_path} -d {shared_memory} -f {flow_file} "
            f"--node {rdma_interface_ip} --service {service_port} -p verbs' > /tmp/target_{service_port}.log 2>&1 & "
            f"for i in {{1..15}}; do "
            f"grep 'Target info:' /tmp/target_{service_port}.log && break; "
            f"sleep 1; "
            f"done; "
            f"cat /tmp/target_{service_port}.log"
            
        )
        
        logger.info(f"Starting target for flow {flow_config.flow_id} on RDMA interface {rdma_interface_ip}:{service_port}")
        logger.debug(f"Target Command: {command}")
        
        try:
            # Execute command via SSH using management IP
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(management_ip, username=username)
            
            # Execute the command with timeout
            stdin, stdout, stderr = ssh.exec_command(command, timeout=15)
            
            # Read the initial output which should contain target-info
            output = stdout.read().decode()
            error = stderr.read().decode()

            logger.debug(f"Target start output: {output}")
            logger.debug(f"Target start errors: {error}")
            
            # Check if target was backgrounded successfully
            if "Target backgrounded" not in output and "Target exited early" in output:
                logger.error(f"Target exited early for flow {flow_config.flow_id}")
                ssh.close()
                return None
            
            if error and "warning" not in error.lower() and "libfabric" not in error.lower():
                logger.error(f"Error starting target for flow {flow_config.flow_id}: {error}")
                ssh.close()
                return None
                
            # Extract target-info token from output - this is critical for the test to work
            try:
                target_token = self._extract_target_info(output)
            except RuntimeError as e:
                logger.error(f"Critical error for flow {flow_config.flow_id}: {e}")
                ssh.close()
                return None
            
            target_info = TargetInfo(
                flow_id=flow_config.flow_id,
                target_token=target_token,
                server_ip=rdma_interface_ip,  # Use RDMA interface IP for connections
                service_port=service_port
            )
            
            ssh.close()
            return target_info
            
        except Exception as e:
            logger.error(f"Failed to start target for flow {flow_config.flow_id}: {e}")
            return None
    
    def _extract_target_info(self, output: str) -> str:
        """Extract target-info token from mxl-fabrics-demo output"""
        # The mxl-fabrics-demo target outputs the TargetInfo as a base64-encoded string
        # after a line containing "Target info:"
        lines = output.split('\n')
        
        for line in lines:
            line = line.strip()
            # Look for the line containing "Target info:"
            if 'Target info:' in line:
                # Extract everything after "Target info:"
                parts = line.split('Target info:')
                if len(parts) > 1:
                    target_token = parts[1].strip()
                    if target_token:
                        logger.info(f"Found target-info: {target_token[:50]}...")
                        return target_token
        
        # Fallback: look for long base64-like strings
        for line in lines:
            line = line.strip()
            # Look for base64-like strings (common pattern for target-info)
            if len(line) > 100 and line.replace('+', '').replace('/', '').replace('=', '').isalnum():
                logger.info(f"Found potential target-info: {line[:50]}...")
                return line 
        
        # Last resort: generate a placeholder (this should be replaced with proper parsing)
        logger.error("Could not extract target-info from output. This is critical for initiator connections.")
        logger.debug(f"Full output was: {output}")
        raise RuntimeError("Failed to extract target-info from mxl-fabrics-demo output. Cannot proceed with test.")
    
    def setup_server_environment(self, server_config: dict, server_type: str) -> bool:
        """Setup server environment (portable-mxl-v1-1 directory and shared memory)"""
        management_ip = server_config["management_ip"]
        username = server_config["username"]
        
        logger.info(f"Setting up {server_type} server environment on {management_ip}")
        
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(management_ip, username=username)
            
            # Setup commands
            setup_commands = [
                "mkdir -p ~/portable-mxl-v1-1",
                "mkdir -p /dev/shm/mxl"
            ]

            for cmd in setup_commands:
                stdin, stdout, stderr = ssh.exec_command(cmd)
                stdout.read()  # Wait for completion
                error = stderr.read().decode().strip()
                if error and "File exists" not in error:
                    logger.warning(f"Setup command '{cmd}' warning: {error}")
            
            ssh.close()
            logger.info(f"{server_type} server environment setup completed")
            return True
            
        except Exception as e:
            logger.error(f"Failed to setup {server_type} server environment: {e}")
            return False
    
    def start_all_targets(self) -> List[TargetInfo]:
        """Start all target server instances in parallel"""
        logger.info(f"Starting {len(self.flows)} target server instances")
        
        base_port = self.config["target_server"]["base_service_port"]
        target_infos = []
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_flow = {
                executor.submit(
                    self.start_target_server_instance, 
                    flow, 
                    base_port + i
                ): flow for i, flow in enumerate(self.flows)
            }
            
            for future in as_completed(future_to_flow):
                target_info = future.result()
                if target_info:
                    target_infos.append(target_info)
                    
        self.target_infos = target_infos
        logger.info(f"Successfully started {len(target_infos)} target instances")
        
        if len(target_infos) == 0:
            logger.error("No target instances started successfully. Cannot proceed with test.")
            raise RuntimeError("Failed to start any target instances with valid target-info")
            
        if len(target_infos) < len(self.flows):
            logger.warning(f"Only {len(target_infos)} of {len(self.flows)} target instances started successfully")
            
        return target_infos
    
    def save_target_info_mapping(self) -> Path:
        """Save flow_id to target_info mapping"""
        mapping_file = self.data_dir / "flow_target_mapping.json"
        
        mapping = {
            target_info.flow_id: asdict(target_info) 
            for target_info in self.target_infos
        }
        
        with open(mapping_file, 'w') as f:
            json.dump(mapping, f, indent=2)
            
        logger.info(f"Saved target info mapping to {mapping_file}")
        return mapping_file
    
    def transfer_files_to_target(self, flow_files: List[Path]) -> bool:
        """Transfer flow files to target server"""
        management_ip = self.config["target_server"]["management_ip"]
        username = self.config["target_server"]["username"]
        
        logger.info(f"Transferring {len(flow_files)} flow files to target server {management_ip}")
        
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(management_ip, username=username)
            
            sftp = ssh.open_sftp()
            
            # Change to portable directory
            sftp.chdir('portable-mxl-v1-1')
            
            # Create remote directory for flow files
            try:
                sftp.mkdir('mxl_flow_files')
            except:
                pass  # Directory might already exist
                
            # Transfer flow files
            for flow_file in flow_files:
                remote_path = f"mxl_flow_files/{flow_file.name}"
                sftp.put(str(flow_file), remote_path)
                logger.info(f"Transferred {flow_file.name} to target")
                
            sftp.close()
            ssh.close()
            
            logger.info("Flow file transfer to target completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Flow file transfer to target failed: {e}")
            return False
    
    def transfer_files_to_initiator(self, files: List[Path]) -> bool:
        """Transfer flow files and mapping to initiator server"""
        management_ip = self.config["initiator_server"]["management_ip"]
        username = self.config["initiator_server"]["username"]
        
        logger.info(f"Transferring {len(files)} files to initiator server {management_ip}")
        
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(management_ip, username=username)
            
            sftp = ssh.open_sftp()
            
            # Change to portable directory
            sftp.chdir('portable-mxl-v1-1')
            
            # Create remote directory
            try:
                sftp.mkdir('mxl_test_data')
            except:
                pass  # Directory might already exist
                
            # Transfer files
            for file_path in files:
                remote_path = f"mxl_test_data/{file_path.name}"
                sftp.put(str(file_path), remote_path)
                logger.info(f"Transferred {file_path.name}")
                
            sftp.close()
            ssh.close()
            
            logger.info("File transfer completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"File transfer failed: {e}")
            return False
    
    def start_initiator_sources(self) -> bool:
        """Start mxl-gst-testsrc instances on initiator"""
        management_ip = self.config["initiator_server"]["management_ip"]
        username = self.config["initiator_server"]["username"]
        mxl_gst_path = self.config["initiator_server"]["mxl_gst_path"]
        shared_memory = self.config["initiator_server"]["shared_memory_path"]
        
        logger.info("Starting MXL video test sources on initiator")
        
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(management_ip, username=username)
            
            for flow in self.flows:
                # Simple command to start GST source in background with flow overlay text
                command = (
                    f"cd ~/portable-mxl-v1-1 && nohup bash -c 'trap \"\" INT TERM; {mxl_gst_path} -d {shared_memory} "
                    f"-v mxl_test_data/{flow.flow_label}.json -t \"{flow.flow_label}\"' > /tmp/gst_source_{flow.flow_label}.log 2>&1 &"
                )
                
                stdin, stdout, stderr = ssh.exec_command(command)
                logger.info(f"Started GST source for flow {flow.flow_label}")
                logger.debug(f"GST command: {command}")
                
            ssh.close()
            return True
            
        except Exception as e:
            logger.error(f"Failed to start initiator sources: {e}")
            return False
    
    def start_initiator_connections(self) -> bool:
        """Start mxl-fabrics-demo instances on initiator to connect to targets"""
        management_ip = self.config["initiator_server"]["management_ip"]
        rdma_interface_ip = self.config["initiator_server"]["rdma_interface_ip"]
        username = self.config["initiator_server"]["username"]
        mxl_demo_path = self.config["initiator_server"]["mxl_demo_path"]
        shared_memory = self.config["initiator_server"]["shared_memory_path"]
        target_rdma_ip = self.config["target_server"]["rdma_interface_ip"]
        
        logger.info("Starting MXL fabric demo connections on initiator")
        
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(management_ip, username=username)
            
            for target_info in self.target_infos:
                # Use RDMA interface IPs for both --node and target connection
                command = (
                    f"cd ~/portable-mxl-v1-1 && nohup bash -c 'trap \"\" INT TERM; {mxl_demo_path} -d {shared_memory} -f {target_info.flow_id} "
                    f"-i --node {rdma_interface_ip} --service {target_info.service_port} "
                    f"-p verbs --target-info {target_info.target_token}' "
                    f"> /tmp/demo_initiator_{target_info.flow_id}.log 2>&1 &"
                )
                
                stdin, stdout, stderr = ssh.exec_command(command)
                logger.info(f"Started connection for flow {target_info.flow_id} "
                          f"from {rdma_interface_ip} to {target_rdma_ip}:{target_info.service_port}")
                logger.debug(f"Initiator command: {command}")
                
            ssh.close()
            return True
            
        except Exception as e:
            logger.error(f"Failed to start initiator connections: {e}")
            return False
    
    def configure_uc3_qos(self) -> bool:
        load_dotenv()  # Load environment variables from .env file
        SUDO_PASSWORD = os.getenv("SUDO_PASSWORD")
        
        #utalizing  DSCP marking 
        rdma_interface = "rocep152s0f0"
        interface = "enp152s0f0np0"
        port = 1

        logger.info(f"Configuring QoS on {interface}: ALL traffic → UC3 (DSCP 24 / TOS 96)")

        commands = [
            
            # ToS 96
            f"sudo mkdir -p /sys/kernel/config/rdma_cm/{rdma_interface}/ports/{port}",
            f"sudo sh -c 'echo 96 > /sys/kernel/config/rdma_cm/{rdma_interface}/ports/{port}/default_roce_tos'",
            
            #Optional
            f"cat /sys/kernel/config/rdma_cm/{rdma_interface}/ports/{port}/default_roce_tos"
            
            
        ]
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(self.config["initiator_server"]["management_ip"],username=self.config["initiator_server"]["username"])
            
            for cmd in commands:
                if cmd.strip().startswith("sudo "):
                    full_cmd = cmd.replace("sudo ", "sudo -S ", 1)  # Add -S once
                else:
                    full_cmd = cmd

                logger.debug(f"Executing: {full_cmd}")
                stdin, stdout, stderr = ssh.exec_command(full_cmd)

                if cmd.strip().startswith("sudo "):
                    stdin.write(SUDO_PASSWORD + "\n")
                    stdin.flush()  # Important!

                exit_status = stdout.channel.recv_exit_status()
                out = stdout.read().decode().strip()
                err = stderr.read().decode().strip()

                if exit_status != 0:
                    logger.error(f"Failed (exit {exit_status}): {full_cmd}")
                    logger.error(f"stderr: {err}")
                else:
                    if out:
                        logger.info(f"Output: {out}")
                        
            ssh.close()

            logger.info("QoS configured: DSCP 24 → UC3 active")
            return True

        except Exception as e:
            logger.error(f"Failed to configure QoS: {e}")
            return False

    
    def run_saturation_test(self, num_flows: int = None) -> bool:
        """Run the complete network saturation test"""
        if num_flows is None:
            num_flows = self.config["test_parameters"]["num_flows"]
            
        logger.info(f"Starting MXL RDMA network saturation test with {num_flows} flows")
        
        try:
            # Step 1: Generate flow configurations
            self.generate_flows(num_flows)
            
            # Step 2: Save flow files
            flow_files = self.save_flow_files()
            
            # Step 3: Setup server environments
            if not self.setup_server_environment(self.config["target_server"], "target"):
                return False
            if not self.setup_server_environment(self.config["initiator_server"], "initiator"):
                return False
            
            # Step 4: Transfer flow files to target server
            if not self.transfer_files_to_target(flow_files):
                return False
            
            # Step 5: Start target server instances
            try:
                self.start_all_targets()
            except RuntimeError as e:
                logger.error(f"Target server startup failed: {e}")
                return False
            
            # Step 6: Save target info mapping
            mapping_file = self.save_target_info_mapping()
            
            # Step 7: Transfer files to initiator
            all_files = flow_files + [mapping_file]
            if not self.transfer_files_to_initiator(all_files):
                return False
            #take into account Qos
            if not self.configure_uc3_qos():
                logger.error("Failed to configure QoS on initiator")
                return False
            
            # Step 8: Start video test sources on initiator
            if not self.start_initiator_sources():
                return False
            
            # Small delay to let sources start up
            time.sleep(2)
            
            # Step 9: Start fabric demo connections on initiator
            if not self.start_initiator_connections():
                return False
            
            logger.info("Network saturation test started successfully!")
            logger.info("Monitor network utilization to verify saturation")
            
            return True
            
        except Exception as e:
            logger.error(f"Saturation test failed: {e}")
            return False
    
    def check_process_status(self) -> bool:
        """Check if target and initiator processes are still running with detailed status"""
        logger.info("=" * 60)
        logger.info("MXL RDMA TEST STATUS REPORT")
        logger.info("=" * 60)
        
        overall_status = True
        
        try:
            # Check target server processes
            target_config = self.config["target_server"]
            management_ip = target_config["management_ip"]
            rdma_ip = target_config["rdma_interface_ip"]
            username = target_config["username"]
            
            logger.info(f"🎯 TARGET SERVER ({management_ip} | RDMA: {rdma_ip})")
            logger.info("-" * 40)
            
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(management_ip, username=username)
            
            # Check for target processes
            stdin, stdout, stderr = ssh.exec_command("pgrep -f 'mxl-fabrics-demo' | wc -l")
            target_count = int(stdout.read().decode().strip())
            
            # Get detailed process info
            stdin, stdout, stderr = ssh.exec_command("pgrep -fl 'mxl-fabrics-demo'")
            target_processes = stdout.read().decode().strip()
            
            # Check log files
            stdin, stdout, stderr = ssh.exec_command("ls -la /tmp/target_*.log 2>/dev/null | wc -l")
            log_count = int(stdout.read().decode().strip())
            
            # Check for recent errors
            stdin, stdout, stderr = ssh.exec_command("tail -50 /tmp/target_*.log 2>/dev/null | grep -i error | tail -5")
            recent_errors = stdout.read().decode().strip()
            
            # Check ports in use
            base_port = target_config.get("base_service_port", 5000)
            port_range = f"{base_port}-{base_port + 20}"
            stdin, stdout, stderr = ssh.exec_command(f"netstat -ln | grep ':{base_port}\\|:{base_port + 1}\\|:{base_port + 2}' | wc -l")
            ports_in_use = int(stdout.read().decode().strip())
            
            logger.info(f"  ✓ Target processes running: {target_count}")
            logger.info(f"  ✓ Log files created: {log_count}")
            logger.info(f"  ✓ Ports in use (around {base_port}): {ports_in_use}")
            
            if target_processes:
                logger.info(f"  📋 Running processes:")
                for line in target_processes.split('\n')[:3]:  # Show first 3
                    if line.strip():
                        logger.info(f"     • {line.strip()}")
            
            if recent_errors and recent_errors != "No recent errors":
                logger.warning(f"  ⚠️  Recent errors found:")
                for error in recent_errors.split('\n')[-3:]:  # Show last 3 errors
                    if error.strip():
                        logger.warning(f"     • {error.strip()}")
                overall_status = False
            else:
                logger.info(f"  ✅ No recent errors in target logs")
            
            ssh.close()
            
            # Check initiator server processes  
            logger.info("")
            initiator_config = self.config["initiator_server"]
            management_ip = initiator_config["management_ip"]
            rdma_ip = initiator_config["rdma_interface_ip"]
            username = initiator_config["username"]
            
            logger.info(f"🚀 INITIATOR SERVER ({management_ip} | RDMA: {rdma_ip})")
            logger.info("-" * 40)
            
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(management_ip, username=username)
            
            # Check for different types of processes
            stdin, stdout, stderr = ssh.exec_command("pgrep -f 'mxl-gst-testsrc' | wc -l")
            gst_count = int(stdout.read().decode().strip())
            
            stdin, stdout, stderr = ssh.exec_command("pgrep -f 'mxl-fabrics-demo.*-i' | wc -l")
            demo_count = int(stdout.read().decode().strip())
            
            total_initiator = gst_count + demo_count
            
            # Check log files
            stdin, stdout, stderr = ssh.exec_command("ls -la /tmp/gst_*.log /tmp/demo_initiator_*.log 2>/dev/null | wc -l")
            initiator_logs = int(stdout.read().decode().strip())
            
            # Check for recent errors
            stdin, stdout, stderr = ssh.exec_command("tail -50 /tmp/gst_*.log /tmp/demo_initiator_*.log 2>/dev/null | grep -i error | tail -5")
            initiator_errors = stdout.read().decode().strip()
            
            logger.info(f"  ✓ GST video sources: {gst_count}")
            logger.info(f"  ✓ Demo initiators: {demo_count}")
            logger.info(f"  ✓ Total initiator processes: {total_initiator}")
            logger.info(f"  ✓ Log files created: {initiator_logs}")
            
            if initiator_errors and initiator_errors != "No recent errors":
                logger.warning(f"  ⚠️  Recent errors found:")
                for error in initiator_errors.split('\n')[-3:]:
                    if error.strip():
                        logger.warning(f"     • {error.strip()}")
                overall_status = False
            else:
                logger.info(f"  ✅ No recent errors in initiator logs")
            
            ssh.close()
            
            # Summary
            logger.info("")
            logger.info("📊 SUMMARY")
            logger.info("-" * 20)
            expected_flows = len(self.flows) if self.flows else self.config["test_parameters"]["num_flows"]
            
            if target_count >= expected_flows and total_initiator >= expected_flows:
                logger.info("  🟢 ALL SYSTEMS OPERATIONAL")
                logger.info(f"     Expected flows: {expected_flows}")
                logger.info(f"     Target processes: {target_count}")
                logger.info(f"     Initiator processes: {total_initiator}")
            elif target_count > 0 and total_initiator > 0:
                logger.warning("  🟡 PARTIAL OPERATION")
                logger.warning(f"     Expected flows: {expected_flows}")
                logger.warning(f"     Target processes: {target_count}")
                logger.warning(f"     Initiator processes: {total_initiator}")
                overall_status = False
            else:
                logger.error("  🔴 SYSTEM DOWN")
                logger.error(f"     Target processes: {target_count}")
                logger.error(f"     Initiator processes: {total_initiator}")
                overall_status = False
            
            logger.info("=" * 60)
            
            if not overall_status:
                logger.info("💡 DEBUGGING TIPS:")
                logger.info("   • Check logs: ssh <server> 'tail -f /tmp/target_*.log'")
                logger.info("   • Check processes: ssh <server> 'ps aux | grep mxl'")
                logger.info("   • Clean restart: python cleanup.py && python network_saturation_test.py")
                logger.info("   • Use --debug flag for verbose output")
            
            return target_count > 0 and total_initiator > 0
            
        except Exception as e:
            logger.error(f"❌ Failed to check process status: {e}")
            logger.info("💡 TIP: Verify SSH connectivity and server accessibility")
            return False
    
    def collect_logs(self, lines: int = 50) -> None:
        """Collect and display logs from both servers for debugging"""
        logger.info("=" * 60)
        logger.info("COLLECTING LOGS FROM ALL SERVERS")
        logger.info("=" * 60)
        
        try:
            # Collect target server logs
            target_config = self.config["target_server"]
            management_ip = target_config["management_ip"]
            username = target_config["username"]
            
            logger.info(f"🎯 TARGET SERVER LOGS ({management_ip})")
            logger.info("-" * 40)
            
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(management_ip, username=username)
            
            # Get list of log files
            stdin, stdout, stderr = ssh.exec_command("ls -la /tmp/target_*.log 2>/dev/null")
            log_files = stdout.read().decode().strip()
            
            if log_files:
                logger.info("📋 Available log files:")
                for line in log_files.split('\n'):
                    if 'target_' in line:
                        logger.info(f"   • {line.split()[-1]} ({line.split()[4]} bytes)")
                
                logger.info(f"\n📖 Last {lines} lines from target logs:")
                stdin, stdout, stderr = ssh.exec_command(f"tail -{lines} /tmp/target_*.log 2>/dev/null")
                logs = stdout.read().decode()
                if logs:
                    for line in logs.split('\n')[-20:]:  # Show last 20 lines
                        if line.strip():
                            logger.info(f"   {line}")
                else:
                    logger.warning("   No log content found")
            else:
                logger.warning("   No target log files found")
            
            ssh.close()
            
            # Collect initiator server logs
            logger.info(f"\n🚀 INITIATOR SERVER LOGS")
            logger.info("-" * 40)
            
            initiator_config = self.config["initiator_server"]
            management_ip = initiator_config["management_ip"]
            username = initiator_config["username"]
            
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(management_ip, username=username)
            
            # Get list of log files
            stdin, stdout, stderr = ssh.exec_command("ls -la /tmp/gst_*.log /tmp/demo_initiator_*.log 2>/dev/null")
            log_files = stdout.read().decode().strip()
            
            if log_files:
                logger.info("📋 Available log files:")
                for line in log_files.split('\n'):
                    if any(x in line for x in ['gst_', 'demo_initiator_']):
                        logger.info(f"   • {line.split()[-1]} ({line.split()[4]} bytes)")
                
                logger.info(f"\n📖 Last {lines} lines from initiator logs:")
                stdin, stdout, stderr = ssh.exec_command(f"tail -{lines} /tmp/gst_*.log /tmp/demo_initiator_*.log 2>/dev/null")
                logs = stdout.read().decode()
                if logs:
                    for line in logs.split('\n')[-20:]:  # Show last 20 lines
                        if line.strip():
                            logger.info(f"   {line}")
                else:
                    logger.warning("   No log content found")
            else:
                logger.warning("   No initiator log files found")
            
            ssh.close()
            logger.info("=" * 60)
            
        except Exception as e:
            logger.error(f"❌ Failed to collect logs: {e}")
            logger.info("💡 TIP: Check SSH connectivity and file permissions")
            
    

def main():
    parser = argparse.ArgumentParser(description="MXL RDMA Network Saturation Test")
    parser.add_argument("--config", help="Configuration file path")
    parser.add_argument("--num-flows", type=int, default=10, help="Number of flows to generate")
    parser.add_argument("--generate-only", action="store_true", help="Only generate flow files")
    parser.add_argument("--check-status", action="store_true", help="Check if processes are running")
    parser.add_argument("--collect-logs", action="store_true", help="Collect logs from all servers")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without executing")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--help-troubleshoot", action="store_true", help="Show troubleshooting guide")
    
    args = parser.parse_args()
    
    # Show troubleshooting guide
    if args.help_troubleshoot:
        show_troubleshooting_guide()
        return
    
    # Set logging level based on debug flag
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.INFO)
    
    try:
        test = MXLSaturationTest(args.config)
    except Exception as e:
        logger.error(f"❌ Failed to initialize test framework: {e}")
        logger.info("💡 Try: python network_saturation_test.py --help-troubleshoot")
        return
    
    if args.generate_only:
        logger.info("🔧 GENERATE-ONLY MODE")
        test.generate_flows(args.num_flows)
        test.save_flow_files()
        logger.info("✅ Flow files generated successfully")
        
    elif args.check_status:
        test.check_process_status()
        
    elif args.collect_logs:
        test.collect_logs()
        
    elif args.dry_run:
        logger.info("🔍 DRY-RUN MODE - Showing what would be executed")
        logger.info("=" * 50)
        dry_run_preview(test, args.num_flows)
        
    else:
        logger.info("🚀 Starting MXL RDMA Network Saturation Test")
        success = test.run_saturation_test(args.num_flows)
        if success:
            logger.info("✅ Saturation test completed successfully!")
            logger.info("💡 Use --check-status to monitor progress")
            logger.info("💡 Use --collect-logs to debug issues")
        else:
            logger.error("❌ Saturation test failed")
            logger.info("💡 Try: python network_saturation_test.py --collect-logs")
            logger.info("💡 Try: python network_saturation_test.py --help-troubleshoot")

def dry_run_preview(test, num_flows):
    """Show what would be executed without running"""
    test.generate_flows(num_flows)
    
    logger.info("📋 Configuration Summary:")
    logger.info(f"   • Target Server: {test.config['target_server']['management_ip']}")
    logger.info(f"   • Initiator Server: {test.config['initiator_server']['management_ip']}")
    logger.info(f"   • Number of flows: {len(test.flows)}")
    logger.info(f"   • Base port: {test.config['target_server']['base_service_port']}")
    
    logger.info("\n🎯 Target Commands (would be executed):")
    for i, flow in enumerate(test.flows[:3]):  # Show first 3
        port = test.config['target_server']['base_service_port'] + i
        logger.info(f"   Flow {i+1}: mxl-fabrics-demo --service {port} --node {test.config['target_server']['rdma_interface_ip']}")
    
    logger.info("\n🚀 Initiator Commands (would be executed):")
    logger.info(f"   GST Sources: {len(test.flows)} x mxl-gst-testsrc")
    logger.info(f"   Demo Connections: {len(test.flows)} x mxl-fabrics-demo -i")
    
    logger.info("\n📁 Files that would be created:")
    logger.info(f"   • {len(test.flows)} flow JSON files")
    logger.info(f"   • Target info mapping file")
    logger.info(f"   • Log files in /tmp/ on both servers")
    


def show_troubleshooting_guide():
    """Display comprehensive troubleshooting guide"""
    print("=" * 60)
    print("MXL RDMA TEST TROUBLESHOOTING GUIDE")
    print("=" * 60)
    
    print("\n🔧 COMMON ISSUES AND SOLUTIONS:")
    
    print("\n1️⃣  Configuration Issues:")
    print("   Problem: Missing configuration fields")
    print("   Solution: Create config.json with required fields")
    print("   Command: python network_saturation_test.py --dry-run")
    
    print("\n2️⃣  SSH Connection Issues:")
    print("   Problem: Cannot connect to servers")
    print("   Solution: Verify SSH keys and network connectivity")
    print("   Test: ssh user@server_ip 'echo success'")
    
    print("\n3️⃣  Process Not Starting:")
    print("   Problem: Target/initiator processes fail to start")
    print("   Solution: Check MXL binary paths and permissions")
    print("   Debug: python network_saturation_test.py --collect-logs")
    
    print("\n4️⃣  RDMA Interface Issues:")
    print("   Problem: 'Interrupted system call' errors")
    print("   Solution: Verify RDMA interface IPs are correct")
    print("   Check: ip addr show | grep 10.164")
    
    print("\n5️⃣  Target Info Extraction Fails:")
    print("   Problem: Cannot extract target-info token")
    print("   Solution: Check target process startup logs")
    print("   Debug: ssh target_server 'tail -f /tmp/target_*.log'")
    
    print("\n6️⃣  Flow File Issues:")
    print("   Problem: Flow JSON files not found")
    print("   Solution: Run with --generate-only first")
    print("   Command: python network_saturation_test.py --generate-only")
    
    print("\n🛠️  DEBUGGING COMMANDS:")
    print("   • Check status: python network_saturation_test.py --check-status")
    print("   • Collect logs: python network_saturation_test.py --collect-logs")
    print("   • Preview run: python network_saturation_test.py --dry-run")
    print("   • Clean start: python cleanup.py && python network_saturation_test.py")
    print("   • Verbose mode: python network_saturation_test.py --debug")
    
    print("\n📞 MANUAL VERIFICATION:")
    print("   • SSH access: ssh user@server 'hostname'")
    print("   • MXL binaries: ssh server 'ls -la ~/portable-mxl-v1-1/mxl-*'")
    print("   • RDMA interfaces: ssh server 'ip addr | grep rdma_ip'")
    print("   • Process status: ssh server 'pgrep -fl mxl'")
    print("   • Log files: ssh server 'ls -la /tmp/{target,gst,demo}_*.log'")
    
    print("=" * 60)

if __name__ == "__main__":
    main()
