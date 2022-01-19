# Installing on Pi

`apt install python3-pyqt5`
`pip install getmac`

### For popup keyboard

`apt install at-spi2-core onboard`

and set appropriate options to auto-show


### Useful running scripts

```
#!/bin/bash
cd /home/pi/PTZControllerUI

while true; do
        /usr/bin/python3 main.py
        printf "\n\nRestarting program...\n"
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
