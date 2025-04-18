{
  "model": "C3850-48T",
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
    "hostname {hostname}",
    "no ip domain-lookup",
    "service password-encryption",
    "spanning-tree mode rapid-pvst",
    "spanning-tree extend system-id",
    "vtp mode transparent"
  ]
}
