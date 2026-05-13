<!--
SPDX-FileCopyrightText: 2026 CBC/Radio-Canada
SPDX-License-Identifier: CC-BY-4.0
-->

# BGP at a Server Level; Configuration and Validation Guide (FRR)

This guide provides instructions for configuring and validating **BGP (Border Gateway Protocol)** on lab servers using **FRR (Free Range Routing)**.  
The goal is to enable dynamic route exchange between each server and its RDMA peer switch, ensuring loopback reachability and routing consistency across the RDMA lab environment.

## 1. Introduction and Purpose

BGP is used in the RDMA lab to establish Layer 3 peering between each server and its corresponding RDMA peer switch.  
This configuration enables automatic route advertisement and discovery between hosts, ensuring connectivity across loopback interfaces for RDMA and testing purposes.

The steps below outline how to configure BGP on a **new server**, validate its session, and troubleshoot common setup issues.

## 2. Before You Begin

### Requirements

- Ubuntu 22.04 or 24.04 server with administrative access  
- Network interface connected to the peer switch  
- Installed and running **FRR** package  
- Verified IP connectivity to the peer switch

### Verify FRR Installation

```bash
frr version
```

Expected output should confirm the installed version, for example:

```scss
FRRouting 8.4.2 (Ubuntu 24.04)
```

### Check Network Interface

Confirm the interface connected to the switch is active:

```bash
ip link show
```

If the interface shows as `DOWN`, bring it up:

```bash
sudo ip link set <interface> up
```

## 3. Switch Interface Setup

On the peer switch, ensure that the connected interface is properly configured for 25G operation and enabled.

```bash
interface <interface_name>
   description <server_name>
   speed-group 17 # the number depends on the interface on the switch
   no shutdown
```

If the server interface remains down, verify the physical link and ensure the speed-group setting matches the server NIC configuration.

## 4. Enabling FRR and BGP Daemon

Enable the BGP daemon in FRR by editing `/etc/frr/daemons`.

```bash
sudo nano /etc/frr/daemons
```

Ensure the following line is set to yes:

```ini
bgpd=yes
```

Then, restart the FRR service:

```bash
sudo systemctl restart frr
sudo systemctl status frr
```

If FRR fails to start, check for syntax errors or missing configuration files in `/etc/frr/`.

---

## 5. Configuring FRR (BGP Setup)

Edit or create the BGP configuration file:

```bash
sudo nano /etc/frr/frr.conf
```

Below is a template for a standard server-side BGP configuration using IPv4.
All values (ASNs, IPs, and interface names) should be adapted for the target server and switch.

```bash
!
log syslog informational
hostname <server_name>
service integrated-vtysh-config
router bgp <local_server_asn>
  bgp router-id <local_server_loopback_ip>
  bgp graceful-restart restart-time 300
  bgp graceful-restart
  maximum-paths 4 ecmp 4
  no bgp ebgp-requires-policy
  neighbor <switch_port_ip> remote-as <switch_asn>
  neighbor <switch_port_ip> send-community
  address-family ipv4 unicast
    ! If you want to advertise the loopbacks (or any other connected route)
    ! make sure the IP is on a loopback interface
    redistribute connected route-map ADVERTISE_LOOPBACKS
  exit-address-family

ip prefix-list SERVER_LOOPBACK_PREFIX_LIST seq 10 permit <prefix_list_subnet> le 32

route-map ADVERTISE_LOOPBACKS permit 10
  match ip address prefix-list SERVER_LOOPBACK_PREFIX_LIST
!
line vty
!
```

### Configuration Explanation

- Prefix List:
  - The prefix list `LOOPBACK-NET` defines which network(s) will be advertised over BGP. In this case, it advertises only the server’s loopback interface (`10.10.10.1/32`).
- Route Map:
  - The route map `LOOPBACK` references the prefix list and allows fine-grained control over what routes are advertised or filtered.
- Router BGP:
  - `bgp router-id` sets the unique identifier for this BGP instance.
  - `neighbor` defines the switch BGP peer and remote AS number.
  - The `network` statement advertises the loopback network via the route map.

## 6. Starting and Verifying BGP

After saving your configuration, restart FRR to apply changes:

```bash
sudo systemctl restart frr
```

Access the FRR shell to confirm BGP operation:

```bash
sudo vtysh
```

From within the FRR shell:

```bash
show running-config
show ip bgp summary
show ip bgp neighbors
show ip route
```

Exit the shell:

```bash
exit
```

If the session state is Active, verify that the peer switch configuration is correct and that the interface link is up.
The session should display Established once peering is active.

## 7. Validation Commands 

The following commands confirm BGP operation:

| Command | Purpose | Expected Output |
| ------- | ------- | --------------- |
| `systemctl status frr` | Check FRR service status | `Active` (running) |
| `ip link show <interface>`| Verify link state | Interface `UP` |
| `sudo vtysh -c "show ip bgp summary"`| Display BGP peering status | State: `Established` |
| `sudo vtysh -c "show ip bgp neighbors"`| Detailed peer information | BGP state = `Established` |
| `sudo vtysh -c "show ip route"`| Confirm advertised and learned routes | Loopback visible in `RIB` |
| `ping <peer_ip>`| Test connectivity to switch | Successful response |



