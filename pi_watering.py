from argparse import ArgumentParser
import RPi.GPIO as GPIO # type: ignore
import time
from datetime import datetime, timedelta
import configparser

# crontab -e
# TODO: Install-Parameter zum Installieren/Überschreiben des crontab
# 0 7 * * * python /home/seiko/gpio.py >> /home/seiko/gpio.log 2>&1
# 0 20 * * * python /home/seiko/gpio.py >> /home/seiko/gpio.log 2>&1
# 7,14,21,28,35,42,49,56 * * * python /home/seiko/gpio_check.py >/dev/null 2>&1


print('\n################################')
print('# Raspberry-Bewässerungssystem #')
print('################################')

# Zeitmessung starten
print('')
startTime = datetime.now()
print( 'Zeitstempel: {:s}'.format(str(startTime)))

#############################
# Programmoptionen
#############################

DEFAULT_WATERING_CONFIG='pi_watering.config'

parser = ArgumentParser(
            description='Bewässerungssystem für Raspberry Pi 2B')

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
    print(' - Hauptschalter-Stellung überbrückt')
    print(' - verkürzte Bewässerungszeit von 2 Sekunden')
    print(' - CLI_PARAM_GPIO_CONFIG: {:s}'.format(args.CLI_PARAM_GPIO_CONFIG))
    print(' - CLI_PARAM_CONFIG: {:s}'.format(args.CLI_PARAM_CONFIG))

# Debug-Schalter erzeugt mehr Ausgaben und reduziert Schaltzeiten
DEBUG = args.CLI_PARAM_DEBUG

#############################
# Bewässerungs-Konfiguration
#############################

# Bewässerungs-Konfiguration einlesen
if(DEBUG):
    print('')
    print(f'Bewässerungs-Konfiguration einlesen von {args.CLI_PARAM_CONFIG} ...')
config = configparser.ConfigParser()
try:
    config.read(args.CLI_PARAM_CONFIG)
except Exception as e:
    print('')
    print(f'Fehler beim Einlese der Bewässerungs-Konfigurationsdatei {args.CLI_PARAM_CONFIG}!\n{e}')
    exit(1)

# Zeitschaltungen
config_section='ZEITSTEUERUNG'
SECONDS_SCHALTHYSTERESE = config.getint(config_section, 'SECONDS_SCHALTHYSTERESE', fallback=10)
SECONDS_KUECHE_PAVILLION = config.getint(config_section, 'SECONDS_KUECHE_PAVILLION', fallback=120)
SECONDS_GARAGE = config.getint(config_section, 'SECONDS_GARAGE', fallback=120)
SECONDS_BEET_EINGANG = config.getint(config_section, 'SECONDS_BEET_EINGANG', fallback=100)

# Sicherung für Hauptwasser-Status
config_section='ALLGEMEIN'
LOCKFILE = config.get(config_section, 'LOCKFILE', fallback='gpio.status')
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

    GPIO.setup(GPIO_IN_HAUPTSCHALTER, GPIO.IN)
except Exception as e:
    print(f'ERROR: Fehler beim Konfigurieren der GPIO Ein- und Ausgänge\n{e}')
    exit(1)

#############################
# Hilfunktionen
#############################

# Hilfsfunktion: Steuern des Hauptwasser
def control_main(mode):

    if(mode==STATUS_AUF):

        print(' > Hauptwasser (GPIO {:d}) öffnen und {:d}s warten ...\n'.format(GPIO_OUT_HAUPTWASSER, SECONDS_SCHALTHYSTERESE))

        # Sicherungsinfo zu geöffnetem Hauptwasser bei Absurz
        try:
            lockFile = open(LOCKFILE, "w")
            lockFile.write('Hauptwasser={:s};{:s}'.format(STATUS_WIRD_GEOEFFNET, str(datetime.now())))
            lockFile.close()
        except:
            print('ERROR: Sicherungsinfo für Hauptwasser konnte nicht geschrieben werden in "{:s}"\n'.format(LOCKFILE))
            GPIO.output(GPIO_OUT_HAUPTWASSER, False)
            exit(1)

        GPIO.output(GPIO_OUT_HAUPTWASSER, True)

        # Sicherungsinfo zu geöffnetem Hauptwasser bei Absurz
        try:
            lockFile = open(LOCKFILE, "w")
            lockFile.write('Hauptwasser={:s};{:s}'.format(STATUS_AUF, str(datetime.now())))
            lockFile.close()
        except:
            print('ERROR: Sicherungsinfo für Hauptwasser konnte nicht geschrieben werden in "{:s}"\n'.format(LOCKFILE))
            GPIO.output(GPIO_OUT_HAUPTWASSER, False)
            exit(1)

        time.sleep(SECONDS_SCHALTHYSTERESE)

    elif(mode==STATUS_ZU):

        GPIO.output(GPIO_OUT_HAUPTWASSER, False)

        # Sicherungsinfo schreiben
        lockFile = open(LOCKFILE, "w")
        lockFile.write('Hauptwasser={:s};{:s}'.format(STATUS_ZU, str(datetime.now())))
        lockFile.close()

    else:
        print('ERROR: Unbekannter Modus für Hauptwasser')
        exit(1)

# Hilfsfunktion: Steuern einzelner Bereiche
def control_area(name, gpio_id, seconds, buffer):
    if(DEBUG):
        seconds=2
        buffer=2
    
    print(' > Bereich "{:s}" (GPIO {:d}) bewässern für {:d}s ...\n'.format(name, gpio_id, seconds))

    GPIO.output(gpio_id, True)
    time.sleep(seconds)
    GPIO.output(gpio_id, False)
    time.sleep(buffer)

#############################
# Programmstart
#############################

if(GPIO.input(GPIO_IN_HAUPTSCHALTER) == 1 or DEBUG):
    # Hauptschalter EIN >> Bewässerung starten

    print('')
    print('Bewässerung wird gestartet ...\n')

    control_main(STATUS_AUF)
    
    control_area("Küche-Pavlillion", GPIO_OUT_KUECHE_PAVILLION, SECONDS_KUECHE_PAVILLION, SECONDS_SCHALTHYSTERESE)
    
    control_area("Garage", GPIO_OUT_GARAGE, SECONDS_GARAGE, SECONDS_SCHALTHYSTERESE)
    
    control_area("Beet am Eingang", GPIO_OUT_BEET_EINGANG, SECONDS_BEET_EINGANG, SECONDS_SCHALTHYSTERESE)

    control_main(STATUS_ZU)


else:
    # Hauptschalter AUS >> keine Bewässerung
    print('INFO: Hauptschalter aus > keine Bewässerung\n')

# Benutzte GPIOs freigeben (GPIO-Ausgänge werden ausgeschalten)
GPIO.cleanup()


# Gemessene Laufzeit berechnen und Skript abschließen
endTime = datetime.now()
runTime = endTime - startTime
calculatedRunTime = SECONDS_SCHALTHYSTERESE + \
                    SECONDS_KUECHE_PAVILLION + \
                    SECONDS_SCHALTHYSTERESE + \
                    SECONDS_GARAGE + \
                    SECONDS_SCHALTHYSTERESE + \
                    SECONDS_BEET_EINGANG + \
                    SECONDS_SCHALTHYSTERESE
calculatedRunTime = timedelta(seconds = calculatedRunTime)

print('#############################################')
print('# Bewässerungssteuerung abgeschlossen       #')
print('#                                           #')
print('#  - theoretische Laufzeit: {:s}.000000  #'.format(str(calculatedRunTime)))
print('#  - gemessene Laufzeit:    {:s}  #'.format(str(runTime)))
print('#                                           #')
print('# https://github.com/KNGP14/pi_watering     #')
print('#############################################\n')

exit(0)