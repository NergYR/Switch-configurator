import sys
import os
import json
import time
import re
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                            QLabel, QPushButton, QComboBox, QLineEdit, QGridLayout,
                            QScrollArea, QTableWidget, QTableWidgetItem, QMessageBox,
                            QTabWidget, QFrame, QGroupBox, QFormLayout, QDialog, QDialogButtonBox,
                            QTextEdit, QCheckBox, QProgressBar, QInputDialog, QFileDialog)
from PySide6.QtCore import Qt, QSize, QTimer, QSettings
from PySide6.QtGui import QPainter, QColor, QPen, QBrush

# Configuration de l'application
APP_NAME = "Switch-configurator"
APP_VERSION = "1.0.0"

# Vérification de la disponibilité d'EndoriumUtils
try:
    from EndoriumUtils import get_logger, log_function_call, log_performance
    from EndoriumUtils import get_version, increment_version, set_version
    ENDORIUM_AVAILABLE = True
    
    # Initialisation du logger avec le nom de l'application
    logger = get_logger(APP_NAME)
    
    try:
        # Tenter de récupérer la version depuis EndoriumUtils
        version_str, version_list = get_version()
        APP_VERSION = version_str
    except Exception as e:
        # Si la version n'est pas définie, initialiser avec notre version par défaut
        logger.warning(f"Impossible de récupérer la version: {e}. Utilisation de la version par défaut {APP_VERSION}")
        set_version(APP_VERSION)
    
    logger.info(f"Application démarrée - version {APP_VERSION}")
except ImportError:
    print("EndoriumUtils non trouvé. Fonctionnalités de journalisation désactivées.")
    ENDORIUM_AVAILABLE = False
    # Fallback si EndoriumUtils n'est pas disponible
    logger = None

# Importation des fonctions TFTP
try:
    from tftp_helper import is_tftp_available, upload_config_via_tftp, check_connectivity
    TFTP_AVAILABLE = is_tftp_available()
    if ENDORIUM_AVAILABLE and TFTP_AVAILABLE:
        logger.info("Module TFTP disponible et chargé")
    elif ENDORIUM_AVAILABLE:
        logger.warning("Module TFTP non disponible. Les fonctionnalités TFTP seront désactivées.")
except ImportError:
    TFTP_AVAILABLE = False
    if ENDORIUM_AVAILABLE and logger is not None:
        logger.warning("Module TFTP non disponible. Installez-le avec 'pip install tftpy'")
    print("Module TFTP non disponible. Installez-le avec 'pip install tftpy'")

# --- Nouveau : import et disponibilité console série ---
try:
    from serial_helper import is_serial_available, SerialConfigSender, list_available_serial_ports
    SERIAL_AVAILABLE = is_serial_available()
    if ENDORIUM_AVAILABLE and SERIAL_AVAILABLE:
        logger.info("Module série disponible et chargé")
    elif ENDORIUM_AVAILABLE:
        logger.warning("Module série non disponible. Fonctionnalités console désactivées.")
except ImportError:
    SERIAL_AVAILABLE = False
    if ENDORIUM_AVAILABLE and logger is not None:
        logger.warning("Module série non disponible. Installez-le avec 'pip install pyserial'")
    print("Module série non disponible. Installez-le avec 'pip install pyserial'")

# Classe pour gérer les modèles de switch
class SwitchTemplateManager:
    def __init__(self):
        self.base_path = os.path.join(os.path.dirname(__file__), "templates")
        if not os.path.exists(self.base_path):
            os.makedirs(self.base_path)
            if ENDORIUM_AVAILABLE:
                logger.info(f"Répertoire de templates créé: {self.base_path}")
    
    @log_function_call if ENDORIUM_AVAILABLE else lambda f: f
    def get_available_brands(self):
        if not os.path.exists(self.base_path):
            return []
        brands = [d for d in os.listdir(self.base_path) if os.path.isdir(os.path.join(self.base_path, d)) and d != "__pycache__"]
        if ENDORIUM_AVAILABLE:
            logger.debug(f"Marques disponibles: {brands}")
        return brands
    
    @log_function_call if ENDORIUM_AVAILABLE else lambda f: f
    def get_available_models(self, brand):
        brand_path = os.path.join(self.base_path, brand)
        if not os.path.exists(brand_path):
            return []
        models = [f.replace('.sc', '') for f in os.listdir(brand_path) if f.endswith('.sc')]
        if ENDORIUM_AVAILABLE:
            logger.debug(f"Modèles disponibles pour {brand}: {models}")
        return models
    
    def get_template_path(self, brand, model):
        return os.path.join(self.base_path, brand, f"{model}.sc")
    
    @log_function_call if ENDORIUM_AVAILABLE else lambda f: f
    def load_template(self, brand, model):
        template_path = self.get_template_path(brand, model)
        if os.path.exists(template_path):
            try:
                with log_performance(logger, f"Chargement du template {brand}/{model}") if ENDORIUM_AVAILABLE else nullcontext():
                    with open(template_path, 'r') as f:
                        # Supprimer les commentaires éventuels (comme le filepath)
                        content = '\n'.join([line for line in f if not line.strip().startswith('//')])
                        template = json.loads(content)
                        if ENDORIUM_AVAILABLE:
                            logger.info(f"Template {brand}/{model} chargé avec succès")
                        return template
            except (json.JSONDecodeError, IOError) as e:
                if ENDORIUM_AVAILABLE:
                    logger.error(f"Erreur lors du chargement du template {template_path}: {str(e)}")
                return None
        return None

# Classe pour représenter un switch
class Switch:
    def __init__(self, brand, model):
        self.brand = brand
        self.model = model
        self.vlans = {}  # {id: name}
        self.ports = {}  # {port_number: {'mode': 'access/trunk/shutdown', 'vlan': id, 'poe': bool}}
        self.vlan_interfaces = {}  # {vlan_id: {'ip': ip_address, 'mask': mask, ...}}
        self.hostname = f"{brand}-{model}"
        
        # Charger le template
        with log_performance(logger, f"Initialisation du switch {brand}/{model}") if ENDORIUM_AVAILABLE else nullcontext():
            self.template = self._load_template(brand, model)
            # Définir la disposition des ports selon le modèle
            self.port_layout = self._get_port_layout()
        
        # Vérifier si le switch supporte le PoE
        self.supports_poe = self._supports_poe()
        
        # --- Attributs SNMP ---
        self.snmp_enabled = False
        self.snmp_community = "public"
        self.snmp_version = "2c"
        self.snmp_location = ""
        self.snmp_contact = ""
        
        # --- Attributs SSH ---
        self.ssh_enabled = False
        self.ssh_version = "2"
        self.ssh_timeout = "60"
        self.ssh_auth_retries = "3"
        self.ssh_key_auth = False
        self.ssh_users = []  # liste de dicts {login, password, privilege}
        
        # --- Attributs Spanning Tree ---
        self.stp_enabled = True
        self.stp_mode = "rapid-pvst"  # rapid-pvst, pvst, mst
        self.stp_priority = "32768"  # valeur par défaut
        self.stp_portfast = True
        self.stp_bpduguard = True
        self.stp_loopguard = False
        
        if ENDORIUM_AVAILABLE:
            logger.info(f"Switch {brand} {model} initialisé avec configurations par défaut")
    
    def _load_template(self, brand, model):
        template_manager = SwitchTemplateManager()
        template = template_manager.load_template(brand, model)
        return template or {}
    
    def _get_port_layout(self):
        # Essayer de récupérer la configuration des ports depuis le template
        if self.template and "port_layout" in self.template:
            if ENDORIUM_AVAILABLE:
                logger.debug(f"Layout des ports chargé depuis le template: {self.template['port_layout']}")
            return self.template["port_layout"]
        
        # Sinon, utiliser une configuration par défaut
        default_layout = {
            "rows": 2,
            "cols": 12,
            "total_ports": 24
        }
        if ENDORIUM_AVAILABLE:
            logger.warning(f"Aucun layout de ports trouvé dans le template, utilisation des valeurs par défaut: {default_layout}")
        return default_layout
    
    def _supports_poe(self):
        """Vérifie si le switch supporte le PoE"""
        if self.template and "supports" in self.template:
            return self.template["supports"].get("poe", False)
        return False
    
    @log_function_call if ENDORIUM_AVAILABLE else lambda f: f
    def add_vlan(self, vlan_id, vlan_name):
        self.vlans[vlan_id] = vlan_name
        if ENDORIUM_AVAILABLE:
            logger.info(f"VLAN ajouté: ID {vlan_id}, Nom {vlan_name}")
    
    @log_function_call if ENDORIUM_AVAILABLE else lambda f: f
    def set_port_config(self, port_number, mode, vlan=None, poe_enabled=False):
        self.ports[port_number] = {'mode': mode, 'vlan': vlan, 'poe': poe_enabled}
        if ENDORIUM_AVAILABLE:
            logger.info(f"Port {port_number} configuré: mode={mode}, vlan={vlan}, poe={poe_enabled}")
    
    @log_function_call if ENDORIUM_AVAILABLE else lambda f: f
    def set_vlan_interface(self, vlan_id, **kwargs):
        self.vlan_interfaces[vlan_id] = kwargs
        if ENDORIUM_AVAILABLE:
            logger.info(f"Interface VLAN {vlan_id} configurée: {kwargs}")
    
    @log_function_call if ENDORIUM_AVAILABLE else lambda f: f
    def set_hostname(self, hostname):
        if ENDORIUM_AVAILABLE:
            logger.info(f"Hostname changé: {self.hostname} -> {hostname}")
        self.hostname = hostname
    
    def set_snmp(self, enabled, community="public", version="2c", location="", contact=""):
        """Configure les paramètres SNMP"""
        self.snmp_enabled = enabled
        self.snmp_community = community
        self.snmp_version = version
        self.snmp_location = location
        self.snmp_contact = contact
        
        if ENDORIUM_AVAILABLE:
            logger.info(f"SNMP {'activé' if enabled else 'désactivé'}, communauté={community}, version={version}")

    def set_ssh(self, enabled, version="2", timeout="60", auth_retries="3", key_auth=False):
        """Configure les paramètres SSH"""
        self.ssh_enabled = enabled
        self.ssh_version = version
        self.ssh_timeout = timeout
        self.ssh_auth_retries = auth_retries
        self.ssh_key_auth = key_auth
        
        if ENDORIUM_AVAILABLE:
            logger.info(f"SSH {'activé' if enabled else 'désactivé'}, version={version}, timeout={timeout}")

    def set_spanning_tree(self, enabled, mode="rapid-pvst", priority="32768", 
                         portfast=True, bpduguard=True, loopguard=False):
        """Configure les paramètres Spanning Tree"""
        self.stp_enabled = enabled
        self.stp_mode = mode
        self.stp_priority = priority
        self.stp_portfast = portfast
        self.stp_bpduguard = bpduguard
        self.stp_loopguard = loopguard
        
        if ENDORIUM_AVAILABLE:
            logger.info(f"Spanning Tree {'activé' if enabled else 'désactivé'}, mode={mode}")

    @log_function_call if ENDORIUM_AVAILABLE else lambda f: f
    def generate_config(self):
        if ENDORIUM_AVAILABLE:
            logger.info(f"Génération de la configuration pour {self.brand} {self.model}")
        
        with log_performance(logger, "Génération de configuration") if ENDORIUM_AVAILABLE else nullcontext():
            config = []
            
            # Configuration de base selon la marque
            if self.brand.lower() == "cisco":
                config.append("enable")
                config.append("configure terminal")
                config.append(f"hostname {self.hostname}")
                
                # Configuration des VLANs
                for vlan_id, vlan_name in self.vlans.items():
                    config.append(f"vlan {vlan_id}")
                    config.append(f" name {vlan_name}")
                    config.append("!")
                
                # Configuration des ports
                for port, settings in self.ports.items():
                    config.append(f"interface GigabitEthernet0/{port}")
                    if settings['mode'] == 'shutdown':
                        config.append(" shutdown")
                    elif settings['mode'] == 'access':
                        config.append(" switchport mode access")
                        if settings.get('vlan'):
                            config.append(f" switchport access vlan {settings['vlan']}")
                    elif settings['mode'] == 'trunk':
                        config.append(" switchport mode trunk")
                    
                    # Configuration PoE si supporté et activé
                    if self.supports_poe and settings.get('poe', False):
                        config.append(" power inline auto")
                    elif self.supports_poe and not settings.get('poe', False):
                        config.append(" power inline never")
                    
                    config.append("!")
                
                # Configuration des interfaces VLAN
                for vlan_id, vlan_settings in self.vlan_interfaces.items():
                    config.append(f"interface Vlan{vlan_id}")
                    if 'ip' in vlan_settings and 'mask' in vlan_settings:
                        config.append(f" ip address {vlan_settings['ip']} {vlan_settings['mask']}")
                    if vlan_settings.get('shutdown', False):
                        config.append(" shutdown")
                    else:
                        config.append(" no shutdown")
                    config.append("!")
                    
                # Ajouter des commandes de base à partir du template
                if "default_commands" in self.template:
                    for cmd in self.template["default_commands"]:
                        config.append(cmd.replace("{hostname}", self.hostname))
                
                # --- Configuration Spanning Tree ---
                if self.stp_enabled:
                    config.append(f"spanning-tree mode {self.stp_mode}")
                    config.append(f"spanning-tree vlan 1-4094 priority {self.stp_priority}")
                    if self.stp_portfast:
                        config.append("spanning-tree portfast default")
                    if self.stp_bpduguard:
                        config.append("spanning-tree portfast bpduguard default")
                    if self.stp_loopguard:
                        config.append("spanning-tree loopguard default")
                else:
                    config.append("no spanning-tree")
                
                # --- Sécurité de base ---
                config.append("ip dhcp snooping")
                config.append("ip dhcp snooping vlan all")
                
                # --- SNMP si activé ---
                if self.snmp_enabled:
                    config.append(f"snmp-server community {self.snmp_community} RO")
                    if self.snmp_version:
                        config.append(f"snmp-server enable traps")
                    if self.snmp_location:
                        config.append(f"snmp-server location {self.snmp_location}")
                    if self.snmp_contact:
                        config.append(f"snmp-server contact {self.snmp_contact}")
                
                # --- SSH si activé ---
                if self.ssh_enabled:
                    config.append(f"ip ssh version {self.ssh_version}")
                    config.append(f"ip ssh time-out {self.ssh_timeout}")
                    config.append(f"ip ssh authentication-retries {self.ssh_auth_retries}")
                    config.append("line vty 0 15")
                    config.append(" transport input ssh")
                    if not self.ssh_key_auth:
                        config.append(" login local")
                    else:
                        config.append(" login")
                    # commandes pour chaque utilisateur SSH
                    for user in self.ssh_users:
                        config.append(f"username {user['login']} privilege {user['privilege']} secret {user['password']}")
            
            elif self.brand.lower() == "hp":
                config.append("configure")
                config.append(f"hostname {self.hostname}")
                
                # Configuration des VLANs
                for vlan_id, vlan_name in self.vlans.items():
                    config.append(f"vlan {vlan_id}")
                    config.append(f" name {vlan_name}")
                    config.append("exit")
                
                # Configuration des ports
                for port, settings in self.ports.items():
                    config.append(f"interface {port}")
                    if settings['mode'] == 'shutdown':
                        config.append(" disable")
                    elif settings['mode'] == 'access':
                        if settings.get('vlan'):
                            config.append(" untagged vlan " + str(settings['vlan']))
                    elif settings['mode'] == 'trunk':
                        config.append(" tagged vlan " + ",".join([str(v) for v in self.vlans.keys()]))
                    
                    # Configuration PoE si supporté et activé
                    if self.supports_poe and settings.get('poe', False):
                        config.append(" poe enable")
                    elif self.supports_poe and not settings.get('poe', False):
                        config.append(" poe disable")
                    
                    config.append("exit")
                
                # Configuration des interfaces VLAN
                for vlan_id, vlan_settings in self.vlan_interfaces.items():
                    config.append(f"vlan {vlan_id}")
                    if 'ip' in vlan_settings and 'mask' in vlan_settings:
                        config.append(f" ip address {vlan_settings['ip']} {vlan_settings['mask']}")
                    config.append("exit")
                    
                # Ajouter des commandes de base à partir du template
                if "default_commands" in self.template:
                    for cmd in self.template["default_commands"]:
                        config.append(cmd.replace("{hostname}", self.hostname))
            
            elif self.brand.lower() == "juniper":
                config.append("configure")
                config.append("set system host-name " + self.hostname)
                
                # Configuration des VLANs
                for vlan_id, vlan_name in self.vlans.items():
                    config.append(f"set vlans {vlan_name} vlan-id {vlan_id}")
                
                # Configuration des ports
                for port, settings in self.ports.items():
                    interface_name = f"ge-0/0/{port}"
                    if settings['mode'] == 'shutdown':
                        config.append(f"set interfaces {interface_name} disable")
                    elif settings['mode'] == 'access':
                        if settings.get('vlan'):
                            vlan_name = self.vlans.get(settings['vlan'], "")
                            config.append(f"set interfaces {interface_name} unit 0 family ethernet-switching port-mode access")
                            config.append(f"set interfaces {interface_name} unit 0 family ethernet-switching vlan members {vlan_name}")
                    elif settings['mode'] == 'trunk':
                        config.append(f"set interfaces {interface_name} unit 0 family ethernet-switching port-mode trunk")
                        for vlan_id, vlan_name in self.vlans.items():
                            config.append(f"set interfaces {interface_name} unit 0 family ethernet-switching vlan members {vlan_name}")
                    
                    # Configuration PoE si supporté et activé
                    if self.supports_poe and settings.get('poe', False):
                        config.append(f"set poe interface {interface_name} enable")
                    elif self.supports_poe and not settings.get('poe', False):
                        config.append(f"set poe interface {interface_name} disable")
                
                # Configuration des interfaces VLAN
                for vlan_id, vlan_settings in self.vlan_interfaces.items():
                    vlan_name = self.vlans.get(vlan_id, f"vlan{vlan_id}")
                    if 'ip' in vlan_settings and 'mask' in vlan_settings:
                        config.append(f"set interfaces irb unit {vlan_id} family inet address {vlan_settings['ip']}/{vlan_settings['mask']}")
                        config.append(f"set vlans {vlan_name} l3-interface irb.{vlan_id}")
                    
                # Ajouter des commandes de base à partir du template
                if "default_commands" in self.template:
                    for cmd in self.template["default_commands"]:
                        config.append(cmd.replace("{hostname}", self.hostname))
            
            elif self.brand.lower() == "aruba":
                config.append("configure")
                config.append(f"hostname {self.hostname}")
                
                # Configuration des VLANs
                for vlan_id, vlan_name in self.vlans.items():
                    config.append(f"vlan {vlan_id}")
                    config.append(f" name {vlan_name}")
                    config.append("exit")
                
                # Configuration des ports
                for port, settings in self.ports.items():
                    config.append(f"interface {port}")
                    if settings['mode'] == 'shutdown':
                        config.append(" disable")
                    elif settings['mode'] == 'access':
                        if settings.get('vlan'):
                            config.append(f" vlan access {settings['vlan']}")
                    elif settings['mode'] == 'trunk':
                        config.append(" trunk")
                        for vlan_id in self.vlans.keys():
                            config.append(f" trunk allowed vlan {vlan_id}")
                    
                    # Configuration PoE si supporté et activé
                    if self.supports_poe and settings.get('poe', False):
                        config.append(" poe-max-power 30")
                    elif self.supports_poe and not settings.get('poe', False):
                        config.append(" no poe")
                    
                    config.append("exit")
                
                # Configuration des interfaces VLAN
                for vlan_id, vlan_settings in self.vlan_interfaces.items():
                    config.append(f"vlan {vlan_id}")
                    if 'ip' in vlan_settings and 'mask' in vlan_settings:
                        config.append(f" ip address {vlan_settings['ip']} {vlan_settings['mask']}")
                    config.append("exit")
                
                # Ajouter des commandes de base à partir du template
                if "default_commands" in self.template:
                    for cmd in self.template["default_commands"]:
                        config.append(cmd.replace("{hostname}", self.hostname))
            
            elif self.brand.lower() == "alcatel":
                config.append("configure terminal")
                config.append(f"system name {self.hostname}")
                
                # Configuration des VLANs
                for vlan_id, vlan_name in self.vlans.items():
                    config.append(f"vlan {vlan_id}")
                    config.append(f" name \"{vlan_name}\"")
                    config.append(" exit")
                
                # Configuration des ports
                for port, settings in self.ports.items():
                    port_name = f"1/1/{port}"
                    config.append(f"interfaces port {port_name}")
                    
                    if settings['mode'] == 'shutdown':
                        config.append(" admin-state disable")
                    else:
                        config.append(" admin-state enable")
                        
                    if settings['mode'] == 'access':
                        if settings.get('vlan'):
                            config.append(f" vlan {settings['vlan']} port default")
                    elif settings['mode'] == 'trunk':
                        config.append(" spanning-tree auto-edge-port disable")
                        for vlan_id in self.vlans.keys():
                            config.append(f" vlan {vlan_id} port")
                    
                    # Configuration PoE si supporté et activé
                    if self.supports_poe and settings.get('poe', False):
                        config.append(" power over-ethernet admin-state enable")
                        config.append(" power over-ethernet priority high")
                    elif self.supports_poe and not settings.get('poe', False):
                        config.append(" power over-ethernet admin-state disable")
                    
                    config.append(" exit")
                
                # Configuration des interfaces VLAN
                for vlan_id, vlan_settings in self.vlan_interfaces.items():
                    config.append(f"vlan {vlan_id}")
                    if 'ip' in vlan_settings and 'mask' in vlan_settings:
                        config.append(f" router interface")
                        config.append(f" address {vlan_settings['ip']} mask {vlan_settings['mask']}")
                        if vlan_settings.get('shutdown', False):
                            config.append(" admin-state disable")
                        else:
                            config.append(" admin-state enable")
                        if 'description' in vlan_settings and vlan_settings['description']:
                            config.append(f" description \"{vlan_settings['description']}\"")
                        config.append(" exit")
                    config.append(" exit")
                
                # Configuration SNMP si activée
                if self.snmp_enabled:
                    config.append(f"snmp community map {self.snmp_community} user \"admin\" on")
                    if self.snmp_location:
                        config.append(f"snmp system location \"{self.snmp_location}\"")
                    if self.snmp_contact:
                        config.append(f"snmp system contact \"{self.snmp_contact}\"") 
                
                # Configuration SSH si activée
                if self.ssh_enabled:
                    config.append("ip service ssh")
                    config.append(f"ip service ssh version v{self.ssh_version}")
                    config.append(f"ip service ssh timeout {self.ssh_timeout}")
                else:
                    config.append("no ip service ssh")
                
                # Configuration Spanning Tree
                if self.stp_enabled:
                    config.append("spanning-tree admin-state enable")
                    mode_map = {"rapid-pvst": "rstp", "pvst": "flat", "mst": "mstp"}
                    stp_mode = mode_map.get(self.stp_mode, "rstp")
                    config.append(f"spanning-tree mode {stp_mode}")
                    config.append(f"spanning-tree priority {self.stp_priority}")
                    if self.stp_portfast:
                        config.append("spanning-tree auto-edge-port enable")
                    if self.stp_bpduguard:
                        config.append("spanning-tree bpdu-guard enable")
                else:
                    config.append("spanning-tree admin-state disable")
                
                # Ajouter des commandes de base à partir du template
                if "default_commands" in self.template:
                    for cmd in self.template["default_commands"]:
                        config.append(cmd.replace("{hostname}", self.hostname))
        
        if ENDORIUM_AVAILABLE:
            logger.debug(f"Configuration générée ({len(config)} lignes)")
            
        return "\n".join(config)

# Classe contextuelle pour simuler log_performance quand EndoriumUtils n'est pas disponible
class nullcontext:
    def __init__(self, *args, **kwargs):
        pass
    def __enter__(self):
        return None
    def __exit__(self, *exc):
        return False

# Fenêtre pour la sélection de marque et modèle
class BrandModelSelectionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.template_manager = SwitchTemplateManager()
        self.setWindowTitle("Sélection de la marque et du modèle")
        self.resize(400, 200)
        self.selected_brand = None
        self.selected_model = None
        
        layout = QVBoxLayout(self)
        
        # Sélection de la marque
        brand_layout = QHBoxLayout()
        brand_layout.addWidget(QLabel("Marque:"))
        self.brand_combo = QComboBox()
        # Récupérer et trier les marques disponibles
        brands = sorted(self.template_manager.get_available_brands())
        self.brand_combo.addItems(brands)
        self.brand_combo.currentIndexChanged.connect(self.update_models)
        brand_layout.addWidget(self.brand_combo)
        layout.addLayout(brand_layout)
        
        # Sélection du modèle
        model_layout = QHBoxLayout()
        model_layout.addWidget(QLabel("Modèle:"))
        self.model_combo = QComboBox()
        model_layout.addWidget(self.model_combo)
        layout.addLayout(model_layout)
        
        # Boutons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        # Initialiser les modèles si des marques sont disponibles
        if self.brand_combo.count() > 0:
            self.update_models()
    
    def update_models(self):
        self.model_combo.clear()
        selected_brand = self.brand_combo.currentText()
        # Récupérer et trier les modèles disponibles pour cette marque
        models = sorted(self.template_manager.get_available_models(selected_brand))
        self.model_combo.addItems(models)
    
    def accept(self):
        self.selected_brand = self.brand_combo.currentText()
        self.selected_model = self.model_combo.currentText()
        
        # S'assurer qu'un modèle est sélectionné
        if not self.selected_model:
            QMessageBox.warning(self, "Avertissement", "Veuillez sélectionner un modèle.")
            return
            
        # Vérifier que le template existe bien
        template = self.template_manager.load_template(self.selected_brand, self.selected_model)
        if not template:
            QMessageBox.warning(self, "Erreur", f"Le template pour {self.selected_brand} {self.selected_model} est introuvable ou invalide.")
            return
            
        super().accept()

# Fenêtre pour configurer les VLANs
class VlanConfigurationDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuration des VLANs")
        self.resize(500, 300)
        self.vlans = {}  # {id: name}
        
        layout = QVBoxLayout(self)
        
        # Table des VLANs
        self.vlan_table = QTableWidget(0, 2)
        self.vlan_table.setHorizontalHeaderLabels(["ID", "Nom"])
        self.vlan_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.vlan_table)
        
        # Formulaire d'ajout
        form_layout = QHBoxLayout()
        self.vlan_id_input = QLineEdit()
        self.vlan_id_input.setPlaceholderText("ID VLAN (1-4094)")
        form_layout.addWidget(self.vlan_id_input)
        
        self.vlan_name_input = QLineEdit()
        self.vlan_name_input.setPlaceholderText("Nom du VLAN")
        form_layout.addWidget(self.vlan_name_input)
        
        add_btn = QPushButton("Ajouter")
        add_btn.clicked.connect(self.add_vlan)
        form_layout.addWidget(add_btn)
        
        layout.addLayout(form_layout)
        
        # Bouton de suppression
        delete_btn = QPushButton("Supprimer le VLAN sélectionné")
        delete_btn.clicked.connect(self.delete_selected_vlan)
        layout.addWidget(delete_btn)
        
        # Boutons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def add_vlan(self):
        try:
            vlan_id = int(self.vlan_id_input.text())
            if vlan_id < 1 or vlan_id > 4094:
                raise ValueError("L'ID VLAN doit être entre 1 et 4094")
            
            vlan_name = self.vlan_name_input.text()
            if not vlan_name:
                raise ValueError("Le nom du VLAN ne peut pas être vide")
            
            # Vérifier si le VLAN existe déjà
            if vlan_id in self.vlans:
                response = QMessageBox.question(self, "VLAN existant", 
                                             f"Le VLAN {vlan_id} existe déjà. Voulez-vous le remplacer ?",
                                             QMessageBox.Yes | QMessageBox.No)
                if response == QMessageBox.No:
                    return
                
                # Trouver la ligne correspondante et la mettre à jour
                for row in range(self.vlan_table.rowCount()):
                    if self.vlan_table.item(row, 0).text() == str(vlan_id):
                        self.vlan_table.setItem(row, 1, QTableWidgetItem(vlan_name))
                        break
            else:
                # Ajouter à la table
                row_position = self.vlan_table.rowCount()
                self.vlan_table.insertRow(row_position)
                self.vlan_table.setItem(row_position, 0, QTableWidgetItem(str(vlan_id)))
                self.vlan_table.setItem(row_position, 1, QTableWidgetItem(vlan_name))
            
            # Effacer les champs
            self.vlan_id_input.clear()
            self.vlan_name_input.clear()
            
            # Mettre à jour le dictionnaire
            self.vlans[vlan_id] = vlan_name
            
        except ValueError as e:
            QMessageBox.warning(self, "Erreur", str(e))
    
    def delete_selected_vlan(self):
        selected_rows = self.vlan_table.selectedIndexes()
        if not selected_rows:
            QMessageBox.warning(self, "Avertissement", "Veuillez sélectionner un VLAN à supprimer.")
            return
        
        row = selected_rows[0].row()
        vlan_id = int(self.vlan_table.item(row, 0).text())
        
        response = QMessageBox.question(self, "Confirmation", 
                                     f"Êtes-vous sûr de vouloir supprimer le VLAN {vlan_id} ?",
                                     QMessageBox.Yes | QMessageBox.No)
        if response == QMessageBox.Yes:
            self.vlan_table.removeRow(row)
            del self.vlans[vlan_id]
    
    def accept(self):
        if not self.vlans:
            QMessageBox.warning(self, "Avertissement", "Aucun VLAN n'a été configuré.")
            return
        super().accept()

# Configuration du hostname
class HostnameDialog(QDialog):
    def __init__(self, current_hostname, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuration du nom d'hôte")
        self.resize(400, 150)
        
        layout = QVBoxLayout(self)
        
        # Champ pour le hostname
        form_layout = QFormLayout()
        self.hostname_input = QLineEdit(current_hostname)
        form_layout.addRow("Nom d'hôte:", self.hostname_input)
        layout.addLayout(form_layout)
        
        # Boutons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def get_hostname(self):
        return self.hostname_input.text()

# Widget pour représenter graphiquement un switch
class SwitchPortWidget(QWidget):
    def __init__(self, switch, main_window=None, parent=None):
        super().__init__(parent)
        self.switch = switch
        self.main_window = main_window
        self.selected_port = None
        self.setMinimumSize(600, 300)
        
        # Légende pour les modes ports
        self.color_legend = {
            "shutdown": QColor(255, 0, 0),    # Rouge
            "trunk": QColor(0, 0, 255),       # Bleu
            "access": QColor(0, 255, 0),      # Vert
            "default": QColor(150, 150, 150)  # Gris
        }
        
        # Couleurs pour les VLANs (générées dynamiquement)
        self.vlan_colors = {}
        self.generate_vlan_colors()
        
        # Pré-calculs pour éviter de recalculer à chaque frame
        self.layout_data = None
    
    def generate_vlan_colors(self):
        """Génère des couleurs distinctives pour chaque VLAN configuré"""
        self.vlan_colors = {}
        for vlan_id in self.switch.vlans.keys():
            hue = (vlan_id * 50) % 360
            self.vlan_colors[vlan_id] = QColor.fromHsv(hue, 200, 200)
    
    def calculate_layout(self):
        """Pré-calcule les données de mise en page pour optimiser le rendu"""
        layout = self.switch.port_layout
        rows = 2  # Format 1U standard
        cols = layout["total_ports"] // rows
        
        # Dimensions et espacements
        chassis_height = min(120, self.height() * 0.3)
        available_width = self.width() - 40
        available_height = chassis_height - 30
        
        port_size = min(available_height / rows * 0.8, available_width / cols * 0.8)
        h_spacing = (available_width - port_size * cols) / (cols + 1)
        v_spacing = (available_height - port_size * rows) / (rows + 1)
        
        y_start = 30
        y_top = y_start + v_spacing
        y_bottom = y_start + v_spacing + port_size + v_spacing
        
        # Stocker les données calculées pour réutilisation
        self.layout_data = {
            'rows': rows,
            'cols': cols,
            'chassis_height': chassis_height,
            'port_size': port_size,
            'h_spacing': h_spacing,
            'v_spacing': v_spacing,
            'y_start': y_start,
            'y_top': y_top,
            'y_bottom': y_bottom
        }
        
        return self.layout_data
    
    def get_port_color(self, port_number):
        """Détermine la couleur d'un port selon sa configuration"""
        port_config = self.switch.ports.get(port_number, {})
        if not port_config:
            return self.color_legend["default"]
        
        if port_config['mode'] == 'shutdown':
            return self.color_legend["shutdown"]
        elif port_config['mode'] == 'trunk':
            return self.color_legend["trunk"]
        elif port_config['mode'] == 'access':
            vlan_id = port_config.get('vlan')
            if vlan_id and vlan_id in self.vlan_colors:
                return self.vlan_colors[vlan_id]
            return self.color_legend["access"]
        
        return self.color_legend["default"]
    
    def draw_port(self, painter, port_number, x, y, size):
        """Dessine un port avec son numéro"""
        # Obtenir la couleur du port
        color = self.get_port_color(port_number)
        
        # Dessiner le port carré
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(Qt.black, 1))
        painter.drawRect(int(x), int(y), int(size), int(size))
        
        # Numéro de port
        painter.setPen(Qt.black)
        font = painter.font()
        font.setBold(False)
        font.setPointSize(7)
        painter.setFont(font)
        text_x = x + size/2 - 5
        text_y = y + size/2 + 3
        painter.drawText(int(text_x), int(text_y), str(port_number))
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Recalculer la mise en page si nécessaire
        if self.layout_data is None or self.layout_data['chassis_height'] != min(120, self.height() * 0.3):
            self.calculate_layout()
        
        # Extraire les données de mise en page
        layout = self.switch.port_layout
        cols = self.layout_data['cols']
        chassis_height = self.layout_data['chassis_height']
        port_size = self.layout_data['port_size']
        h_spacing = self.layout_data['h_spacing']
        y_top = self.layout_data['y_top']
        y_bottom = self.layout_data['y_bottom']
        
        # Dessiner le chassis du switch (format 1U)
        painter.setPen(QPen(Qt.black, 2))
        painter.setBrush(QBrush(QColor(200, 200, 200)))
        painter.drawRect(10, 10, self.width() - 20, chassis_height)
        
        # Dessiner le nom du switch
        painter.setPen(Qt.black)
        font = painter.font()
        font.setBold(True)
        font.setPointSize(10)
        painter.setFont(font)
        painter.drawText(20, 25, f"{self.switch.hostname} - {self.switch.brand} {self.switch.model}")
        
        # Dessiner tous les ports (impairs en haut, pairs en bas)
        for col in range(cols):
            # Port impair (rangée supérieure)
            port_number = col * 2 + 1
            if port_number <= layout["total_ports"]:
                x = 20 + h_spacing + col * (port_size + h_spacing)
                self.draw_port(painter, port_number, x, y_top, port_size)
            
            # Port pair (rangée inférieure)
            port_number = col * 2 + 2
            if port_number <= layout["total_ports"]:
                x = 20 + h_spacing + col * (port_size + h_spacing)
                self.draw_port(painter, port_number, x, y_bottom, port_size)
        
        # Dessiner la légende des modes de port avec un décalage vertical ajusté
        legend_y_pos = chassis_height + 30  # Augmenté de 20 à 30 pour plus d'espace
        self.draw_mode_legend(painter, legend_y_pos)
        
        # Dessiner la légende des VLANs si nécessaire avec un espacement plus grand
        if self.switch.vlans:
            self.draw_vlan_legend(painter, legend_y_pos + 65)  # Augmenté de 55 à 65 pour éviter le chevauchement
    
    def draw_mode_legend(self, painter, y_pos):
        """Dessine la légende des modes de ports avec tout le texte en blanc"""
        legend_items = [
            ("Non configuré", self.color_legend["default"]),
            ("Access", self.color_legend["access"]),
            ("Trunk", self.color_legend["trunk"]),
            ("Shutdown", self.color_legend["shutdown"])
        ]
        
        legend_width = self.width() / len(legend_items)
        
        # Titre de la légende - décalé vers le bas
        font = painter.font()
        font.setBold(True)
        font.setPointSize(9)
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(20, y_pos - 5, "Modes de port:")  # Décalé de -15 à -5 pixels
        
        # Éléments de légende - ajustés à cause du titre décalé
        font.setBold(False)
        font.setPointSize(8)
        painter.setFont(font)
        
        for i, (text, bg_color) in enumerate(legend_items):
            x = 20 + i * legend_width
            
            # Dessiner le carré de couleur avec ajustement vertical
            painter.setBrush(QBrush(bg_color))
            painter.setPen(QPen(Qt.black, 1))
            painter.drawRect(int(x), int(y_pos + 10), 15, 15)  # Ajouté +10 pixels
            
            # Dessiner le texte avec ajustement vertical
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(int(x + 20), int(y_pos + 22), text)  # Ajouté +10 pixels
    
    def draw_vlan_legend(self, painter, y_pos):
        """Dessine la légende des VLANs configurés avec tout le texte en blanc"""
        # Titre de la légende - décalé vers le bas
        font = painter.font()
        font.setBold(True)
        font.setPointSize(9)
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(20, y_pos - 5, "VLANs:")  # Décalé de -15 à -5 pixels
        
        # Configuration de la police
        font.setBold(False)
        font.setPointSize(8)
        painter.setFont(font)
        
        # Calculer la largeur pour chaque VLAN (max 8 par ligne)
        max_per_row = 8
        vlan_legend_width = (self.width() - 40) / min(len(self.switch.vlans), max_per_row)
        
        # Dessiner chaque VLAN avec ajustement vertical
        vlan_count = 0
        for vlan_id, vlan_name in self.switch.vlans.items():
            row_offset = (vlan_count // max_per_row) * 20
            col_position = vlan_count % max_per_row
            
            x = 20 + col_position * vlan_legend_width
            y = y_pos + 10 + row_offset  # Ajouté +10 pixels
            
            if vlan_id in self.vlan_colors:
                # Carré de couleur
                color = self.vlan_colors[vlan_id]
                painter.setBrush(QBrush(color))
                painter.setPen(QPen(Qt.black, 1))
                painter.drawRect(int(x), int(y), 15, 15)
                
                # Texte toujours blanc comme montré dans l'image
                painter.setPen(QColor(255, 255, 255))
                
                # Texte (limité en longueur)
                display_name = f"{vlan_id} - {vlan_name}"
                if len(display_name) > 20:
                    display_name = display_name[:17] + "..."
                painter.drawText(int(x + 20), int(y + 12), display_name)
            
            vlan_count += 1
        
        # Réinitialiser la couleur du stylo à noir pour le reste du dessin
        painter.setPen(Qt.black)
    
    def get_port_at_position(self, x, y):
        """Détermine quel port est à la position (x,y)"""
        if not self.layout_data:
            self.calculate_layout()
            
        # Extraire les données de mise en page
        layout = self.switch.port_layout
        cols = self.layout_data['cols']
        port_size = self.layout_data['port_size']
        h_spacing = self.layout_data['h_spacing']
        y_top = self.layout_data['y_top']
        y_bottom = self.layout_data['y_bottom']
        
        # Vérifier si c'est sur la rangée du haut (ports impairs)
        if y_top <= y <= y_top + port_size:
            for col in range(cols):
                x_pos = 20 + h_spacing + col * (port_size + h_spacing)
                if x_pos <= x <= x_pos + port_size:
                    port_number = col * 2 + 1  # Ports impairs: 1, 3, 5...
                    if port_number <= layout["total_ports"]:
                        return port_number
        
        # Vérifier si c'est sur la rangée du bas (ports pairs)
        elif y_bottom <= y <= y_bottom + port_size:
            for col in range(cols):
                x_pos = 20 + h_spacing + col * (port_size + h_spacing)
                if x_pos <= x <= x_pos + port_size:
                    port_number = col * 2 + 2  # Ports pairs: 2, 4, 6...
                    if port_number <= layout["total_ports"]:
                        return port_number
        
        return None
    
    def mousePressEvent(self, event):
        port_number = self.get_port_at_position(event.position().x(), event.position().y())
        
        if port_number:
            self.selected_port = port_number
            if self.main_window and hasattr(self.main_window, 'show_port_config_dialog'):
                self.main_window.show_port_config_dialog(port_number)
            else:
                if ENDORIUM_AVAILABLE:
                    logger.error(f"Impossible de configurer le port {port_number}, fenêtre principale non disponible")
                print(f"Erreur: impossible de configurer le port {port_number}")
    
    def resizeEvent(self, event):
        # Forcer le recalcul de la disposition lors du redimensionnement
        self.layout_data = None
        super().resizeEvent(event)

# Dialogue de configuration pour un port
class PortConfigDialog(QDialog):
    def __init__(self, port_number, vlans, current_config=None, supports_poe=False, parent=None):
        super().__init__(parent)
        self.port_number = port_number
        self.vlans = vlans
        self.supports_poe = supports_poe
        self.setWindowTitle(f"Configuration du port {port_number}")
        
        layout = QVBoxLayout(self)
        
        form_layout = QFormLayout()
        
        # Mode du port
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["access", "trunk", "shutdown"])
        self.mode_combo.currentTextChanged.connect(self.update_ui)
        form_layout.addRow("Mode:", self.mode_combo)
        
        # VLAN (pour mode access)
        self.vlan_combo = QComboBox()
        for vlan_id, vlan_name in vlans.items():
            self.vlan_combo.addItem(f"{vlan_id} - {vlan_name}", vlan_id)
        form_layout.addRow("VLAN:", self.vlan_combo)
        
        # Option PoE (si supporté)
        self.poe_checkbox = QCheckBox("Activer PoE sur ce port")
        if supports_poe:
            form_layout.addRow("", self.poe_checkbox)
        
        layout.addLayout(form_layout)
        
        # Appliquer la configuration actuelle si elle existe
        if current_config:
            self.mode_combo.setCurrentText(current_config.get('mode', 'access'))
            vlan = current_config.get('vlan')
            if vlan is not None:
                index = self.vlan_combo.findData(vlan)
                if index >= 0:
                    self.vlan_combo.setCurrentIndex(index)
            
            # État du PoE
            if supports_poe:
                self.poe_checkbox.setChecked(current_config.get('poe', False))
        
        # Mettre à jour l'UI en fonction du mode
        self.update_ui(self.mode_combo.currentText())
            
        # Boutons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def update_ui(self, mode):
        # Activer/désactiver la sélection du VLAN selon le mode
        self.vlan_combo.setEnabled(mode == "access")
        # Désactiver PoE si le port est en shutdown
        if self.supports_poe:
            self.poe_checkbox.setEnabled(mode != "shutdown")
            if mode == "shutdown":
                self.poe_checkbox.setChecked(False)
    
    def get_config(self):
        mode = self.mode_combo.currentText()
        result = {'mode': mode}
        if mode == "access":
            result['vlan'] = self.vlan_combo.currentData()
        
        # Ajouter l'état du PoE si supporté
        if self.supports_poe:
            result['poe'] = self.poe_checkbox.isChecked()
        
        return result

# Dialogue pour configurer les interfaces VLAN
class VlanInterfaceDialog(QDialog):
    def __init__(self, vlans, current_configs=None, parent=None):
        super().__init__(parent)
        self.vlans = vlans
        self.current_configs = current_configs or {}
        self.setWindowTitle("Configuration des interfaces VLAN")
        self.resize(500, 400)
        
        layout = QVBoxLayout(self)
        
        # Onglet pour chaque VLAN
        self.tabs = QTabWidget()
        for vlan_id, vlan_name in vlans.items():
            tab = QWidget()
            tab_layout = QFormLayout(tab)
            
            # Configuration IP
            ip_input = QLineEdit()
            mask_input = QLineEdit()
            
            # État de l'interface
            shutdown_checkbox = QCheckBox("Interface désactivée")
            
            # Commentaires pour l'interface
            description_input = QLineEdit()
            
            # Options supplémentaires selon le type de VLAN
            dhcp_checkbox = QCheckBox("Activer le serveur DHCP")
            
            # Charger la configuration existante
            if vlan_id in self.current_configs:
                config = self.current_configs[vlan_id]
                ip_input.setText(config.get('ip', ''))
                mask_input.setText(config.get('mask', ''))
                shutdown_checkbox.setChecked(config.get('shutdown', False))
                description_input.setText(config.get('description', ''))
                dhcp_checkbox.setChecked(config.get('dhcp_enabled', False))
            
            tab_layout.addRow("Adresse IP:", ip_input)
            tab_layout.addRow("Masque:", mask_input)
            tab_layout.addRow("Description:", description_input)
            tab_layout.addRow("", shutdown_checkbox)
            tab_layout.addRow("", dhcp_checkbox)
            
            # Stocker les widgets pour récupérer les valeurs plus tard
            tab.ip_input = ip_input
            tab.mask_input = mask_input
            tab.shutdown_checkbox = shutdown_checkbox
            tab.description_input = description_input
            tab.dhcp_checkbox = dhcp_checkbox
            
            self.tabs.addTab(tab, f"VLAN {vlan_id} - {vlan_name}")
        
        layout.addWidget(self.tabs)
        
        # Boutons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def get_configs(self):
        result = {}
        for i in range(self.tabs.count()):
            tab = self.tabs.widget(i)
            vlan_id = list(self.vlans.keys())[i]
                
            result[vlan_id] = {
                'ip': tab.ip_input.text(),
                'mask': tab.mask_input.text(),
                'shutdown': tab.shutdown_checkbox.isChecked(),
                'description': tab.description_input.text(),
                'dhcp_enabled': tab.dhcp_checkbox.isChecked()
            }
        return result

# Dialogue pour gérer les utilisateurs SSH
class SSHUserDialog(QDialog):
    def __init__(self, ssh_users, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gestion des utilisateurs SSH")
        self.resize(500, 300)
        self.ssh_users = ssh_users.copy()
        
        layout = QVBoxLayout(self)
        
        # Table des utilisateurs SSH
        self.user_table = QTableWidget(0, 3)
        self.user_table.setHorizontalHeaderLabels(["Login", "Mot de passe", "Privilège"])
        self.user_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.user_table)
        
        # Formulaire d'ajout
        form_layout = QHBoxLayout()
        self.login_input = QLineEdit()
        self.login_input.setPlaceholderText("Login")
        form_layout.addWidget(self.login_input)
        
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Mot de passe")
        self.password_input.setEchoMode(QLineEdit.Password)
        form_layout.addWidget(self.password_input)
        
        self.privilege_input = QLineEdit()
        self.privilege_input.setPlaceholderText("Privilège (0-15)")
        form_layout.addWidget(self.privilege_input)
        
        add_btn = QPushButton("Ajouter")
        add_btn.clicked.connect(self.add_user)
        form_layout.addWidget(add_btn)
        
        layout.addLayout(form_layout)
        
        # Bouton de suppression
        delete_btn = QPushButton("Supprimer l'utilisateur sélectionné")
        delete_btn.clicked.connect(self.delete_selected_user)
        layout.addWidget(delete_btn)
        
        # Boutons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        # Charger les utilisateurs existants
        self.load_users()
    
    def load_users(self):
        for user in self.ssh_users:
            row_position = self.user_table.rowCount()
            self.user_table.insertRow(row_position)
            self.user_table.setItem(row_position, 0, QTableWidgetItem(user['login']))
            self.user_table.setItem(row_position, 1, QTableWidgetItem(user['password']))
            self.user_table.setItem(row_position, 2, QTableWidgetItem(str(user['privilege'])))
    
    def add_user(self):
        try:
            login = self.login_input.text()
            password = self.password_input.text()
            privilege = int(self.privilege_input.text())
            
            if not login or not password or privilege < 0 or privilege > 15:
                raise ValueError("Informations utilisateur invalides")
            
            # Vérifier si l'utilisateur existe déjà
            for row in range(self.user_table.rowCount()):
                if self.user_table.item(row, 0).text() == login:
                    response = QMessageBox.question(self, "Utilisateur existant", 
                                                 f"L'utilisateur {login} existe déjà. Voulez-vous le remplacer ?",
                                                 QMessageBox.Yes | QMessageBox.No)
                    if response == QMessageBox.No:
                        return
                    
                    # Mettre à jour la ligne existante
                    self.user_table.setItem(row, 1, QTableWidgetItem(password))
                    self.user_table.setItem(row, 2, QTableWidgetItem(str(privilege)))
                    break
            else:
                # Ajouter à la table
                row_position = self.user_table.rowCount()
                self.user_table.insertRow(row_position)
                self.user_table.setItem(row_position, 0, QTableWidgetItem(login))
                self.user_table.setItem(row_position, 1, QTableWidgetItem(password))
                self.user_table.setItem(row_position, 2, QTableWidgetItem(str(privilege)))
            
            # Effacer les champs
            self.login_input.clear()
            self.password_input.clear()
            self.privilege_input.clear()
            
            # Mettre à jour la liste
            self.ssh_users = [{'login': self.user_table.item(row, 0).text(),
                               'password': self.user_table.item(row, 1).text(),
                               'privilege': int(self.user_table.item(row, 2).text())}
                              for row in range(self.user_table.rowCount())]
            
        except ValueError as e:
            QMessageBox.warning(self, "Erreur", str(e))
    
    def delete_selected_user(self):
        selected_rows = self.user_table.selectedIndexes()
        if not selected_rows:
            QMessageBox.warning(self, "Avertissement", "Veuillez sélectionner un utilisateur à supprimer.")
            return
        
        row = selected_rows[0].row()
        login = self.user_table.item(row, 0).text()
        
        response = QMessageBox.question(self, "Confirmation", 
                                     f"Êtes-vous sûr de vouloir supprimer l'utilisateur {login} ?",
                                     QMessageBox.Yes | QMessageBox.No)
        if response == QMessageBox.Yes:
            self.user_table.removeRow(row)
            self.ssh_users = [{'login': self.user_table.item(row, 0).text(),
                               'password': self.user_table.item(row, 1).text(),
                               'privilege': int(self.user_table.item(row, 2).text())}
                              for row in range(self.user_table.rowCount())]
    
    def accept(self):
        super().accept()

# Fenêtre principale
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Switch Configurator")
        self.resize(800, 600)
        
        self.switch = None
        
        # stocker préférences
        self.settings = QSettings("Endorium", "SwitchConfigurator")
        self.show_brand_model_dialog()
    
    def show_brand_model_dialog(self):
        dialog = BrandModelSelectionDialog(self)
        if dialog.exec():
            self.switch = Switch(dialog.selected_brand, dialog.selected_model)
            if ENDORIUM_AVAILABLE:
                logger.info(f"Switch sélectionné: {dialog.selected_brand} {dialog.selected_model}")
            self.show_vlan_config_dialog()
        else:
            # L'utilisateur a annulé, quitter l'application
            QApplication.quit()
    
    def show_vlan_config_dialog(self):
        dialog = VlanConfigurationDialog(self)
        if dialog.exec():
            # Copier les VLANs configurés dans notre switch
            self.switch.vlans = dialog.vlans.copy()
            if ENDORIUM_AVAILABLE:
                logger.info(f"VLANs configurés: {len(self.switch.vlans)}")
            self.show_hostname_dialog()
        else:
            # Revenir à la sélection de marque et modèle
            self.show_brand_model_dialog()
    
    def show_hostname_dialog(self):
        dialog = HostnameDialog(self.switch.hostname, self)
        if dialog.exec():
            hostname = dialog.get_hostname()
            if hostname:
                self.switch.set_hostname(hostname)
                if ENDORIUM_AVAILABLE:
                    logger.info(f"Hostname défini: {hostname}")
            self.setup_main_ui()
        else:
            # Revenir à la configuration des VLANs
            self.show_vlan_config_dialog()
    
    def setup_main_ui(self):
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)
        
        # Interface à onglets
        tabs = QTabWidget()
        
        # Onglet pour la configuration des ports
        ports_tab = QWidget()
        ports_layout = QVBoxLayout(ports_tab)
        
        # Widget pour représenter le switch - passer self comme fenêtre principale
        self.switch_widget = SwitchPortWidget(self.switch, self, ports_tab)
        ports_layout.addWidget(self.switch_widget)
        
        # Informations d'aide
        help_label = QLabel("Cliquez sur un port pour configurer son mode et son VLAN.")
        help_label.setAlignment(Qt.AlignCenter)
        ports_layout.addWidget(help_label)
        
        # Boutons d'action pour les ports
        ports_actions = QHBoxLayout()
        
        configure_range_btn = QPushButton("Configurer une plage de ports")
        configure_range_btn.clicked.connect(self.show_port_range_dialog)
        ports_actions.addWidget(configure_range_btn)
        
        reset_ports_btn = QPushButton("Réinitialiser tous les ports")
        reset_ports_btn.clicked.connect(self.reset_all_ports)
        ports_actions.addWidget(reset_ports_btn)
        
        ports_layout.addLayout(ports_actions)
        
        tabs.addTab(ports_tab, "Configuration des Ports")
        
        # Onglet pour la configuration des interfaces VLAN
        vlan_interfaces_tab = QWidget()
        vlan_interfaces_layout = QVBoxLayout(vlan_interfaces_tab)
        
        vlan_interfaces_btn = QPushButton("Configurer les interfaces VLAN")
        vlan_interfaces_btn.clicked.connect(self.show_vlan_interface_dialog)
        vlan_interfaces_layout.addWidget(vlan_interfaces_btn)
        
        vlan_status_layout = QGridLayout()
        vlan_status_layout.addWidget(QLabel("VLAN"), 0, 0)
        vlan_status_layout.addWidget(QLabel("Adresse IP"), 0, 1)
        vlan_status_layout.addWidget(QLabel("État"), 0, 2)
        row = 1
        for vlan_id, vlan_name in self.switch.vlans.items():
            vlan_settings = self.switch.vlan_interfaces.get(vlan_id, {})
            ip_address = vlan_settings.get('ip', "Non configuré")
            status = "Désactivé" if vlan_settings.get('shutdown', False) else "Actif"
            vlan_status_layout.addWidget(QLabel(f"{vlan_id} - {vlan_name}"), row, 0)
            vlan_status_layout.addWidget(QLabel(ip_address), row, 1)
            vlan_status_layout.addWidget(QLabel(status), row, 2)
            row += 1
        
        vlan_interfaces_layout.addLayout(vlan_status_layout)
        vlan_interfaces_layout.addStretch()
        tabs.addTab(vlan_interfaces_tab, "Interfaces VLAN")
        
        # Onglet pour la génération de configuration
        config_tab = QWidget()
        config_layout = QVBoxLayout(config_tab)
        
        generate_btn = QPushButton("Générer la configuration")
        generate_btn.clicked.connect(self.generate_config)
        config_layout.addWidget(generate_btn)
        
        self.config_output = QTextEdit()
        self.config_output.setReadOnly(True)
        config_layout.addWidget(self.config_output)
        
        save_btn = QPushButton("Enregistrer la configuration")
        save_btn.clicked.connect(self.save_config)
        config_layout.addWidget(save_btn)
        
        # profils
        profil_layout = QHBoxLayout()
        save_prof = QPushButton("Enregistrer profil")
        save_prof.clicked.connect(self.save_profile)
        load_prof = QPushButton("Charger profil")
        load_prof.clicked.connect(self.load_profile)
        profil_layout.addWidget(save_prof)
        profil_layout.addWidget(load_prof)
        config_layout.addLayout(profil_layout)
        
        # Bouton pour envoyer la configuration via TFTP
        if TFTP_AVAILABLE:
            tftp_btn = QPushButton("Envoyer via TFTP")
            tftp_btn.clicked.connect(self.send_config_via_tftp)
            config_layout.addWidget(tftp_btn)

        # --- Nouveau : bouton pour console série ---
        if SERIAL_AVAILABLE:
            console_btn = QPushButton("Envoyer via console")
            console_btn.clicked.connect(self.send_config_via_console)
            config_layout.addWidget(console_btn)

        tabs.addTab(config_tab, "Configuration")
        
        # Onglet pour SNMP
        snmp_tab = QWidget()
        snmp_layout = QFormLayout(snmp_tab)
        
        # Active/désactive SNMP
        snmp_enabled_checkbox = QCheckBox("Activer SNMP")
        snmp_enabled_checkbox.setChecked(self.switch.snmp_enabled)
        snmp_layout.addRow("", snmp_enabled_checkbox)
        
        # Version SNMP
        snmp_version_combo = QComboBox()
        snmp_version_combo.addItems(["1", "2c", "3"])
        snmp_version_combo.setCurrentText(self.switch.snmp_version)
        snmp_layout.addRow("Version SNMP:", snmp_version_combo)
        
        # Communauté SNMP
        snmp_community_input = QLineEdit(self.switch.snmp_community)
        snmp_community_input.setPlaceholderText("Communauté SNMP")
        snmp_layout.addRow("Communauté:", snmp_community_input)
        
        # Emplacement SNMP
        snmp_location_input = QLineEdit(self.switch.snmp_location)
        snmp_location_input.setPlaceholderText("Localisation")
        snmp_layout.addRow("Localisation:", snmp_location_input)
        
        # Contact SNMP
        snmp_contact_input = QLineEdit(self.switch.snmp_contact)
        snmp_contact_input.setPlaceholderText("Contact administrateur")
        snmp_layout.addRow("Contact:", snmp_contact_input)
        
        # Connexion des signaux pour mettre à jour les attributs du switch
        def update_snmp_config():
            self.switch.set_snmp(
                snmp_enabled_checkbox.isChecked(),
                snmp_community_input.text(),
                snmp_version_combo.currentText(),
                snmp_location_input.text(),
                snmp_contact_input.text()
            )
        
        snmp_enabled_checkbox.stateChanged.connect(update_snmp_config)
        snmp_version_combo.currentTextChanged.connect(update_snmp_config)
        snmp_community_input.textChanged.connect(update_snmp_config)
        snmp_location_input.textChanged.connect(update_snmp_config)
        snmp_contact_input.textChanged.connect(update_snmp_config)
        
        tabs.addTab(snmp_tab, "SNMP")
        
        # Onglet pour SSH
        ssh_tab = QWidget()
        ssh_layout = QFormLayout(ssh_tab)
        
        # Active/désactive SSH
        self.ssh_enabled_checkbox = QCheckBox("Activer SSH")
        self.ssh_enabled_checkbox.setChecked(self.switch.ssh_enabled)
        ssh_layout.addRow("", self.ssh_enabled_checkbox)
        
        # Version SSH
        ssh_version_combo = QComboBox()
        ssh_version_combo.addItems(["1", "2"])
        ssh_version_combo.setCurrentText(self.switch.ssh_version)
        ssh_layout.addRow("Version SSH:", ssh_version_combo)
        
        # Timeout SSH
        ssh_timeout_input = QLineEdit(self.switch.ssh_timeout)
        ssh_timeout_input.setPlaceholderText("Délai d'attente (secondes)")
        ssh_layout.addRow("Timeout:", ssh_timeout_input)
        
        # Nombre de tentatives d'authentification
        ssh_retries_input = QLineEdit(self.switch.ssh_auth_retries)
        ssh_retries_input.setPlaceholderText("Nombre d'essais")
        ssh_layout.addRow("Tentatives d'auth:", ssh_retries_input)
        
        # Authentification par clé
        ssh_key_auth_checkbox = QCheckBox("Utiliser l'authentification par clé")
        ssh_key_auth_checkbox.setChecked(self.switch.ssh_key_auth)
        ssh_layout.addRow("", ssh_key_auth_checkbox)
        
        # Bouton pour gérer les utilisateurs SSH
        ssh_users_btn = QPushButton("Gérer les utilisateurs SSH")
        ssh_users_btn.clicked.connect(self.show_ssh_user_dialog)
        ssh_layout.addRow("", ssh_users_btn)
        
        # Connexion des signaux pour mettre à jour les attributs du switch
        def update_ssh_config():
            self.switch.set_ssh(
                self.ssh_enabled_checkbox.isChecked(),
                ssh_version_combo.currentText(),
                ssh_timeout_input.text(),
                ssh_retries_input.text(),
                ssh_key_auth_checkbox.isChecked()
            )
        
        self.ssh_enabled_checkbox.stateChanged.connect(update_ssh_config)
        
        # Si on active SSH et qu'il n'y a pas encore d'utilisateurs, on ouvre la popup
        def on_ssh_enable_popup(state):
            if state == Qt.Checked and not self.switch.ssh_users:
                self.show_ssh_user_dialog()
        self.ssh_enabled_checkbox.stateChanged.connect(on_ssh_enable_popup)
        
        tabs.addTab(ssh_tab, "SSH")
        
        # Nouvel onglet pour Spanning Tree
        stp_tab = QWidget()
        stp_layout = QFormLayout(stp_tab)
        
        # Active/désactive Spanning Tree
        stp_enabled_checkbox = QCheckBox("Activer Spanning Tree")
        stp_enabled_checkbox.setChecked(self.switch.stp_enabled)
        stp_layout.addRow("", stp_enabled_checkbox)
        
        # Mode Spanning Tree
        stp_mode_combo = QComboBox()
        stp_mode_combo.addItems(["rapid-pvst", "pvst", "mst"])
        stp_mode_combo.setCurrentText(self.switch.stp_mode)
        stp_layout.addRow("Mode STP:", stp_mode_combo)
        
        # Priorité Spanning Tree
        stp_priority_combo = QComboBox()
        stp_priority_combo.addItems(["0", "4096", "8192", "12288", "16384", "20480", "24576", "28672", "32768", "36864", "40960", "45056", "49152", "53248", "57344", "61440"])
        stp_priority_combo.setCurrentText(self.switch.stp_priority)
        stp_layout.addRow("Priorité:", stp_priority_combo)
        
        # Paramètres supplémentaires
        stp_portfast_checkbox = QCheckBox("Activer PortFast par défaut")
        stp_portfast_checkbox.setChecked(self.switch.stp_portfast)
        stp_layout.addRow("", stp_portfast_checkbox)
        
        stp_bpduguard_checkbox = QCheckBox("Activer BPDU Guard")
        stp_bpduguard_checkbox.setChecked(self.switch.stp_bpduguard)
        stp_layout.addRow("", stp_bpduguard_checkbox)
        
        stp_loopguard_checkbox = QCheckBox("Activer Loop Guard")
        stp_loopguard_checkbox.setChecked(self.switch.stp_loopguard)
        stp_layout.addRow("", stp_loopguard_checkbox)
        
        # Connexion des signaux pour mettre à jour les attributs du switch
        def update_stp_config():
            self.switch.set_spanning_tree(
                stp_enabled_checkbox.isChecked(),
                stp_mode_combo.currentText(),
                stp_priority_combo.currentText(),
                stp_portfast_checkbox.isChecked(),
                stp_bpduguard_checkbox.isChecked(),
                stp_loopguard_checkbox.isChecked()
            )
        
        stp_enabled_checkbox.stateChanged.connect(update_stp_config)
        stp_mode_combo.currentTextChanged.connect(update_stp_config)
        stp_priority_combo.currentTextChanged.connect(update_stp_config)
        stp_portfast_checkbox.stateChanged.connect(update_stp_config)
        stp_bpduguard_checkbox.stateChanged.connect(update_stp_config)
        stp_loopguard_checkbox.stateChanged.connect(update_stp_config)
        
        tabs.addTab(stp_tab, "Spanning Tree")
        
        # Onglet d'informations
        info_tab = QWidget()
        info_layout = QVBoxLayout(info_tab)
        
        info_text = QLabel(f"""
        <h2>Switch Configurator</h2>
        <p>Version: {APP_VERSION}</p>
        <p>Ce programme permet de configurer graphiquement des switches et de générer des configurations.</p>
        <h3>Switch actuel:</h3>
        <p>Marque: {self.switch.brand}</p>
        <p>Modèle: {self.switch.model}</p>
        <p>Hostname: {self.switch.hostname}</p>
        <p>Nombre de VLANs configurés: {len(self.switch.vlans)}</p>
        <p>Nombre de ports configurés: {len(self.switch.ports)}</p>
        """)
        info_text.setAlignment(Qt.AlignTop)
        info_text.setTextFormat(Qt.RichText)
        info_layout.addWidget(info_text)
        
        change_hostname_btn = QPushButton("Modifier le nom d'hôte")
        change_hostname_btn.clicked.connect(lambda: self.show_hostname_dialog_with_update(info_text))
        info_layout.addWidget(change_hostname_btn)
        
        back_to_brand_btn = QPushButton("Recommencer avec un autre switch")
        back_to_brand_btn.clicked.connect(self.confirm_restart)
        info_layout.addWidget(back_to_brand_btn)
        
        tabs.addTab(info_tab, "Informations")
        
        main_layout.addWidget(tabs)
        
        self.setCentralWidget(central_widget)
    
    def show_hostname_dialog_with_update(self, info_label):
        """Affiche le dialogue de hostname et met à jour l'onglet d'infos."""
        dialog = HostnameDialog(self.switch.hostname, self)
        if dialog.exec():
            hostname = dialog.get_hostname()
            if hostname:
                self.switch.set_hostname(hostname)
                if ENDORIUM_AVAILABLE:
                    logger.info(f"Hostname modifié: {hostname}")
                    
                # Mettre à jour l'affichage du switch
                self.switch_widget.update()
                
                # Mettre à jour les informations
                info_label.setText(f"""
                <h2>Switch Configurator</h2>
                <p>Version: {APP_VERSION}</p>
                <p>Ce programme permet de configurer graphiquement des switches et de générer des configurations.</p>
                <h3>Switch actuel:</h3>
                <p>Marque: {self.switch.brand}</p>
                <p>Modèle: {self.switch.model}</p>
                <p>Hostname: {self.switch.hostname}</p>
                <p>Nombre de VLANs configurés: {len(self.switch.vlans)}</p>
                <p>Nombre de ports configurés: {len(self.switch.ports)}</p>
                """)
    
    def confirm_restart(self):
        """Demande confirmation avant de redémarrer avec un nouveau switch."""
        response = QMessageBox.question(self, "Confirmation", 
                                     "Êtes-vous sûr de vouloir recommencer avec un nouveau switch ? Toutes les configurations actuelles seront perdues.",
                                     QMessageBox.Yes | QMessageBox.No)
        if response == QMessageBox.Yes:
            self.show_brand_model_dialog()
    
    def show_port_config_dialog(self, port_number):
        current_config = self.switch.ports.get(port_number, {})
        dialog = PortConfigDialog(port_number, self.switch.vlans, current_config, self.switch.supports_poe, self)
        if dialog.exec():
            config = dialog.get_config()
            poe_enabled = config.get('poe', False) if self.switch.supports_poe else False
            self.switch.set_port_config(port_number, config['mode'], config.get('vlan'), poe_enabled)
            self.switch_widget.update()
            if ENDORIUM_AVAILABLE:
                logger.info(f"Port {port_number} configuré: {config}")
    
    def show_port_range_dialog(self):
        """Affiche une boîte de dialogue pour configurer une plage de ports."""
        if not self.switch.vlans:
            QMessageBox.warning(self, "Avertissement", "Veuillez d'abord configurer des VLANs.")
            return
        
        # Créer la boîte de dialogue
        dialog = QDialog(self)
        dialog.setWindowTitle("Configuration d'une plage de ports")
        dialog.resize(450, 200)
        
        layout = QVBoxLayout(dialog)
        
        form = QFormLayout()
        
        # Sélection de la plage de ports
        range_layout = QHBoxLayout()
        port_start = QLineEdit()
        port_start.setPlaceholderText("Port de début")
        range_layout.addWidget(port_start)
        
        range_layout.addWidget(QLabel("à"))
        
        port_end = QLineEdit()
        port_end.setPlaceholderText("Port de fin")
        range_layout.addWidget(port_end)
        
        form.addRow("Plage de ports:", range_layout)
        
        # Mode de port
        mode_combo = QComboBox()
        mode_combo.addItems(["access", "trunk", "shutdown"])
        form.addRow("Mode:", mode_combo)
        
        # VLAN pour le mode access
        vlan_combo = QComboBox()
        for vlan_id, vlan_name in self.switch.vlans.items():
            vlan_combo.addItem(f"{vlan_id} - {vlan_name}", vlan_id)
        form.addRow("VLAN (pour mode access):", vlan_combo)
        
        # Option PoE (si supporté)
        poe_checkbox = QCheckBox("Activer PoE sur ces ports")
        if self.switch.supports_poe:
            form.addRow("", poe_checkbox)
        
        layout.addLayout(form)
        
        # Activer/désactiver le combo VLAN selon le mode
        def update_ui(mode):
            vlan_combo.setEnabled(mode == "access")
            if self.switch.supports_poe:
                poe_checkbox.setEnabled(mode != "shutdown")
                if mode == "shutdown":
                    poe_checkbox.setChecked(False)
        
        mode_combo.currentTextChanged.connect(update_ui)
        update_ui(mode_combo.currentText())
        
        # Boutons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        
        # Exécuter la boîte de dialogue
        if dialog.exec():
            try:
                start = int(port_start.text())
                end = int(port_end.text())
                
                if start <= 0 or end <= 0 or start > end or end > self.switch.port_layout["total_ports"]:
                    raise ValueError("Plage de ports invalide")
                
                mode = mode_combo.currentText()
                vlan = vlan_combo.currentData() if mode == "access" else None
                poe_enabled = poe_checkbox.isChecked() if self.switch.supports_poe else False
                
                # Configurer tous les ports dans la plage
                for port in range(start, end + 1):
                    self.switch.set_port_config(port, mode, vlan, poe_enabled)
                
                # Mettre à jour l'affichage
                self.switch_widget.update()
                if ENDORIUM_AVAILABLE:
                    logger.info(f"Ports {start}-{end} configurés en mode {mode}" + 
                                (f", PoE: {poe_enabled}" if self.switch.supports_poe else ""))
                QMessageBox.information(self, "Succès", f"Ports {start} à {end} configurés en mode {mode}")
                
            except ValueError as e:
                QMessageBox.warning(self, "Erreur", str(e))
    
    def reset_all_ports(self):
        """Réinitialise tous les ports du switch."""
        response = QMessageBox.question(self, "Confirmation", 
                                     "Êtes-vous sûr de vouloir réinitialiser tous les ports ?",
                                     QMessageBox.Yes | QMessageBox.No)
        if response == QMessageBox.Yes:
            self.switch.ports = {}
            self.switch_widget.update()
            if ENDORIUM_AVAILABLE:
                logger.info("Tous les ports ont été réinitialisés")
    
    def show_vlan_interface_dialog(self):
        dialog = VlanInterfaceDialog(self.switch.vlans, self.switch.vlan_interfaces, self)
        if dialog.exec():
            self.switch.vlan_interfaces = dialog.get_configs()
            if ENDORIUM_AVAILABLE:
                logger.info(f"Interfaces VLAN configurées: {len(self.switch.vlan_interfaces)}")
            
            # Mettre à jour l'onglet des interfaces VLAN
            if hasattr(self, "setCentralWidget"):  # Pour éviter des erreurs si l'UI n'est pas encore initialisée
                self.setup_main_ui()
    
    def show_ssh_user_dialog(self):
        dialog = SSHUserDialog(self.switch.ssh_users, self)
        if dialog.exec():
            self.switch.ssh_users = dialog.ssh_users.copy()
            if ENDORIUM_AVAILABLE:
                logger.info(f"Utilisateurs SSH configurés: {len(self.switch.ssh_users)}")
    
    def generate_config(self):
        config_text = self.switch.generate_config()
        self.config_output.setPlainText(config_text)
        if ENDORIUM_AVAILABLE:
            logger.info("Configuration générée")
        # Proposer l'envoi via TFTP après génération
        if TFTP_AVAILABLE:
            réponse = QMessageBox.question(
                self,
                "Envoyer via TFTP",
                "La configuration a été générée. Voulez-vous l'envoyer via TFTP ?",
                QMessageBox.Yes | QMessageBox.No
            )
            if réponse == QMessageBox.Yes:
                self.send_config_via_tftp()
        # --- Nouveau : proposer l'envoi via console après génération ---
        if SERIAL_AVAILABLE:
            resp = QMessageBox.question(
                self,
                "Envoyer via console",
                "La configuration a été générée. Voulez‑vous l'envoyer via la console ?",
                QMessageBox.Yes | QMessageBox.No
            )
            if resp == QMessageBox.Yes:
                self.send_config_via_console()
    
    def save_config(self):
        if not self.config_output.toPlainText():
            QMessageBox.warning(self, "Erreur", "Veuillez d'abord générer la configuration.")
            return
        
        try:
            filepath, _ = QFileDialog.getSaveFileName(self, "Enregistrer la configuration", "", "Fichiers texte (*.txt);;Tous les fichiers (*)")
            
            if filepath:
                with open(filepath, 'w') as f:
                    f.write(self.config_output.toPlainText())
                QMessageBox.information(self, "Succès", f"Configuration enregistrée dans {filepath}")
                if ENDORIUM_AVAILABLE:
                    logger.info(f"Configuration enregistrée dans {filepath}")
                # Proposer l'envoi via TFTP après sauvegarde
                if TFTP_AVAILABLE:
                    rep = QMessageBox.question(
                        self,
                        "Envoyer via TFTP",
                        "Configuration enregistrée. Voulez-vous l'envoyer via TFTP ?",
                        QMessageBox.Yes | QMessageBox.No
                    )
                    if rep == QMessageBox.Yes:
                        switch_ip, ok = QInputDialog.getText(
                            self,
                            "Adresse IP du Switch",
                            "Entrez l'adresse IP du switch cible :"
                        )
                        if ok and switch_ip:
                            success, message = upload_config_via_tftp(
                                self.config_output.toPlainText(), switch_ip
                            )
                            if success:
                                QMessageBox.information(self, "Succès", f"Envoyé via TFTP : {message}")
                                if ENDORIUM_AVAILABLE:
                                    logger.info(f"TFTP envoyé : {message}")
                            else:
                                QMessageBox.critical(self, "Erreur", f"Échec TFTP : {message}")
                # --- Nouveau : proposer console après sauvegarde ---
                if SERIAL_AVAILABLE:
                    r = QMessageBox.question(
                        self,
                        "Envoyer via console",
                        "Configuration enregistrée. Voulez‑vous l'envoyer via la console ?",
                        QMessageBox.Yes | QMessageBox.No
                    )
                    if r == QMessageBox.Yes:
                        self.send_config_via_console()
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible d'enregistrer le fichier: {str(e)}")
            if ENDORIUM_AVAILABLE:
                logger.error(f"Erreur lors de l'enregistrement: {str(e)}")
    
    def save_profile(self):
        """Sauvegarde profil JSON complet."""
        fpath, _ = QFileDialog.getSaveFileName(self, "Enregistrer profil", "*.json", "JSON (*.json)")
        if not fpath:
            return
        prof = {
            "vlans": self.switch.vlans,
            "ports": self.switch.ports,
            "vlan_interfaces": self.switch.vlan_interfaces,
            "snmp": {
                "enabled": self.switch.snmp_enabled,
                "community": self.switch.snmp_community,
                "version": self.switch.snmp_version,
                "location": self.switch.snmp_location,
                "contact": self.switch.snmp_contact,
            },
            "ssh": {
                "enabled": self.switch.ssh_enabled,
                "version": self.switch.ssh_version,
                "timeout": self.switch.ssh_timeout,
                "retries": self.switch.ssh_auth_retries,
                "key": self.switch.ssh_key_auth,
                "users": self.switch.ssh_users,
            },
            "stp": {
                "enabled": self.switch.stp_enabled,
                "mode": self.switch.stp_mode,
                "priority": self.switch.stp_priority,
                "portfast": self.switch.stp_portfast,
                "bpduguard": self.switch.stp_bpduguard,
                "loopguard": self.switch.stp_loopguard,
            },
        }
        with open(fpath, "w") as f:
            json.dump(prof, f, indent=2)
        QMessageBox.information(self, "Succès", "Profil enregistré")

    def load_profile(self):
        """Charge un profil JSON et applique."""
        fpath, _ = QFileDialog.getOpenFileName(self, "Charger profil", "", "JSON (*.json)")
        if fpath and ENDORIUM_AVAILABLE:
            logger.debug(f"load_profile: selected file {fpath}")
        if not fpath:
            return
        try:
            if ENDORIUM_AVAILABLE:
                logger.debug("load_profile: reading file content")
            with open(fpath, "r") as f:
                raw = f.read()
            txt = re.sub(r'//.*', '', raw)
            prof = json.loads(txt)
            # Conversion des clés en int
            vlans_raw = prof.get("vlans", {})
            self.switch.vlans = {int(k): v for k, v in vlans_raw.items()}
            ports_raw = prof.get("ports", {})
            self.switch.ports = {int(k): v for k, v in ports_raw.items()}
            vlan_if_raw = prof.get("vlan_interfaces", {})
            self.switch.vlan_interfaces = {int(k): v for k, v in vlan_if_raw.items()}
            sn = prof.get("snmp", {})
            self.switch.set_snmp(
                sn.get("enabled", False),
                sn.get("community", ""),
                sn.get("version", ""),
                sn.get("location", ""),
                sn.get("contact", ""),
            )
            sh = prof.get("ssh", {})
            self.switch.set_ssh(
                sh.get("enabled", False),
                sh.get("version", ""),
                sh.get("timeout", ""),
                sh.get("retries", ""),
                sh.get("key", False),
            )
            self.switch.ssh_users = sh.get("users", [])
            st = prof.get("stp", {})
            self.switch.set_spanning_tree(
                st.get("enabled", True),
                st.get("mode", ""),
                st.get("priority", ""),
                st.get("portfast", True),
                st.get("bpduguard", True),
                st.get("loopguard", False),
            )
            self.setup_main_ui()
            QMessageBox.information(self, "Succès", "Profil chargé")
        except Exception as e:
            if ENDORIUM_AVAILABLE:
                logger.exception("load_profile: exception during loading profile")
            QMessageBox.warning(self, "Erreur", str(e))

    def send_config_via_tftp(self):
        """Envoie la configuration générée via TFTP."""
        if not TFTP_AVAILABLE:
            QMessageBox.warning(self, "Erreur", "Le module TFTP n'est pas disponible.")
            return
        
        if not self.config_output.toPlainText():
            QMessageBox.warning(self, "Erreur", "Veuillez d'abord générer la configuration.")
            return
        
        # Demander l'adresse IP du switch
        switch_ip, ok = QInputDialog.getText(self, "Adresse IP du Switch", 
                                        "Entrez l'adresse IP du switch cible:")
        if not ok or not switch_ip:
            return
        
        # ping / connectivité
        if not check_connectivity(switch_ip):
            QMessageBox.warning(self, "Erreur", "Switch non joignable (ping).")
            return
            
        # Créer une boîte de dialogue de progression
        progress_dialog = QDialog(self)
        progress_dialog.setWindowTitle("Envoi TFTP en cours")
        progress_dialog.resize(400, 150)
        
        dialog_layout = QVBoxLayout(progress_dialog)
        progress_label = QLabel(f"Envoi de la configuration au switch {switch_ip}...")
        dialog_layout.addWidget(progress_label)
        
        progress_bar = QProgressBar()
        progress_bar.setRange(0, 0)  # Barre de progression indéterminée
        dialog_layout.addWidget(progress_bar)
        
        status_label = QLabel("Préparation de l'envoi...")
        dialog_layout.addWidget(status_label)
        
        # Montrer la boîte de dialogue sans bloquer
        progress_dialog.show()
        QApplication.processEvents()
        
        try:
            # Envoi de la configuration directement via la fonction TFTP
            config_text = self.config_output.toPlainText()
            status_label.setText("Envoi en cours...")
            QApplication.processEvents()
            
            success, message = upload_config_via_tftp(config_text, switch_ip)
            
            # Fermer la boîte de dialogue de progression
            progress_dialog.close()
            
            if success:
                QMessageBox.information(self, "Succès", f"Configuration envoyée avec succès: {message}")
                if ENDORIUM_AVAILABLE:
                    logger.info(f"Configuration envoyée au switch {switch_ip} via TFTP: {message}")
            else:
                QMessageBox.critical(self, "Erreur", f"Échec de l'envoi TFTP: {message}")
                if ENDORIUM_AVAILABLE:
                    logger.error(f"Échec de l'envoi TFTP vers {switch_ip}: {message}")
                    
        except Exception as e:
            progress_dialog.close()
            QMessageBox.critical(self, "Erreur", f"Impossible d'envoyer la configuration via TFTP: {str(e)}")
            if ENDORIUM_AVAILABLE:
                logger.error(f"Erreur lors de l'envoi via TFTP: {str(e)}")

    # --- Nouveau : méthode d'envoi via le port console série ---
    def send_config_via_console(self):
        if not SERIAL_AVAILABLE:
            QMessageBox.warning(self, "Erreur", "Le module de communication série n'est pas disponible.")
            return
        if not self.config_output.toPlainText():
            QMessageBox.warning(self, "Erreur", "Veuillez d'abord générer la configuration.")
            return

        # choix port COM auto
        ports = list_available_serial_ports()
        last = self.settings.value("last_com_port", "")
        com_port, ok = QInputDialog.getItem(
            self,
            "Port COM",
            "Sélectionnez port:",
            ports,
            ports.index(last) if last in ports else 0,
            False,
        )
        if not ok:
            return
        self.settings.setValue("last_com_port", com_port)
        baud, ok = QInputDialog.getInt(self, "Baudrate", "Entrez la vitesse (baud):", 9600, 300, 115200)
        if not ok:
            return

        try:
            sender = SerialConfigSender(com_port, baud)
        except ImportError as e:
            QMessageBox.critical(self, "Erreur", str(e))
            return

        if not sender.connect():
            QMessageBox.critical(self, "Erreur", f"Impossible de se connecter sur {com_port} à {baud} bauds")
            return

        # Dialogue de progression
        progress_dialog = QDialog(self)
        progress_dialog.setWindowTitle("Envoi console en cours")
        progress_dialog.resize(400, 150)
        layout = QVBoxLayout(progress_dialog)
        layout.addWidget(QLabel(f"Envoi sur {com_port} @ {baud} bauds..."))
        pb = QProgressBar()
        pb.setRange(0, 0)
        layout.addWidget(pb)
        status = QLabel("")
        layout.addWidget(status)
        progress_dialog.show()
        QApplication.processEvents()

        sender.on_line_sent = lambda line, i, total: status.setText(f"Ligne {i}/{total}")
        sender.on_completed = lambda msg: (QMessageBox.information(self, "Succès", msg), progress_dialog.close())
        sender.on_error = lambda msg: (QMessageBox.critical(self, "Erreur", msg), progress_dialog.close())

        sender.send_configuration(self.config_output.toPlainText(), line_delay=0.5)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())



