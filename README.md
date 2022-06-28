SSDTTime
==========
A simple tool designed to make creating SSDTs simple.
Supports macOS, Linux and Windows

## Supported SSDTs:
- SSDT-EC
    - OS-aware fake EC
- SSDT-EC-Laptop
    - Only Builds Fake EC - Leaves Existing Untouched
- SSDT-PMC
    - Enables Native NVRAM on True 300-Series Boards
- SSDT-AWAC
    - Context-Aware AWAC Disable and RTC Fake
- SSDT-PLUG
    - Sets plugin-type = 1 on CPU0/PR00
- SSDT-HPET
    - Patches out IRQ conflicts
- SSDT-USB_Reset
    -  Reset USB controllers to allow hardware mapping
    
Additionally on Linux and Windows the tool can be used to dump the system DSDT.

## Instructions:
### Linux:
* Launch SSDTTime.py with any somewhat recent version of Python from either a terminal window or by running the file normally.
### macOS:
* Launch SSDTTime.command from either a terminal window or by double clicking the file.
### Windows:
* Launch SSDTTime.bat from either a terminal window or by double clicking the file.

## Credits:
- [CorpNewt](https://github.com/CorpNewt) - Writing the script and libraries used
- [NoOne](https://github.com/IOIIIO) - Some small improvements to the script
- Rehabman/Intel - iasl
