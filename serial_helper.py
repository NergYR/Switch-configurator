"""
Module d'aide pour les opérations de communication série
"""
import os
import time
import threading

# Vérifier si pyserial est disponible
try:
    import serial
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False

def is_serial_available():
    """Vérifie si le module de communication série est disponible"""
    return SERIAL_AVAILABLE

def list_available_serial_ports():
    """Retourne la liste des ports série disponibles"""
    if not SERIAL_AVAILABLE:
        return []
    
    from serial.tools import list_ports
    return [port.device for port in list_ports.comports()]

def get_standard_baud_rates():
    """Retourne les vitesses de transmission standard"""
    return ["9600", "19200", "38400", "57600", "115200"]

class SerialConfigSender:
    """Classe pour envoyer des configurations via un port série"""
    def __init__(self, com_port, baud_rate=9600, timeout=1):
        """
        Initialise un envoyeur de configuration série.
        
        Args:
            com_port (str): Port COM à utiliser (ex: "COM1")
            baud_rate (int): Vitesse en bauds (ex: 9600)
            timeout (float): Délai d'attente en secondes
        """
        if not SERIAL_AVAILABLE:
            raise ImportError("Module pyserial non disponible. Installez-le avec 'pip install pyserial'")
        
        self.com_port = com_port
        self.baud_rate = int(baud_rate)
        self.timeout = timeout
        self.ser = None
        self.is_connected = False
        self.is_sending = False
        self.last_error = None
        
        # Callbacks pour suivre la progression
        self.on_progress = None
        self.on_line_sent = None
        self.on_completed = None
        self.on_error = None
    
    def connect(self):
        """Établit une connexion avec le port série"""
        try:
            self.ser = serial.Serial(
                port=self.com_port,
                baudrate=self.baud_rate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.timeout
            )
            self.is_connected = True
            return True
        except Exception as e:
            self.last_error = str(e)
            if self.on_error:
                self.on_error(f"Erreur de connexion: {str(e)}")
            return False
    
    def disconnect(self):
        """Ferme la connexion série"""
        if self.ser and self.is_connected:
            try:
                self.ser.close()
            finally:
                self.is_connected = False
    
    def send_configuration(self, config_text, line_delay=0.5):
        """
        Envoie une configuration ligne par ligne au périphérique.
        
        Args:
            config_text (str): Texte de configuration à envoyer
            line_delay (float): Délai en secondes entre chaque ligne
        """
        if not self.is_connected:
            if not self.connect():
                return False
        
        self.is_sending = True
        thread = threading.Thread(target=self._send_config_thread, 
                                 args=(config_text, line_delay))
        thread.daemon = True
        thread.start()
        return True
    
    def _send_config_thread(self, config_text, line_delay):
        """Thread d'envoi de configuration"""
        try:
            lines = config_text.splitlines()
            total_lines = len(lines)
            
            for i, line in enumerate(lines):
                if not self.is_sending:
                    break
                
                # Envoyer la ligne avec retour à la ligne
                self.ser.write((line + '\r\n').encode('utf-8'))
                
                # Lire la réponse (facultatif)
                response = self.ser.read_until(b'#', timeout=1)
                
                # Notifications de progression
                if self.on_progress:
                    progress = (i + 1) / total_lines
                    self.on_progress(progress)
                
                if self.on_line_sent:
                    self.on_line_sent(line, i+1, total_lines)
                
                # Attendre entre chaque ligne
                time.sleep(line_delay)
            
            # Notification de fin
            if self.on_completed and self.is_sending:
                self.on_completed("Configuration envoyée avec succès")
            
        except Exception as e:
            self.last_error = str(e)
            if self.on_error:
                self.on_error(f"Erreur lors de l'envoi: {str(e)}")
        finally:
            self.is_sending = False
    
    def cancel(self):
        """Annule l'envoi en cours"""
        self.is_sending = False
