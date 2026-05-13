#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 CBC/Radio-Canada
# SPDX-License-Identifier: Apache-2.0

"""
MXL Test Cleanup Script

Stops all MXL processes and cleans up test data.

Cleanup for tagging the processes

"""

import subprocess
import logging
import argparse
import paramiko
import json
from pathlib import Path
import os
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MXLCleanup:
    """Clean up MXL test processes and data"""
    
    def __init__(self, config_file: str = None):
        self.config = self._load_config(config_file)
        
    def _load_config(self, config_file: str) -> dict:
        """Load configuration"""
        if config_file and Path(config_file).exists():
            with open(config_file, 'r') as f:
                return json.load(f)
        return {}
    
    def cleanup_local_processes(self) -> bool:
        """Stop all local MXL processes"""
        logger.info("Cleaning up local MXL processes")
        
        try:
            # Find MXL processes
            result = subprocess.run(['pgrep', '-f', 'mxl'], 
                                  capture_output=True, text=True)
            
            if result.stdout.strip():
                pids = result.stdout.strip().split('\n')
                for pid in pids:
                    if pid:
                        logger.info(f"Stopping process {pid}")
                        subprocess.run(['kill', '-TERM', pid])
                        
                # Wait a moment, then force kill if needed
                import time
                time.sleep(2)
                
                result = subprocess.run(['pgrep', '-f', 'mxl'], 
                                      capture_output=True, text=True)
                if result.stdout.strip():
                    pids = result.stdout.strip().split('\n')
                    for pid in pids:
                        if pid:
                            logger.info(f"Force stopping process {pid}")
                            subprocess.run(['kill', '-KILL', pid])
                            
            logger.info("Local cleanup completed")
            return True
            
        except Exception as e:
            logger.error(f"Local cleanup failed: {e}")
            return False
    
    def cleanup_remote_processes(self, server_config: dict) -> bool:
        load_dotenv()  # Load environment variables from .env file
        SUDO_PASSWORD = os.getenv("SUDO_PASSWORD")
        """Stop MXL processes on remote server"""
        if not server_config:
            return True
            
        # Use management_ip for SSH connection, fallback to 'ip' for backward compatibility
        server_ip = server_config.get('management_ip') or server_config.get('ip')
        username = server_config.get('username')
        
        if not server_ip or not username:
            logger.warning("Missing server configuration for remote cleanup")
            return False
            
        logger.info(f"Cleaning up MXL processes on {server_ip}")
        
        
        rdma_interface = "rocep152s0f0"
        port = 1
        
        
        
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(server_ip, username=username)
            
            # Stop MXL processes
            commands = [
                "pkill -f mxl-fabrics-demo",
                "pkill -f mxl-gst-testsrc",
                "sleep 2",
                "pkill -9 -f mxl-fabrics-demo",
                "pkill -9 -f mxl-gst-testsrc",
                # Clean up flow files and shared memory
                "rm -rf ~/portable-mxl-v1-1/mxl_flow_files",
                "rm -rf ~/portable-mxl-v1-1/mxl_test_data",
                "sudo rm -rf /dev/shm/mxl",
                # Clean up log files in /tmp
                "rm -f /tmp/target_*.log",
                "rm -f /tmp/target_output_*.log",
                "rm -f /tmp/gst_source_*.log",
                "rm -f /tmp/demo_initiator_*.log",
                f"sudo sh -c 'echo 0 > /sys/kernel/config/rdma_cm/{rdma_interface}/ports/{port}/default_roce_tos'"
            ]
            
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
            
            logger.info(f"Remote cleanup completed for {server_ip}")
            return True
            
        except Exception as e:
            logger.error(f"Remote cleanup failed for {server_ip}: {e}")
            return False
    
    def cleanup_test_data(self) -> bool:
        """Clean up generated test data"""
        logger.info("Cleaning up test data")
        
        try:
            data_dir = Path(__file__).parent / "data" / "generated_flows"
            if data_dir.exists():
                for file in data_dir.glob("*.json"):
                    file.unlink()
                    logger.info(f"Removed {file.name}")
                    
            # Remove mapping file
            mapping_file = Path(__file__).parent / "data" / "flow_target_mapping.json"
            if mapping_file.exists():
                mapping_file.unlink()
                logger.info("Removed flow target mapping")
                
            return True
            
        except Exception as e:
            logger.error(f"Data cleanup failed: {e}")
            return False
    
    def full_cleanup(self) -> bool:
        """Perform complete cleanup"""
        logger.info("Starting full MXL test cleanup")
        
        success = True
        
        # Clean up local processes
        if not self.cleanup_local_processes():
            success = False
            
        # Clean up remote processes
        if self.config:
            target_config = self.config.get('target_server', {})
            initiator_config = self.config.get('initiator_server', {})
            
            if not self.cleanup_remote_processes(target_config):
                success = False
                
            if not self.cleanup_remote_processes(initiator_config):
                success = False
        
        # Clean up test data
        if not self.cleanup_test_data():
            success = False
            
        if success:
            logger.info("Full cleanup completed successfully")
        else:
            logger.warning("Cleanup completed with some errors")
            
        return success

def main():
    parser = argparse.ArgumentParser(description="Clean up MXL test processes and data")
    parser.add_argument("--config", help="Configuration file path")
    parser.add_argument("--local-only", action="store_true", 
                       help="Only clean up local processes")
    parser.add_argument("--no-data", action="store_true",
                       help="Don't clean up test data files")
    
    args = parser.parse_args()
    
    cleanup = MXLCleanup(args.config)
    
    if args.local_only:
        cleanup.cleanup_local_processes()
    else:
        if args.no_data:
            cleanup.cleanup_local_processes()
            if cleanup.config:
                cleanup.cleanup_remote_processes(cleanup.config.get('target_server', {}))
                cleanup.cleanup_remote_processes(cleanup.config.get('initiator_server', {}))
        else:
            cleanup.full_cleanup()

if __name__ == "__main__":
    main()