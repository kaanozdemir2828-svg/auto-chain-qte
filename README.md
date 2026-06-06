# Auto Chain QTE
Auto Chain QTE is a simple Windows tool that detects QTE letters on screen and presses the correct key automatically.
Supported letters:
E, R, T, F, G

## Requirements
You need:
- Windows 10 or Windows 11
- Python 3





Download Python here:
https://www.python.org/downloads/

During installation, check:

Add Python to PATH
## Install Required Packages

Open Command Prompt in the program folder and run:

pip install opencv-python pillow numpy pydirectinput
## Included Files





## How to Use
1. Open Chain from Roblox.
2. Open auto_chain_qte_v7.
3. Choose your monitor size.
4. Click START.





## Monitor Presets
The program includes these monitor presets:
4K 3840x2160
QHD / 2K 2560x1440
Full HD 1920x1080
HD 1366x768
Choose the one that matches your monitor.





## If the Program Does Not Start
Check Python:
python --version

Then install the packages again:
pip install opencv-python pillow numpy pydirectinput





## If the Bot Does Not Press Keys
Try these:
- Click once inside the game window.
- Choose the correct monitor size.
- Make sure the game window is active.





## If the Bot Spams Keys
Open the Python file and increase this value : PRESS_THRESHOLD = 0.80
Try
PRESS_THRESHOLD = 0.85
or
PRESS_THRESHOLD = 0.90
or more





## If the Bot Misses Letters
Open the Python file and lower this value : PRESS_THRESHOLD = 0.55
Try
PRESS_THRESHOLD = 0.50
or
PRESS_THRESHOLD = 0.45
or less





## Notes
Auto Chain QTE works locally on your computer.
It does not upload your data.
It does not need internet after installation.
It only checks part of your screen and compares it with the included letter files.
