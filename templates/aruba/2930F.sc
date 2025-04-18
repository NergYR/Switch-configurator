{
  "model": "2930F",
  "port_layout": {
    "rows": 2,
    "cols": 12,
    "total_ports": 24
  },
  "supports": {
    "vlan": true,
    "trunk": true,
    "stacking": true
  },
  "default_commands": [
    "hostname {hostname}",
    "no telnet-server",
    "password manager user-name admin plaintext",
    "spanning-tree",
    "spanning-tree force-version rstp-operation"
  ]
}
