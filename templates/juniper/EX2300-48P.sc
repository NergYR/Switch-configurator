{
  "model": "EX2300-48P",
  "port_layout": {
    "rows": 2,
    "cols": 24,
    "total_ports": 48
  },
  "supports": {
    "vlan": true,
    "trunk": true,
    "stacking": true
  },
  "default_commands": [
    "set system host-name {hostname}",
    "set system services ssh",
    "set system services web-management https system-generated-certificate",
    "set vlans default vlan-id 1"
  ]
}
