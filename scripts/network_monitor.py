#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 CBC/Radio-Canada
# SPDX-License-Identifier: Apache-2.0

"""
MXL RDMA Network Monitoring Script

Monitors network utilization and MXL process status during saturation testing.
"""

import time
import subprocess
import json
import logging
from pathlib import Path
from typing import Dict, List
import argparse

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class NetworkMonitor:
    """Monitor network and system resources during MXL testing"""
    
    def __init__(self, interface: str = "eth0", log_interval: int = 5):
        self.interface = interface
        self.log_interval = log_interval
        self.data_dir = Path(__file__).parent / "data"
        self.monitoring_data = []
        
    def get_network_stats(self) -> Dict:
        """Get current network statistics"""
        try:
            # Get network interface statistics
            result = subprocess.run(['cat', f'/proc/net/dev'], 
                                  capture_output=True, text=True)
            
            for line in result.stdout.split('\n'):
                if self.interface in line:
                    fields = line.split()
                    return {
                        'timestamp': time.time(),
                        'rx_bytes': int(fields[1]),
                        'rx_packets': int(fields[2]),
                        'tx_bytes': int(fields[9]),
                        'tx_packets': int(fields[10])
                    }
        except Exception as e:
            logger.error(f"Failed to get network stats: {e}")
            
        return {}
    
    def get_mxl_processes(self) -> List[Dict]:
        """Get information about running MXL processes"""
        try:
            result = subprocess.run(['pgrep', '-f', 'mxl'], 
                                  capture_output=True, text=True)
            
            pids = result.stdout.strip().split('\n') if result.stdout.strip() else []
            
            processes = []
            for pid in pids:
                if pid:
                    try:
                        # Get process info
                        ps_result = subprocess.run(['ps', '-p', pid, '-o', 'pid,command'], 
                                                 capture_output=True, text=True)
                        if ps_result.stdout:
                            lines = ps_result.stdout.strip().split('\n')
                            if len(lines) > 1:  # Skip header
                                process_info = lines[1].strip()
                                processes.append({
                                    'pid': int(pid),
                                    'command': process_info
                                })
                    except:
                        continue
                        
            return processes
            
        except Exception as e:
            logger.error(f"Failed to get MXL processes: {e}")
            return []
    
    def get_system_load(self) -> Dict:
        """Get system load information (cross-platform)"""
        try:
            import platform
            import subprocess
            
            system = platform.system()
            
            if system == "Linux":
                # Linux: use /proc/loadavg
                with open('/proc/loadavg', 'r') as f:
                    load_data = f.read().strip().split()
                    
                return {
                    'load_1min': float(load_data[0]),
                    'load_5min': float(load_data[1]),
                    'load_15min': float(load_data[2])
                }
            elif system == "Darwin":  # macOS
                # macOS: use sysctl
                result = subprocess.run(['sysctl', '-n', 'vm.loadavg'], 
                                      capture_output=True, text=True)
                if result.returncode == 0:
                    # Output format: "{ 1.23 4.56 7.89 }"
                    load_str = result.stdout.strip().strip('{}')
                    load_values = load_str.split()
                    
                    return {
                        'load_1min': float(load_values[0]),
                        'load_5min': float(load_values[1]),
                        'load_15min': float(load_values[2])
                    }
            else:
                # Fallback for other systems
                logger.warning(f"System load monitoring not supported on {system}")
                return {}
                
        except Exception as e:
            logger.error(f"Failed to get system load: {e}")
            return {}
    
    def calculate_bandwidth(self, current_stats: Dict, previous_stats: Dict) -> Dict:
        """Calculate bandwidth utilization"""
        if not current_stats or not previous_stats:
            return {}
            
        time_diff = current_stats['timestamp'] - previous_stats['timestamp']
        if time_diff <= 0:
            return {}
            
        rx_bps = (current_stats['rx_bytes'] - previous_stats['rx_bytes']) / time_diff
        tx_bps = (current_stats['tx_bytes'] - previous_stats['tx_bytes']) / time_diff
        
        return {
            'rx_mbps': rx_bps / (1024 * 1024),
            'tx_mbps': tx_bps / (1024 * 1024),
            'total_mbps': (rx_bps + tx_bps) / (1024 * 1024)
        }
    
    def monitor_test(self, duration_minutes: int = 10) -> None:
        """Monitor the test for specified duration"""
        logger.info(f"Starting monitoring for {duration_minutes} minutes on interface {self.interface}")
        
        start_time = time.time()
        end_time = start_time + (duration_minutes * 60)
        previous_stats = None
        
        while time.time() < end_time:
            current_stats = self.get_network_stats()
            mxl_processes = self.get_mxl_processes()
            system_load = self.get_system_load()
            
            bandwidth = {}
            if previous_stats:
                bandwidth = self.calculate_bandwidth(current_stats, previous_stats)
            
            monitoring_point = {
                'timestamp': time.time(),
                'network_stats': current_stats,
                'bandwidth': bandwidth,
                'mxl_processes': len(mxl_processes),
                'system_load': system_load
            }
            
            self.monitoring_data.append(monitoring_point)
            
            # Log current status
            if bandwidth:
                logger.info(f"Bandwidth: RX={bandwidth.get('rx_mbps', 0):.2f} Mbps, "
                          f"TX={bandwidth.get('tx_mbps', 0):.2f} Mbps, "
                          f"Total={bandwidth.get('total_mbps', 0):.2f} Mbps, "
                          f"MXL Processes: {len(mxl_processes)}")
            else:
                logger.info(f"MXL Processes: {len(mxl_processes)}, Load: {system_load}")
            
            previous_stats = current_stats
            time.sleep(self.log_interval)
    
    def save_monitoring_data(self) -> Path:
        """Save monitoring data to file"""
        timestamp = int(time.time())
        output_file = self.data_dir / f"monitoring_data_{timestamp}.json"
        
        with open(output_file, 'w') as f:
            json.dump(self.monitoring_data, f, indent=2)
            
        logger.info(f"Monitoring data saved to {output_file}")
        return output_file
    
    def generate_summary(self) -> Dict:
        """Generate summary statistics"""
        if not self.monitoring_data:
            return {}
            
        bandwidths = [point['bandwidth'] for point in self.monitoring_data 
                     if point['bandwidth']]
        
        if not bandwidths:
            return {}
            
        total_mbps_values = [bw['total_mbps'] for bw in bandwidths]
        
        return {
            'max_bandwidth_mbps': max(total_mbps_values),
            'avg_bandwidth_mbps': sum(total_mbps_values) / len(total_mbps_values),
            'min_bandwidth_mbps': min(total_mbps_values),
            'total_monitoring_points': len(self.monitoring_data),
            'monitoring_duration_minutes': (self.monitoring_data[-1]['timestamp'] - 
                                          self.monitoring_data[0]['timestamp']) / 60
        }

def main():
    parser = argparse.ArgumentParser(description="Monitor MXL RDMA Network Test")
    parser.add_argument("--interface", default="eth0", help="Network interface to monitor")
    parser.add_argument("--duration", type=int, default=10, help="Monitoring duration in minutes")
    parser.add_argument("--interval", type=int, default=5, help="Logging interval in seconds")
    
    args = parser.parse_args()
    
    monitor = NetworkMonitor(args.interface, args.interval)
    
    try:
        monitor.monitor_test(args.duration)
        
        # Save data and generate summary
        monitor.save_monitoring_data()
        summary = monitor.generate_summary()
        
        if summary:
            logger.info("=== Test Summary ===")
            logger.info(f"Max Bandwidth: {summary['max_bandwidth_mbps']:.2f} Mbps")
            logger.info(f"Avg Bandwidth: {summary['avg_bandwidth_mbps']:.2f} Mbps")
            logger.info(f"Min Bandwidth: {summary['min_bandwidth_mbps']:.2f} Mbps")
            logger.info(f"Duration: {summary['monitoring_duration_minutes']:.1f} minutes")
        
    except KeyboardInterrupt:
        logger.info("Monitoring stopped by user")
        monitor.save_monitoring_data()

if __name__ == "__main__":
    main()