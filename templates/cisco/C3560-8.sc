{
  "model": "C3560-8",
  "port_layout": {
    "rows": 1,
    "cols": 8,
    "total_ports": 8
  },
  "supports": {
    "vlan": true,
    "trunk": true,
    "stacking": false,
    "poe": false
  },
  "default_commands": [
    "hostname {hostname}",
    "no ip domain-lookup",
    "service password-encryption",
    "spanning-tree mode rapid-pvst",
    "spanning-tree extend system-id",
    "vtp mode transparent"
  ]
}
