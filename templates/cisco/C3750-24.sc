{
  "model": "C3750-24",
  "port_layout": {
    "rows": 1,
    "cols": 24,
    "total_ports": 24
  },
  "supports": {
    "vlan": true,
    "trunk": true,
    "stacking": true,
    "poe": false
  },
  "default_commands": [
    "hostname {hostname}",
    "no ip domain-lookup",
    "service password-encryption",
    "spanning-tree mode rapid-pvst",
    "spanning-tree extend system-id",
    "vtp mode transparent",
    "switch 1 provision ws-c3750-24ts"
  ]
}
