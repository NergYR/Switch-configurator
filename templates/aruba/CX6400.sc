{
  "model": "CX6400",
  "port_layout": {
    "rows": 4,
    "cols": 12,
    "total_ports": 48
  },
  "supports": {
    "vlan": true,
    "trunk": true,
    "stacking": true
  },
  "default_commands": [
    "hostname {hostname}",
    "ssh server vrf default",
    "no telnet-server",
    "ntp enable",
    "spanning-tree",
    "spanning-tree config-name {hostname}"
  ]
}
