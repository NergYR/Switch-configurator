"""
Module d'aide pour les opérations TFTP
"""
import os
import tempfile
import socket
import time
from threading import Thread, Event

# Vérifier si tftpy est disponible
try:
    import tftpy
    TFTP_AVAILABLE = True
except ImportError:
    TFTP_AVAILABLE = False

def is_tftp_available():
    """Vérifie si le module TFTP est disponible"""
    return TFTP_AVAILABLE

def check_connectivity(host, port=69, timeout=2):
    """Vérifie si un hôte est accessible"""
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_DGRAM).connect((host, port))
        return True
    except (socket.timeout, socket.error):
        return False

class TFTPServerThread(Thread):
    """Classe pour gérer un serveur TFTP dans un thread séparé"""
    def __init__(self, root_path=None, ip="0.0.0.0", port=69):
        Thread.__init__(self)
        self.daemon = True
        self.stop_event = Event()
        
        # Utiliser un répertoire temporaire si aucun n'est spécifié
        self.root_path = root_path or tempfile.mkdtemp()
        self.ip = ip
        self.port = port
        self.server = None
        self.success = False
        self.error_message = None
        
    def run(self):
        """Démarrer le serveur TFTP"""
        if not TFTP_AVAILABLE:
            self.error_message = "Module tftpy non disponible. Impossible de démarrer le serveur TFTP."
            return
        
        try:
            # Créer et démarrer le serveur
            self.server = tftpy.TftpServer(self.root_path)
            self.server.listen(self.ip, self.port)
            self.success = True
        except Exception as e:
            self.error_message = f"Erreur du serveur TFTP: {str(e)}"
    
    def stop(self):
        """Arrêter le serveur TFTP"""
        self.stop_event.set()
        if self.server:
            # Attendre un peu avant de fermer le serveur
            time.sleep(0.5)
            try:
                self.server.stop()
            except:
                pass

def upload_config_via_tftp(config_text, switch_ip, filename="config.txt", timeout=30):
    """
    Télécharger une configuration vers un switch via TFTP
    
    Args:
        config_text (str): Texte de configuration à envoyer
        switch_ip (str): Adresse IP du switch
        filename (str): Nom du fichier à créer sur le switch
        timeout (int): Délai d'attente en secondes
    
    Returns:
        tuple: (succès, message)
    """
    if not TFTP_AVAILABLE:
        return False, "Module TFTP non disponible. Installez tftpy avec 'pip install tftpy'."
    
    # Créer un fichier temporaire avec la configuration
    temp_dir = tempfile.mkdtemp()
    config_path = os.path.join(temp_dir, filename)
    
    try:
        # Vérifier la connectivité d'abord
        if not check_connectivity(switch_ip):
            return False, f"Le switch {switch_ip} n'est pas accessible. Vérifiez la connexion."
        
        # Écrire la config dans un fichier temporaire
        with open(config_path, 'w') as f:
            f.write(config_text)
        
        # Démarrer un serveur TFTP
        server = TFTPServerThread(temp_dir)
        server.start()
        
        # Attendre que le serveur démarre
        start_time = time.time()
        while not server.success and server.error_message is None and time.time() - start_time < 5:
            time.sleep(0.5)
            
        if not server.success:
            if server.error_message:
                return False, server.error_message
            return False, "Le serveur TFTP n'a pas pu démarrer dans le délai imparti."
        
        try:
            # Le client TFTP envoie une requête de téléchargement au switch
            client = tftpy.TftpClient(switch_ip, 69)
            # Le 2e paramètre de upload désigne le nom du fichier sur le serveur
            client.upload(filename, config_path)
            return True, f"Configuration envoyée avec succès à {switch_ip} via TFTP."
        except tftpy.TftpException as e:
            return False, f"Erreur TFTP: {str(e)}"
    except Exception as e:
        return False, f"Erreur lors de l'envoi via TFTP: {str(e)}"
    finally:
        # Arrêter le serveur
        if 'server' in locals():
            server.stop()
        
        # Nettoyer
        try:
            os.remove(config_path)
            os.rmdir(temp_dir)
        except:
            pass
