{
  "model": "6000",
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
    "no telnet-server",
    "no web-management plaintext",
    "web-management ssl",
    "spanning-tree",
    "spanning-tree mode rapid-pvst"
  ]
}
