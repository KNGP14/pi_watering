from argparse import ArgumentParser
import RPi.GPIO as GPIO # type: ignore
from datetime import datetime, timedelta
import configparser

print('\n#######################################')
print('# Überprüfung des Bewässerungssystems #')
print('#######################################\n')

#############################
# Programmoptionen
#############################

parser = ArgumentParser(
            description='Überprüfung des Bewässerungssystems')

parser.add_argument(
            "-gc",
            "--gpio-config",
            default="../pi_config/pi.config",
            dest="CLI_PARAM_GPIO_CONFIG",
            required=False,
            help="Pfad zur GPIO-Konfiguration pi.config des pi_config-Repositories")
parser.add_argument(
            "-c",
            "--config",
            default="./pi_watering.config",
            dest="CLI_PARAM_CONFIG",
            required=False,
            help="Pfad zur Bewässerungs-Konfiguration pi_watering.config")
parser.add_argument(
            "-l",
            "--lockfile",
            default="./gpio.status",
            dest="CLI_PARAM_LOCKFILE",
            required=False,
            help="Pfad zur LOCK-Datei, die bei Ansteuerung von GPIOs erzeugt wird (für gpio_check.py)")
parser.add_argument(
            "-d",
            "--debug",
            default=False,
            dest="CLI_PARAM_DEBUG",
            required=False,
            action="store_true",
            help="Wenn angegeben, Debug-Modus aktivieren")

args = parser.parse_args()

if(args.CLI_PARAM_DEBUG):
    print('')
    print('DEBUG-Modus aktiviert:')
    print(' - CLI_PARAM_GPIO_CONFIG: {:s}'.format(args.CLI_PARAM_GPIO_CONFIG))
    print(' - CLI_PARAM_CONFIG: {:s}'.format(args.CLI_PARAM_CONFIG))
    print(' - CLI_PARAM_LOCKFILE: {:s}'.format(args.CLI_PARAM_LOCKFILE))

# Parameter setzen aus Optionen
DEBUG = args.CLI_PARAM_DEBUG
LOCKFILE = args.CLI_PARAM_LOCKFILE

# Konfigurationsdatei einlesen
config = configparser.ConfigParser()
config.read(args.CLI_PARAM_CONFIG)

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

# Sicherungsdatei für Hauptwasser-Status
config_section='ALLGEMEIN'
STATUS_AUF = config.get(config_section, 'STATUS_AUF', fallback='AUF')
STATUS_WIRD_GEOEFFNET = config.get(config_section, 'STATUS_WIRD_GEOEFFNET', fallback='WIRD_GEOEFFNET')
STATUS_ZU = config.get(config_section, 'STATUS_ZU', fallback='ZU')

#############################
# GPIO-Belegung
#############################

if(DEBUG):
    print('')
    print(f'GPIO-Belegung einlesen von {args.CLI_PARAM_GPIO_CONFIG} ...')
config = configparser.ConfigParser()
try:
    config.read(args.CLI_PARAM_GPIO_CONFIG)
except Exception as e:
    print('')
    print(f'Fehler beim Einlese der GPIO-Konfigurationsdatei {args.CLI_PARAM_GPIO_CONFIG}!\n{e}')
    exit(1)

def getGPIO(query_config, query_name, fallback):
    for section in query_config.sections():
        if "GPIO_" in section:
            name=query_config.get(section,"NAME", fallback="")
            if name==query_name:
                id=int(section[5:])
                mode=query_config.get(section,"MODE", fallback="")
                gpio_config = {
                    "id": id,
                    "mode": mode,
                    "name": name
                }
                if(DEBUG):
                    print(gpio_config)
                return gpio_config
    return fallback

try:
    GPIO_OUT_HAUPTWASSER = getGPIO(config, 'HAUPTWASSER', fallback=6)["id"]
    GPIO_OUT_KUECHE_PAVILLION = getGPIO(config, 'KUECHE_PAVILLION', fallback=13)["id"]
    GPIO_OUT_GARAGE = getGPIO(config, 'GARAGE', fallback=19)["id"]
    GPIO_OUT_BEET_EINGANG = getGPIO(config, 'BEET_EINGANG', fallback=26)["id"]
    GPIO_IN_HAUPTSCHALTER = getGPIO(config, 'HAUPTSCHALTER_BEWAESSERUNG', fallback=5)["id"]

    if(DEBUG):
        print(f' GPIO_OUT_HAUPTWASSER={GPIO_OUT_HAUPTWASSER}')
        print(f' GPIO_OUT_KUECHE_PAVILLION={GPIO_OUT_KUECHE_PAVILLION}')
        print(f' GPIO_OUT_GARAGE={GPIO_OUT_GARAGE}')
        print(f' GPIO_OUT_BEET_EINGANG={GPIO_OUT_BEET_EINGANG}')
        print(f' GPIO_IN_HAUPTSCHALTER={GPIO_IN_HAUPTSCHALTER}')
except Exception as e:
    print(f'ERROR: Fehler beim Einlesen und Umwandeln der GPIO Ein- und Ausgänge\n{e}')
    exit(1)

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

print('')
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