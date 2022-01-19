# Installing on Pi

`apt install python3-pyqt5`
`pip install getmac`

### For popup keyboard

`apt install at-spi2-core onboard`

and set appropriate options to auto-show


### Useful running scripts

```bash
#!/bin/bash
cd /home/pi/PTZControllerUI

RESTART_FILE=/tmp/norestart

while true; do
    /usr/bin/python3 main.py
    printf "\n\nCrash occured?\n\n"
    if [ -f "$RESTART_FILE" ]; then
        printf "norestart file detected, exiting for good"
        break
    fi
    read -p "Press any key to restart"
    printf "Restarting program...\n"
done
```
```
[Desktop Entry]
Type=Application
Name=Onboard Keyboard
Exec=/usr/bin/onboard
```
```
[Desktop Entry]
Type=Application
Name=PTZ Controller
Exec=/usr/bin/lxterminal -e /home/pi/runPTZ.sh
```
