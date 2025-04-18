#!/usr/bin/env python3
"""
Script pour mettre à jour la version du Switch Configurator.
Utilise EndoriumUtils pour gérer les versions.
"""

import sys
import argparse
from datetime import datetime

try:
    from EndoriumUtils import get_logger, get_version, increment_version, set_version
except ImportError:
    print("EndoriumUtils non trouvé. Veuillez l'installer avec 'pip install EndoriumUtils'")
    sys.exit(1)

logger = get_logger("version_updater")

def main():
    parser = argparse.ArgumentParser(description="Gestionnaire de version pour Switch Configurator")
    parser.add_argument('action', choices=['get', 'set', 'increment'],
                        help='Action à effectuer sur la version')
    parser.add_argument('--value', '-v', help='Nouvelle version (pour "set") ou niveau (pour "increment")')
    args = parser.parse_args()
    
    try:
        if args.action == 'get':
            version_str, version_list = get_version()
            print(f"Version actuelle: {version_str}")
            
        elif args.action == 'set':
            if not args.value:
                parser.error("L'option --value est requise pour l'action 'set'")
            
            set_version(args.value)
            version_str, _ = get_version()
            print(f"Version définie à: {version_str}")
            logger.info(f"Version modifiée manuellement à {version_str}")
            
        elif args.action == 'increment':
            level = args.value if args.value in ['major', 'minor', 'patch'] else 'patch'
            
            old_version, _ = get_version()
            new_version = increment_version(level)
            print(f"Version mise à jour: {old_version} -> {new_version}")
            
            # Ajouter un log avec des détails
            logger.info(f"Version incrémentée ({level}): {old_version} -> {new_version}")
            
            # Créer un fichier de changelog
            with open('CHANGELOG.md', 'a') as f:
                f.write(f"\n## Version {new_version} ({datetime.now().strftime('%Y-%m-%d')})\n")
                f.write("\n*Ajoutez ici les changements apportés dans cette version*\n\n")
    
    except Exception as e:
        logger.error(f"Erreur lors de la gestion de la version: {str(e)}")
        print(f"Erreur: {str(e)}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
