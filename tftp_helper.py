"""
Module d'aide pour les opérations TFTP
"""
import os
import tempfile
import socket
import time

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
    
    # Création et écriture du fichier temporaire
    temp_dir = tempfile.mkdtemp()
    config_path = os.path.join(temp_dir, filename)

    try:
        # Vérifier la connectivité
        if not check_connectivity(switch_ip):
            return False, f"Le switch {switch_ip} n'est pas accessible. Vérifiez la connexion."

        # Écrire la configuration
        with open(config_path, 'w') as f:
            f.write(config_text)

        # Envoi direct via TftpClient (client → switch)
        client = tftpy.TftpClient(switch_ip, 69)
        client.upload(filename, config_path)
        return True, f"Configuration envoyée avec succès à {switch_ip} via TFTP."

    except tftpy.TftpException as e:
        return False, f"Erreur TFTP: {str(e)}"
    except Exception as e:
        return False, f"Erreur lors de l'envoi via TFTP: {str(e)}"
    finally:
        # Nettoyage
        try:
            os.remove(config_path)
            os.rmdir(temp_dir)
        except:
            pass
