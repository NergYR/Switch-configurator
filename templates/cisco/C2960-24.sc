{
  "model": "C2960-24",
  "port_layout": {
    "rows": 2,
    "cols": 12,
    "total_ports": 24
  },
  "supports": {
    "vlan": true,
    "trunk": true,
    "stacking": false
  },
  "default_commands": [
    "hostname {hostname}",
    "no ip domain-lookup",
    "service password-encryption",
    "spanning-tree mode rapid-pvst",
    "interface range fastEthernet 0/1-24",
    " shutdown"
  ]
}
