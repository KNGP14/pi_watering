import RPi.GPIO as GPIO
from datetime import datetime, timedelta
import configparser

# Konfigurationsdatei einlesen
config = configparser.ConfigParser()
config.read('pi_watering.config')

# Zeitschaltungen
config_section='ZEITSTEUERUNG'
SECONDS_SCHALTHYSTERESE = config.getint(config_section, 'SECONDS_SCHALTHYSTERESE', fallback=10)
SECONDS_KUECHE_PAVILLION = config.getint(config_section, 'SECONDS_KUECHE_PAVILLION', fallback=120)
SECONDS_GARAGE = config.getint(config_section, 'SECONDS_GARAGE', fallback=120)
SECONDS_BEET_EINGANG = config.getint(config_section, 'SECONDS_BEET_EINGANG', fallback=100)
MAX_LAUFZEIT_PUFFER = config.getint(config_section, 'MAX_LAUFZEIT_PUFFER', fallback=100)
LAUFZEIT = SECONDS_SCHALTHYSTERESE + \
           SECONDS_KUECHE_PAVILLION + \
           SECONDS_SCHALTHYSTERESE + \
           SECONDS_GARAGE + \
           SECONDS_SCHALTHYSTERESE + \
           SECONDS_BEET_EINGANG + \
           SECONDS_SCHALTHYSTERESE
MAX_RUNTIME_SECONDS=LAUFZEIT+MAX_LAUFZEIT_PUFFER
MAX_RUNTIME = timedelta(seconds = MAX_RUNTIME_SECONDS)

# GPIO-Belegung
config_section='GPIO_BELEGUNG'
GPIO_OUT_HAUPTWASSER = config.getint(config_section, 'GPIO_OUT_HAUPTWASSER', fallback=6)
GPIO_OUT_KUECHE_PAVILLION = config.getint(config_section, 'GPIO_OUT_KUECHE_PAVILLION', fallback=13)
GPIO_OUT_GARAGE = config.getint(config_section, 'GPIO_OUT_GARAGE', fallback=19)
GPIO_OUT_BEET_EINGANG = config.getint(config_section, 'GPIO_OUT_BEET_EINGANG', fallback=26)

# Sicherungsdatei für Hauptwasser-Status
config_section='ALLGEMEIN'
LOCKFILE = config.get(config_section, 'LOCKFILE', fallback='gpio.status')
STATUS_AUF = config.get(config_section, 'STATUS_AUF', fallback='AUF')
STATUS_WIRD_GEOEFFNET = config.get(config_section, 'STATUS_WIRD_GEOEFFNET', fallback='WIRD_GEOEFFNET')
STATUS_ZU = config.get(config_section, 'STATUS_ZU', fallback='ZU')

print('\n#######################################')
print('# Überprüfung des Bewässerungssystems #')
print('#######################################\n')

# BCM-Nummerierung verwenden
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

# GPIOs einrichten
try:
    GPIO.setup(GPIO_OUT_HAUPTWASSER, GPIO.OUT)
    GPIO.setup(GPIO_OUT_KUECHE_PAVILLION, GPIO.OUT)
    GPIO.setup(GPIO_OUT_GARAGE, GPIO.OUT)
    GPIO.setup(GPIO_OUT_BEET_EINGANG, GPIO.OUT)
except:
    print('ERROR: Fehler beim Konfigurieren der GPIO Ein- und Ausgänge\n')

# Hilfsfunktion zum Prüfen, ob Ausgang geschalten (open=True)
def gpio_is_open(name, gpio_id):
    print(' > Prüfe Status für "{:s}" mit GPIO {:d}'.format(name, gpio_id))

    # Status auslesen und zurückgeben
    gpio_status=GPIO.input(gpio_id)
    if(gpio_status == 1):
        print(' > "{:s}" offen ({:d}={:d})'.format(name, gpio_id, gpio_status))
        return True
    else:
        print(' > "{:s}" geschlossen ({:d}={:d})'.format(name, gpio_id, gpio_status))
        return False

# Hilfsfunktion zum Schließen eines GPIOs
def close_gpio(name, gpio_id):
    print('NOTAUS initieren durch Schließen von GPIO {:d} "{:s}" ...\n'.format(gpio_id, name))
    try:
        GPIO.output(gpio_id, False)
        print(' > GPIO erfolgreich geschlossen')
    except:
        print('ERROR: Fehler beim Schließen!')

    # Sicherungsinfo schreiben (falls GPIO für Hauptwasser)
    if(name=="Hauptwasser"):
        lockFile = open(LOCKFILE, "w")
        lockFile.write('Hauptwasser=ZU;{:s}'.format(str(datetime.now())))
        lockFile.close()

###########################################
# Sicherungsdatei einlesen un Status prüfen
###########################################

lockfile_content=""
try:
    f = open(LOCKFILE, "r")
    lockfile_content=f.read()

except FileNotFoundError:
    print('Sicherungsdatei "{:s}" nicht vorhanden = kein Skriptabbruch vermutet\n'.format(LOCKFILE))
    hauptwasser_open = gpio_is_open("Hauptwasser", GPIO_OUT_HAUPTWASSER)
    if(hauptwasser_open):
        print(' > Hauptwasser offen trotz fehlender Sicherungsdatei = FEHLERZUSTAND\n')
        close_gpio("Hauptwasser", GPIO_OUT_HAUPTWASSER)
    else:
        print(' > Alles okay')
except:
    print('ERROR: Datei {:s} konnte nicht geöffnet werden ...\n'.format(LOCKFILE))
    exit(1)

if lockfile_content.find(";") != -1:
    # Beispiel: Hauptwasser=OFFEN;2024-07-21 14:06:38.233326
    tmp=lockfile_content.split(';')
    status=tmp[0]
    timestamp_str=tmp[1]

    #Beispiel: Hauptwasser=OFFEN
    tmp=status.split('=')
    gpio_name=tmp[0]
    gpio_status=tmp[1]

    if(gpio_status==STATUS_AUF):
        print('{:s} geöffnet laut Sicherungsdatei.\n'.format(gpio_name))

        print(' > Prüfe Zeitstempel "{:s}"'.format(timestamp_str))
        timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S.%f')
        runtime=datetime.now()-timestamp
        print(' > Laufzeit = {:s} (max. {:s})'.format(str(runtime), str(MAX_RUNTIME)))
        if(runtime>MAX_RUNTIME):
            print(' > Maximale Laufzeit von {:s} (h:mm:ss) überschritten!\n'.format(str(MAX_RUNTIME)))
            close_gpio(gpio_name, GPIO_OUT_HAUPTWASSER)
        else:
            print(' > Alles okay')
    
    elif(gpio_status==STATUS_WIRD_GEOEFFNET):
        print('{:s} wird gerade geöffnet laut Sicherungsdatei.\n'.format(gpio_name))
        print(' > Alles okay')

    elif(gpio_status==STATUS_ZU):
        print('{:s} geschlossen laut Sicherungsdatei.\n'.format(gpio_name))
        print(' > Alles okay')
        #TODO: Prüfen, ob realer GPIO-Status trotzdem nochmal geprüft werden sollte

    else:
        print('ERROR: Unbekannter Status "{:s}" in Sicherungsdatei "{:s}"'.format(gpio_status, LOCKFILE))
else:
    print(lockfile_content)

print('\n#########################################')
print('# https://github.com/KNGP14/pi_watering #')
print('#########################################\n')
exit(0)