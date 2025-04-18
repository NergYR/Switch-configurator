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
        
    def run(self):
        """Démarrer le serveur TFTP"""
        if not TFTP_AVAILABLE:
            print("Module tftpy non disponible. Impossible de démarrer le serveur TFTP.")
            return
        
        try:
            # Créer et démarrer le serveur
            self.server = tftpy.TftpServer(self.root_path)
            self.server.listen(self.ip, self.port)
        except Exception as e:
            print(f"Erreur du serveur TFTP: {str(e)}")
    
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

def upload_config_via_tftp(config_text, switch_ip, filename="config.txt"):
    """Télécharger une configuration vers un switch via TFTP"""
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
        time.sleep(1)
        
        # Le client TFTP envoie une requête de téléchargement au switch
        # Mais en réalité, c'est le switch qui va venir chercher le fichier
        client = tftpy.TftpClient(switch_ip, 69)
        client.upload(filename, config_path)
        
        # Arrêter le serveur
        server.stop()
        
        return True, f"Configuration envoyée avec succès à {switch_ip} via TFTP."
    except Exception as e:
        return False, f"Erreur lors de l'envoi via TFTP: {str(e)}"
    finally:
        # Nettoyer
        try:
            os.remove(config_path)
            os.rmdir(temp_dir)
        except:
            pass
