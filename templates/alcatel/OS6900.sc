{
  "model": "OS6900",
  "port_layout": {
    "rows": 2,
    "cols": 20,
    "total_ports": 40
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
    "spanning-tree mode mstp",
    "spanning-tree mst configuration",
    "name {hostname}-MSTP",
    "exit",
    "ntp client enable"
  ]
}
