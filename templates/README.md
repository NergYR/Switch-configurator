# Templates pour Switch Configurator

Ce dossier contient les templates pour différentes marques et modèles de switches.

## Structure des dossiers

Les templates doivent suivre cette structure:
```
templates/
├── <marque>/
│   ├── <modèle1>.sc
│   ├── <modèle2>.sc
│   └── ...
├── <autre_marque>/
│   ├── <modèle1>.sc
│   └── ...
```

## Format de fichier .sc

Les fichiers .sc sont des fichiers JSON qui définissent les caractéristiques du switch. Exemple:

```json
{
  "model": "C3750X-48P",
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
    "service password-encryption"
  ]
}
```

## Marques et modèles disponibles

Voici quelques exemples de marques et modèles déjà configurés:

- Cisco
  - C2960-24
  - C3750X-48P
- HP
  - 2530-48G
- Juniper
  - EX2300-48P
