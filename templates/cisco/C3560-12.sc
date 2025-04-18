{
  "model": "C3560-12",
  "port_layout": {
    "rows": 1,
    "cols": 12,
    "total_ports": 12
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
