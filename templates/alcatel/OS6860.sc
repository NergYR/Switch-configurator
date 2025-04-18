{
  "model": "OS6860",
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
    "ip service ssh",
    "no ip service telnet",
    "spanning-tree mode rstp",
    "spanning-tree rstp priority 32768"
  ]
}
