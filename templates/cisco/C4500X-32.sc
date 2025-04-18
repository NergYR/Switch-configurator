{
  "model": "C4500X-32",
  "port_layout": {
    "rows": 1,
    "cols": 32,
    "total_ports": 32
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
    "vtp mode transparent",
    "redundancy",
    "mode sso",
    "ip routing"
  ]
}
