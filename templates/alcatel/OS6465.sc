{
  "model": "OS6465",
  "port_layout": {
    "rows": 1,
    "cols": 24,
    "total_ports": 24
  },
  "supports": {
    "vlan": true,
    "trunk": true,
    "stacking": false
  },
  "default_commands": [
    "hostname {hostname}",
    "ip service ssh",
    "no ip service telnet",
    "no ip service http",
    "spanning-tree mode rstp",
    "snmp-server community public ro"
  ]
}
