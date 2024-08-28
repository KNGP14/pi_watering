# pi_watering
Bewässerungssystem für Raspberry PI (2B)

## Zeitseuerung
Empfehlung: Nutzung von crontab-ui

Manuelle Metode mit `crontab -e`:
```
crontab -e
0 7 * * * python /path/to/pi_watering/pi_watering.py >> /path/to/pi_watering/pi_watering.log 2>&1
0 20 * * * python /path/to/pi_watering/pi_watering.py >> /path/to/pi_watering/pi_watering.log 2>&1
7,14,21,28,35,42,49,56 * * * python /path/to/pi_watering/pi_watering.py >/dev/null 2>&1
```