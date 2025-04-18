{
  "model": "C3560-12P",
  "port_layout": {
    "rows": 1,
    "cols": 12,
    "total_ports": 12
  },
  "supports": {
    "vlan": true,
    "trunk": true,
    "stacking": false,
    "poe": true
  },
  "default_commands": [
    "hostname {hostname}",
    "no ip domain-lookup",
    "service password-encryption",
    "spanning-tree mode rapid-pvst",
    "spanning-tree extend system-id",
    "vtp mode transparent",
    "power inline consumption default 15400"
  ]
}
